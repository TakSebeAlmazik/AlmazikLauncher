"""Скины: библиотека PNG, превью (Pillow) и локальное применение через ресурспак."""
import io
import json
import re
import uuid
import zipfile
from pathlib import Path

import requests
from PIL import Image

ROOT = Path.home() / ".mclauncher"
SKINS = ROOT / "skins"
INDEX = SKINS / "index.json"
PACK = "AlmazikSkin.zip"
LEGACY = "BlockLauncherSkin.zip"          # старое имя пака (до переименования лаунчера)
NAMES = ["steve", "alex", "ari", "efe", "kai", "makena", "noor", "sunny", "zuri"]
# (минор, патч, pack_format) для версий 1.x
FORMATS = [(8, 0, 1), (9, 0, 2), (11, 0, 3), (13, 0, 4), (15, 0, 5), (16, 2, 6), (17, 0, 7), (18, 0, 8),
           (19, 0, 9), (19, 3, 12), (19, 4, 13), (20, 0, 15), (20, 2, 18), (20, 3, 22), (20, 5, 32),
           (21, 0, 34), (21, 2, 42), (21, 4, 46), (21, 5, 55), (21, 6, 63), (21, 7, 64)]
RES, TR = Image.Resampling, Image.Transpose

# грани руки/ноги внутри блока 16x16 (широкий вариант) и зеркальные пары для старых скинов 64x32
_BLOCK = dict(top=(4, 0, 8, 4), bottom=(8, 0, 12, 4), rs=(0, 4, 4, 16), front=(4, 4, 8, 16),
              ls=(8, 4, 12, 16), back=(12, 4, 16, 16))
_SLIM = dict(top=(4, 0, 7, 4), bottom=(7, 0, 10, 4), rs=(0, 4, 4, 16), front=(4, 4, 7, 16),
             ls=(7, 4, 11, 16), back=(11, 4, 14, 16))
_MIRROR = dict(top="top", bottom="bottom", rs="ls", front="front", ls="rs", back="back")


# ---------------- библиотека ----------------
def load_index():
    try:
        return json.loads(INDEX.read_text("utf-8"))
    except Exception:
        return {}


def _save(idx):
    SKINS.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=1), "utf-8")


def normalize(img):
    img = img.convert("RGBA")
    if img.width == img.height and img.width > 64 and img.width % 64 == 0:
        img = img.resize((64, 64), RES.NEAREST)
    if img.size == (64, 32):                       # старый формат: достраиваем левую руку и ногу
        new = Image.new("RGBA", (64, 64))
        new.paste(img, (0, 0))
        for (sx, sy), (dx, dy) in (((0, 16), (16, 48)), ((40, 16), (32, 48))):
            for k, b in _BLOCK.items():
                s = _BLOCK[_MIRROR[k]]
                face = img.crop((sx + s[0], sy + s[1], sx + s[2], sy + s[3])).transpose(TR.FLIP_LEFT_RIGHT)
                new.paste(face, (dx + b[0], dy + b[1]))
        img = new
    if img.size != (64, 64):
        raise ValueError("Нужен PNG-скин размером 64×64 или 64×32")
    return img


def detect_slim(img):
    """У тонких рук (Alex) последний столбец текстуры руки пустой."""
    return all(img.getpixel((55, y))[3] == 0 for y in range(20, 32))


def add_skin(name, src):
    img = normalize(Image.open(io.BytesIO(src) if isinstance(src, bytes) else src))
    sid = uuid.uuid4().hex[:8]
    SKINS.mkdir(parents=True, exist_ok=True)
    img.save(SKINS / f"{sid}.png")
    idx = load_index()
    idx[sid] = {"name": name[:24] or "Скин", "slim": detect_slim(img)}
    _save(idx)
    return sid


def get_image(sid):
    return Image.open(SKINS / f"{sid}.png").convert("RGBA")


def set_slim(sid, value):
    idx = load_index()
    if sid in idx:
        idx[sid]["slim"] = value
        _save(idx)


