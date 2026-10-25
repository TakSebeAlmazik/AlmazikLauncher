@echo off
REM Build BlockLauncher.exe (run this on Windows, Python 3.9+ installed)
cd /d "%~dp0"
py -m pip install --upgrade pip
py -m pip install pyinstaller customtkinter minecraft-launcher-lib requests certifi pillow
py -m PyInstaller --noconfirm --clean --onefile --windowed --name BlockLauncher ^
  --icon icon.ico --add-data "icon.ico;." ^
  --collect-all customtkinter --collect-all minecraft_launcher_lib --collect-data certifi ^
  launcher.py
echo.
echo Done: dist\BlockLauncher.exe
pause
