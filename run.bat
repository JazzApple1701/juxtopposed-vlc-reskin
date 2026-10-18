@echo off
rem Launches VLC Reskin from source. First run creates a Python environment
rem (kept at a short path because PySide6 fails to load from very long ones).
setlocal
set "VENV=%LOCALAPPDATA%\vlc-redesign\venv"

if not exist "%VENV%\Scripts\pythonw.exe" (
    echo Setting up Python environment, this takes a minute the first time...
    where py >nul 2>nul && (py -3.12 -m venv "%VENV%") || ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m venv "%VENV%")
    "%VENV%\Scripts\python.exe" -m pip install -q PySide6 python-vlc
)

start "" "%VENV%\Scripts\pythonw.exe" "%~dp0player\main.py" %*