def delete_skin(sid):
    idx = load_index()
    idx.pop(sid, None)
    _save(idx)
    (SKINS / f"{sid}.png").unlink(missing_ok=True)


def fetch_by_nick(nick):
    nick = re.sub(r"\W", "", nick)[:16]
    if not nick:
        raise ValueError("Введи ник")
    for url in (f"https://minotar.net/skin/{nick}", f"http://skinsystem.ely.by/skins/{nick}.png"):
        try:
            r = requests.get(url, timeout=15)
            if r.ok and r.content[:4] == b"\x89PNG":
                return r.content
        except requests.RequestException:
            pass
    raise RuntimeError(f"Скин «{nick}» не найден или сервис недоступен")


# ---------------- превью ----------------
def render_preview(img, slim=False, scale=4):
    """Вид спереди и сзади (с внешним слоем), увеличенный без размытия."""
    aw = 3 if slim else 4

    def view(back):
        c = Image.new("RGBA", (16, 32))

        def put(parts, x, y):
            for box in parts:
                c.alpha_composite(img.crop(box), (x, y))
        if back:
            head, body = ((24, 8, 32, 16), (56, 8, 64, 16)), ((32, 20, 40, 32), (32, 36, 40, 48))
            xr, xl, xo = (51 if slim else 52), (43 if slim else 44), (59 if slim else 60)
            ra = ((xr, 20, xr + aw, 32), (xr, 36, xr + aw, 48))
            la = ((xl, 52, xl + aw, 64), (xo, 52, xo + aw, 64))
            rl, ll = ((12, 20, 16, 32), (12, 36, 16, 48)), ((28, 52, 32, 64), (12, 52, 16, 64))
        else:
            head, body = ((8, 8, 16, 16), (40, 8, 48, 16)), ((20, 20, 28, 32), (20, 36, 28, 48))
            ra = ((44, 20, 44 + aw, 32), (44, 36, 44 + aw, 48))
            la = ((36, 52, 36 + aw, 64), (52, 52, 52 + aw, 64))
            rl, ll = ((4, 20, 8, 32), (4, 36, 8, 48)), ((20, 52, 24, 64), (4, 52, 8, 64))
        l_arm, r_arm = (la, ra) if back else (ra, la)       # как на экране: слева / справа
        l_leg, r_leg = (ll, rl) if back else (rl, ll)
        put(head, 4, 0), put(body, 4, 8)
        put(l_arm, 4 - aw, 8), put(r_arm, 12, 8)
        put(l_leg, 4, 20), put(r_leg, 8, 20)
        return c

    out = Image.new("RGBA", (34, 32))
    out.alpha_composite(view(False), (0, 0))
    out.alpha_composite(view(True), (18, 0))
    return out.resize((34 * scale, 32 * scale), RES.NEAREST)


# ---------------- применение в игре ----------------
def convert_arms(img, to_slim):
    """Перерисовывает руки под другую модель (широкие <-> тонкие)."""
    src, dst = (_BLOCK, _SLIM) if to_slim else (_SLIM, _BLOCK)
    out = img.copy()
    for ox, oy in ((40, 16), (40, 32), (32, 48), (48, 48)):
        faces = {}
        for k, b in src.items():
            d = dst[k]
            faces[k] = img.crop((ox + b[0], oy + b[1], ox + b[2], oy + b[3])).resize(
                (d[2] - d[0], d[3] - d[1]), RES.BOX if to_slim else RES.NEAREST)
        out.paste((0, 0, 0, 0), (ox, oy, ox + 16, oy + 16))
        for k, face in faces.items():
            out.paste(face, (ox + dst[k][0], oy + dst[k][1]))
    return out


def mc_ver(mc):
    m = re.match(r"1\.(\d+)(?:\.(\d+))?", mc)
    return (int(m[1]), int(m[2] or 0)) if m else None      # None = снапшот / новая схема версий


def pack_format(mc):
    v = mc_ver(mc)
    if not v:
        return FORMATS[-1][2]
    fmt = FORMATS[0][2]
    for mi, pa, f in FORMATS:
        if (mi, pa) <= v:
            fmt = f
    return fmt


