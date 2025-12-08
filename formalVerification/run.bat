@echo off
cd /d "%~dp0"
echo Starting Formal Verification Engine...
echo.
echo Starting Flask backend server...
start "Flask Backend" cmd /k "cd /d %~dp0 && python app.py"
timeout /t 5 /nobreak >nul
echo.
echo Starting Tkinter frontend...
start "Tkinter Frontend" cmd /k "cd /d %~dp0 && python ui.py"
echo.
echo Both applications are starting in separate windows.
echo Make sure the backend window shows "Server running on: http://127.0.0.1:5000"
echo Close this window when done.

