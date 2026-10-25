"""Логика лаунчера (без интерфейса): версии, установка, сборки с хостинга, запуск."""
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import requests
import minecraft_launcher_lib as mll

import netlayer
import skins

ROOT = Path.home() / ".mclauncher"
MC_DIR = ROOT / "minecraft"
INSTANCES = ROOT / "instances"
CONFIG = ROOT / "config.json"
LOADERS = ["Vanilla", "Fabric", "Forge", "Quilt"]

DEFAULTS = {"username": "Player", "ram_gb": 4, "version": "", "loader": "Vanilla",
            "hosting": "", "server": "", "mirror": "Авто", "proxy": "", "java": "", "skin": "",
            "theme": "dark", "accent": "Алмаз", "animations": True, "splash": True,
            "after_launch": "Ничего", "jvm_args": ""}


def sha1_of(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Core:
    def __init__(self, status=lambda t: None, progress=lambda v, m=None: None):
        self.status, self.progress = status, progress
        try:
            self.cfg = {**DEFAULTS, **json.loads(CONFIG.read_text("utf-8"))}
        except Exception:
            self.cfg = dict(DEFAULTS)
        self.apply_net()

    # ---- настройки ----
    def save(self, **changes):
        self.cfg.update(changes)
        ROOT.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(self.cfg, indent=2, ensure_ascii=False), "utf-8")
        self.apply_net()

    def apply_net(self):
        netlayer.NET["mode"] = self.cfg["mirror"] if self.cfg["mirror"] in netlayer.MIRROR_MODES else "Авто"
        netlayer.NET["proxy"] = self.cfg["proxy"].strip()
        netlayer._dead_hosts.clear()
        netlayer.apply_java_proxy(netlayer.NET["proxy"])

    # ---- версии и папки ----
    def get_versions(self):
        try:
            return mll.utils.get_version_list()
        except Exception:
            if MC_DIR.exists():
                return [{"id": v["id"], "type": "release"} for v in mll.utils.get_installed_versions(str(MC_DIR))]
            raise

    @staticmethod
    def instance_dir(version, loader):
        d = INSTANCES / f"{version}-{loader.lower()}".replace("/", "_")
        (d / "mods").mkdir(parents=True, exist_ok=True)
        return d

    # ---- свой хостинг ----
    def sync(self):
        url = self.cfg["hosting"]
        if not url:
            raise RuntimeError("Укажи URL manifest.json своего хостинга")
        self.status("Загрузка manifest.json...")
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        m = r.json()
        changes = {}
        if m.get("minecraft"):
            changes["version"] = m["minecraft"]
        if m.get("loader"):
            changes["loader"] = m["loader"].capitalize()
        if m.get("server"):
            changes["server"] = m["server"]
        self.save(**changes)

        game_dir = self.instance_dir(self.cfg["version"], self.cfg["loader"])
        files = m.get("files", [])
        self.progress(0, len(files))
        for i, item in enumerate(files, 1):
            dest = (game_dir / item["path"]).resolve()
            if game_dir.resolve() not in dest.parents:
                raise RuntimeError(f"Небезопасный путь в манифесте: {item['path']}")
            if not (dest.exists() and item.get("sha1") and sha1_of(dest) == item["sha1"]):
                self.status(f"Скачивание {item['path']} ({i}/{len(files)})")
                dest.parent.mkdir(parents=True, exist_ok=True)
                netlayer.download(item["url"], dest)
                if item.get("sha1") and sha1_of(dest) != item["sha1"]:
                    dest.unlink()
                    raise RuntimeError(f"Неверная контрольная сумма: {item['path']}")
            self.progress(i)
        self.status(f"Сборка «{m.get('name', '')}» синхронизирована")
        return changes

    # ---- установка и запуск ----
    def _callback(self):
        return {"setStatus": self.status, "setProgress": self.progress,
                "setMax": lambda m: self.progress(0, m)}

    # ---- Java ----
    def _java_component(self, version_id):
        """Какой JRE (по классификации Mojang) нужен этой версии. Для модовых версий смотрим родителя."""
        p = MC_DIR / "versions" / version_id / f"{version_id}.json"
        data = json.loads(p.read_text("utf-8"))
        if "javaVersion" in data:
            return data["javaVersion"]["component"]
        if "inheritsFrom" in data:
            return self._java_component(data["inheritsFrom"])
        return "jre-legacy"          # старые версии (Java 8)

    def java_for(self, version_id):
        """Путь к java: свой из настроек -> нужный JRE от Mojang (скачивается сам) -> java из PATH."""
        custom = self.cfg["java"].strip()
        if custom:
            if not Path(custom).is_file():
                raise RuntimeError(f"Java не найдена по пути: {custom}")
            return custom
        comp, mdir = self._java_component(version_id), str(MC_DIR)
        exe = mll.runtime.get_executable_path(comp, mdir)
        if not exe:
            self.status(f"Скачивание Java ({comp})...")
            try:
                mll.runtime.install_jvm_runtime(comp, mdir, callback=self._callback())
            except Exception:
                pass                  # нет сборки под эту систему/сеть: попробуем системную
            exe = mll.runtime.get_executable_path(comp, mdir)
        exe = exe or shutil.which("java")
        if not exe:
            raise RuntimeError("Не удалось получить Java. Включи зеркало/прокси на вкладке «Сеть» "
                               "или укажи путь к java.exe в поле «Java».")
        return exe

    # ---- установка ----
    def _find_installed(self, mc, loader):
        """id уже установленной версии (запуск без сети) или None, если ставить нужно."""
        vdir = MC_DIR / "versions" / mc
        if not (vdir / f"{mc}.json").exists() or not (vdir / f"{mc}.jar").exists():
            return None
        if (MC_DIR / f".installing-{mc}-{loader}").exists():      # прошлая установка прервалась
            return None
        if loader == "Vanilla":
            return mc
        ids = [v["id"] for v in mll.utils.get_installed_versions(str(MC_DIR))]
        if loader == "Forge":
            found = [i for i in ids if "forge" in i.lower() and i.startswith(mc)]
        else:
            found = [i for i in ids if loader.lower() + "-loader" in i and i.endswith(mc)]
        return sorted(found)[-1] if found else None

    def install(self, mc, loader):
        """Если версия уже стоит, сеть не нужна. Иначе скачивает. Возвращает (id версии, путь к java)."""
        vid = self._find_installed(mc, loader)
        if vid:
            return vid, self.java_for(mc)
        MC_DIR.mkdir(parents=True, exist_ok=True)
        flag = MC_DIR / f".installing-{mc}-{loader}"
        flag.write_text("")
        result = self._install_online(mc, loader)
        flag.unlink(missing_ok=True)
        return result

    def _install_online(self, mc, loader):
        """Ставит версию и загрузчик. Возвращает (id версии для запуска, путь к java)."""
        MC_DIR.mkdir(parents=True, exist_ok=True)
        cb, mdir = self._callback(), str(MC_DIR)
        mll.install.install_minecraft_version(mc, mdir, callback=cb)   # ваниль + данные о нужной Java
        java = self.java_for(mc)
        if loader == "Vanilla":
            return mc, java
        if loader == "Fabric":
            if not mll.fabric.is_minecraft_version_supported(mc):
                raise RuntimeError(f"Fabric не поддерживает {mc}")
            mll.fabric.install_fabric(mc, mdir, callback=cb)
        elif loader == "Quilt":
            if not mll.quilt.is_minecraft_version_supported(mc):
                raise RuntimeError(f"Quilt не поддерживает {mc}")
            mll.quilt.install_quilt(mc, mdir, callback=cb)
        elif loader == "Forge":
            fv = mll.forge.find_forge_version(mc)
            if not fv:
                raise RuntimeError(f"Forge для {mc} не найден")
            mll.forge.install_forge_version(fv, mdir, callback=cb, java=java)   # установщику нужна Java
            return mll.forge.forge_to_installed_version(fv), java
        key = loader.lower() + "-loader"
        found = [v["id"] for v in mll.utils.get_installed_versions(mdir)
                 if key in v["id"] and v["id"].endswith(mc)]
        if not found:
            raise RuntimeError("Не удалось найти установленную версию загрузчика")
        return sorted(found)[-1], java

    def play(self):
        if self.cfg["hosting"]:
            self.sync()
        mc, loader = self.cfg["version"], self.cfg["loader"]
        if not mc:
            raise RuntimeError("Выбери версию")
        self.status(f"Установка {mc} ({loader})...")
        version_id, java = self.install(mc, loader)

        name = self.cfg["username"]
        ram = int(self.cfg["ram_gb"]) * 1024
        options = {
            "username": name,
            "uuid": str(uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + name)),
            "token": "",
            "executablePath": java,
            "gameDirectory": str(self.instance_dir(mc, loader)),
            "jvmArguments": [f"-Xmx{ram}M", f"-Xms{min(1024, ram)}M"] + self.cfg.get("jvm_args", "").split(),
        }
        if self.cfg["server"]:
            host, _, port = self.cfg["server"].partition(":")
            options["server"], options["port"] = host, port or "25565"

        cmd = mll.command.get_minecraft_command(version_id, str(MC_DIR), options)
        try:
            skins.apply(self.cfg["skin"], options["gameDirectory"], mc)
        except Exception as e:                      # скин не должен мешать запуску игры
            self.status(f"Скин не применён: {e}")
        self.status("Запуск игры...")
        flags = 0x08000000 if sys.platform.startswith("win") else 0   # без чёрного окна консоли
        subprocess.Popen(cmd, cwd=options["gameDirectory"], creationflags=flags)
        self.status("Игра запущена. Приятной игры!")