def real_format(mc):
    """Формат ресурспаков из самого клиента игры: ('old', N) / ('new', N) или None."""
    try:
        with zipfile.ZipFile(ROOT / "minecraft" / "versions" / mc / f"{mc}.jar") as z:
            pv = json.loads(z.read("version.json")).get("pack_version")
        if isinstance(pv, dict):
            if "resource_major" in pv:
                return "new", pv["resource_major"]
            return "old", pv.get("resource") or pv.get("data")
        if isinstance(pv, int):
            return "old", pv
    except Exception:
        pass
    return None


def pack_meta(mc):
    """Содержимое pack.mcmeta. Версии с форматом 65+ (1.21.9+, 26.x) требуют min_format/max_format."""
    v, fmt = mc_ver(mc), real_format(mc)
    kind = fmt[0] if fmt else ("new" if v is None or v >= (21, 9) else "old")
    desc = "AlmazikLauncher skin"
    if kind == "new":
        return {"min_format": 65, "max_format": [1000, 0], "description": desc}   # любая новая версия
    n = fmt[1] if fmt else pack_format(mc)
    return {"pack_format": n, "supported_formats": [1, 64], "description": desc}


def build_pack(sid, mc, dest):
    img, slim = get_image(sid), load_index()[sid]["slim"]
    wide_tex = convert_arms(img, False) if slim else img
    slim_tex = img if slim else convert_arms(img, True)

    def png(im):
        b = io.BytesIO()
        im.save(b, "PNG")
        return b.getvalue()
    meta = {"pack": pack_meta(mc)}
    base = "assets/minecraft/textures/entity/"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.mcmeta", json.dumps(meta))
        z.writestr(base + "steve.png", png(wide_tex))               # версии до 1.19.2
        z.writestr(base + "alex.png", png(slim_tex))
        for n in NAMES:                                              # 1.19.3 и новее
            z.writestr(f"{base}player/wide/{n}.png", png(wide_tex))
            z.writestr(f"{base}player/slim/{n}.png", png(slim_tex))


def _jlist(line):
    try:
        return json.loads(line.split(":", 1)[1])
    except Exception:
        return []


def _set_enabled(game_dir, mc, enabled):
    opt = Path(game_dir) / "options.txt"
    if not opt.exists() and not enabled:
        return
    v = mc_ver(mc)
    modern = v is None or v[0] >= 13                    # с 1.13 имена вида "file/имя.zip"
    name = ("file/" if modern else "") + PACK
    lines = opt.read_text("utf-8").splitlines() if opt.exists() else []
    cur, inc, out = None, [], []
    for ln in lines:
        if ln.startswith("resourcePacks:"):
            cur = _jlist(ln)
        elif ln.startswith("incompatibleResourcePacks:"):
            inc = _jlist(ln)
        else:
            out.append(ln)
    if cur is None:
        cur = ["vanilla"] if modern else []
    cur = [p for p in cur if not p.endswith((PACK, LEGACY))]
    inc = [p for p in inc if not p.endswith((PACK, LEGACY))]
    if enabled:
        cur.append(name)     # в incompatibleResourcePacks НЕ добавляем: для совместимого пака игра
                             # тогда снимает его с выбора при старте
    out.append("resourcePacks:" + json.dumps(cur, separators=(",", ":")))
    out.append("incompatibleResourcePacks:" + json.dumps(inc, separators=(",", ":")))
    opt.write_text("\n".join(out) + "\n", "utf-8")


def apply(sid, game_dir, mc):
    """Включает выбранный скин в папке игры (или убирает, если sid пустой)."""
    rp = Path(game_dir) / "resourcepacks"
    pack = rp / PACK
    (rp / LEGACY).unlink(missing_ok=True)
    if sid and sid in load_index():
        rp.mkdir(parents=True, exist_ok=True)
        build_pack(sid, mc, pack)
        _set_enabled(game_dir, mc, True)
    elif pack.exists():
        pack.unlink()
        _set_enabled(game_dir, mc, False)