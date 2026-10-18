@echo off
rem Builds dist\VLC Reskin\VLC Reskin.exe and puts a shortcut on the Desktop.
rem Run it again after changing the code to rebuild the app.
setlocal
cd /d "%~dp0"
rem The Python environment keeps its original folder name.
set "VENV=%LOCALAPPDATA%\vlc-redesign\venv"

if not exist "%VENV%\Scripts\python.exe" (
    echo Setting up Python environment, this takes a minute the first time...
    where py >nul 2>nul && (py -3.12 -m venv "%VENV%") || ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m venv "%VENV%")
)
"%VENV%\Scripts\python.exe" -m pip install -q PySide6 python-vlc pyinstaller

echo Building VLC Reskin.exe ...
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --log-level WARN ^
    --distpath dist --workpath build "VLC Reskin.spec" || goto :fail

echo Creating Desktop shortcut ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\VLC Reskin.lnk');" ^
  "$s.TargetPath='%~dp0dist\VLC Reskin\VLC Reskin.exe'; $s.WorkingDirectory='%~dp0dist\VLC Reskin';" ^
  "$s.IconLocation='%~dp0dist\VLC Reskin\VLC Reskin.exe,0'; $s.Description='VLC Reskin (unofficial reskin of VLC)'; $s.Save()"

echo.
echo Done: dist\VLC Reskin\VLC Reskin.exe (and a "VLC Reskin" shortcut on your Desktop)
pause
exit /b 0

:fail
echo Build failed - see the messages above.
pause
exit /b 1
