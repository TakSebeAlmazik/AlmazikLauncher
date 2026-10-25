"""Диагностика AlmazikLauncher.  Запусти:  python diagnose.py   и пришли весь вывод целиком."""
import importlib
import pathlib
import platform
import sys
import traceback

here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here))
print("Python:", sys.version.split()[0], "|", platform.platform())
print("Папка:", here)

print("\n== Файлы ==")
for f in ("launcher.py", "core.py", "netlayer.py", "skins.py", "auth.py", "icon.ico"):
    p = here / f
    print(("OK   " if p.exists() else "НЕТ  ") + f, f"({p.stat().st_size} байт)" if p.exists() else "<- этого файла нет рядом с launcher.py")

print("\n== Версии файлов (по характерным признакам) ==")
marks = {"launcher.py": ["import auth", "_auth_screen", "report_callback_exception", "apply_theme"],
         "core.py": ['"theme"', "jvm_args", "_find_installed"], "skins.py": ["pack_meta"], "netlayer.py": ["_smart_request"]}
for f, words in marks.items():
    p = here / f
    text = p.read_text("utf-8", "ignore") if p.exists() else ""
    for w in words:
        print(f"  {f:13} {w:26}", "есть" if w in text else "НЕТ  <- старая версия файла, замени его")

print("\n== Пакеты ==")
for mod in ("customtkinter", "minecraft_launcher_lib", "requests", "PIL", "certifi"):
    try:
        m = importlib.import_module(mod)
        print(f"OK   {mod:24}", getattr(m, "__version__", getattr(m, "version", "")))
    except Exception as e:
        print(f"НЕТ  {mod:24} {e}  <- python -m pip install -r requirements.txt")

print("\n== Импорт модулей лаунчера ==")
for mod in ("netlayer", "auth", "skins", "core", "launcher"):
    try:
        importlib.import_module(mod)
        print("OK  ", mod)
    except Exception:
        print("ОШИБКА при импорте", mod)
        traceback.print_exc()

print("\n== Пробный запуск окна (закроется само через 2 секунды) ==")
try:
    import launcher
    app = launcher.App()
    app.after(2000, app.destroy)
    app.mainloop()
    print("Окно открылось и закрылось без ошибок.")
except Exception:
    print("ОШИБКА при запуске окна:")
    traceback.print_exc()

log = pathlib.Path.home() / ".mclauncher" / "crash.log"
print("\n== crash.log ==")
if log.exists():
    print("\n".join(log.read_text("utf-8", "ignore").splitlines()[-25:]))
else:
    print("(файла нет: ошибок в обработчиках окна ещё не было)")
