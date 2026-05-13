@echo off
cd /d "%~dp0"

if not exist ".env" (
    echo.
    echo [!] .env file not found.
    echo     Copy .env.example to .env and fill in your NAVER API keys.
    echo.
    pause
    exit /b 1
)

echo.
echo Starting app... a browser window will open shortly.
echo To stop the app, press Ctrl+C in this window.
echo.
".venv\Scripts\streamlit.exe" run app.py
pause
