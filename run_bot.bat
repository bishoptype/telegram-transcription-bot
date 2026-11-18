@echo off
setlocal
cd /d "%~dp0" || exit /b 1
set "PYTHON_PATH=.venv\Scripts\python.exe"

if not exist "%PYTHON_PATH%" (
    echo Create .venv and install requirements first. See README.md.
    exit /b 1
)

"%PYTHON_PATH%" -X utf8 bot.py
exit /b %errorlevel%
