"""Сетевой слой: зеркало BMCLAPI + прокси для запросов minecraft_launcher_lib."""
import os
from urllib.parse import urlsplit

import requests

# ======================= СЕТЬ: зеркало + прокси =======================
BMCL = "https://bmclapi2.bangbang93.com"
# хост Mojang/Fabric/Forge -> префикс пути на зеркале BMCLAPI
MIRRORS = {
    "launchermeta.mojang.com": "",
    "launcher.mojang.com": "",
    "piston-meta.mojang.com": "",
    "piston-data.mojang.com": "",
    "resources.download.minecraft.net": "/assets",
    "libraries.minecraft.net": "/maven",
    "maven.minecraftforge.net": "/maven",
    "files.minecraftforge.net": "",          # путь уже начинается с /maven/...
    "meta.fabricmc.net": "/fabric-meta",
    "maven.fabricmc.net": "/maven",
}
MIRROR_MODES = ["Авто", "Всегда", "Выкл"]
NET = {"mode": "Авто", "proxy": ""}
_dead_hosts = set()          # хосты, до которых напрямую не достучались -> сразу идём на зеркало

# Свежий пакет сертификатов (частая причина SSLError на старых системах)
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass


def to_mirror(url):
    p = urlsplit(url)
    prefix = MIRRORS.get(p.hostname)
    if prefix is None:
        return url
    return f"{BMCL}{prefix}{p.path}" + (f"?{p.query}" if p.query else "")


_orig_request = requests.sessions.Session.request


def _smart_request(self, method, url, *args, **kwargs):
    """Перехватывает ВСЕ http-запросы minecraft_launcher_lib (она работает через requests):
    подставляет прокси и при ошибке/блокировке переключается на зеркало."""
    mirrored = to_mirror(url)
    host = urlsplit(url).hostname
    mode = NET["mode"]
    if mirrored == url or mode == "Выкл":
        order = [url]
    elif mode == "Всегда" or host in _dead_hosts:
        order = [mirrored, url]
    else:
        order = [url, mirrored]

    if NET["proxy"] and not kwargs.get("proxies"):
        kwargs["proxies"] = {"http": NET["proxy"], "https": NET["proxy"]}
    kwargs["timeout"] = (10, 45)       # библиотека ставит 8 секунд: для медленного канала мало

    last = None
    for u in order:
        for _ in range(2):             # две попытки на адрес
            try:
                return _orig_request(self, method, u, *args, **kwargs)
            except (requests.exceptions.ConnectionError,   # включает SSLError
                    requests.exceptions.Timeout) as e:
                last = e
        if u == url and mirrored != url:
            _dead_hosts.add(host)
    raise last


requests.sessions.Session.request = _smart_request


def apply_java_proxy(proxy):
    """Прокси для Java-процессов (установщик Forge качает файлы сам, мимо Python)."""
    if not proxy:
        os.environ.pop("JAVA_TOOL_OPTIONS", None)
        return
    p = urlsplit(proxy)
    if not p.hostname or not p.scheme.startswith("http"):
        return
    port = p.port or 80
    os.environ["JAVA_TOOL_OPTIONS"] = (
        f"-Dhttp.proxyHost={p.hostname} -Dhttp.proxyPort={port} "
        f"-Dhttps.proxyHost={p.hostname} -Dhttps.proxyPort={port}")


def download(url, dest):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)