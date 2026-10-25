"""Диагностика скинов. Запусти:  python check_skin.py   и пришли весь вывод."""
import json
import zipfile
from pathlib import Path

root = Path.home() / ".mclauncher"
try:
    cfg = json.loads((root / "config.json").read_text("utf-8"))
except Exception as e:
    cfg = {}
    print("config.json:", e)
print("Версия:", cfg.get("version"), "| загрузчик:", cfg.get("loader"), "| выбранный скин:", cfg.get("skin") or "нет")
try:
    print("Скины в библиотеке:", list(json.loads((root / "skins" / "index.json").read_text("utf-8")).items()))
except Exception as e:
    print("Библиотека скинов:", e)

for inst in sorted((root / "instances").glob("*")):
    print("\n==", inst.name)
    opt = inst / "options.txt"
    if opt.exists():
        for ln in opt.read_text("utf-8").splitlines():
            if ln.startswith(("resourcePacks", "incompatibleResourcePacks", "version")):
                print("  options:", ln)
    else:
        print("  options.txt НЕТ")
    pack = inst / "resourcepacks" / "AlmazikSkin.zip"
    if pack.exists():
        z = zipfile.ZipFile(pack)
        print("  pack.mcmeta:", z.read("pack.mcmeta").decode())
        print("  файлов в паке:", len(z.namelist()))
    else:
        print("  пака AlmazikSkin.zip НЕТ")
    mc = inst.name.rsplit("-", 1)[0]
    try:
        jar = root / "minecraft" / "versions" / mc / f"{mc}.jar"
        print("  pack_version игры:", json.loads(zipfile.ZipFile(jar).read("version.json")).get("pack_version"))
    except Exception as e:
        print("  version.json игры:", e)
    log = inst / "logs" / "latest.log"
    if log.exists():
        for ln in log.read_text("utf-8", "ignore").splitlines():
            if "AlmazikSkin" in ln or "esource pack" in ln:
                print("  log:", ln[:200])