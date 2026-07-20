@echo off
cd /d "%~dp0"
python scripts\download_coloring_book_assets.py
echo.
echo Press any key to close this window...
pause >nul
