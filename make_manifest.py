#!/usr/bin/env python3
"""Генератор manifest.json для твоего хостинга.

Пример:
  python make_manifest.py ./pack --url https://example.com/pack \
      --name "My Pack" --mc 1.20.1 --loader fabric --server play.example.com:25565

Структура папки ./pack:  mods/*.jar, config/*, resourcepacks/* ...
Залей всю папку + manifest.json на любой статический хостинг (nginx, GitHub Pages, S3, свой VPS).
В лаунчере вставь ссылку https://example.com/pack/manifest.json
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

ap = argparse.ArgumentParser()
ap.add_argument("folder")
ap.add_argument("--url", required=True, help="Базовый URL папки на хостинге")
ap.add_argument("--name", default="My Pack")
ap.add_argument("--mc", required=True, help="Версия Minecraft")
ap.add_argument("--loader", default="fabric", choices=["vanilla", "fabric", "forge", "quilt"])
ap.add_argument("--server", default="")
a = ap.parse_args()

root = Path(a.folder)
files = []
for p in sorted(root.rglob("*")):
    if p.is_file() and p.name != "manifest.json":
        rel = p.relative_to(root).as_posix()
        files.append({"path": rel,
                      "url": a.url.rstrip("/") + "/" + quote(rel),
                      "sha1": hashlib.sha1(p.read_bytes()).hexdigest()})

manifest = {"name": a.name, "minecraft": a.mc, "loader": a.loader, "server": a.server, "files": files}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), "utf-8")
print(f"Готово: {len(files)} файлов -> {root / 'manifest.json'}")
