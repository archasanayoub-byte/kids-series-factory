@echo off
cd /d "%~dp0"
python scripts\generate_token.py --client-secret "client_secret_442575586453-s5cbc0pku9ct3jvfv0vf2p4386i1dhcc.apps.googleusercontent.com.json"
echo.
echo Press any key to close this window...
pause >nul
