@echo off
cd /d "%~dp0"
echo === Testing local upload with the fresh token.json ===
python scripts\youtube_upload.py --file videos\to_upload\ep6.mp4 --meta videos\to_upload\ep6.json --token-file token.json --privacy private
echo.
echo Press any key to close this window...
pause >nul
