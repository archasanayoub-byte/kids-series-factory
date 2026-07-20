@echo off
cd /d "%~dp0"
python scripts\download_book2_book3_assets.py
echo.
echo Press any key to close this window...
pause >nul
