@echo off
cd /d "%~dp0"
python scripts\auto_fetch_and_push.py
echo.
echo Press any key to close this window...
pause >nul
