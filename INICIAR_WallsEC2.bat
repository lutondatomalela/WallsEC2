@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Execute primeiro INSTALAR_Windows.bat.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" WallsEC2.py
if errorlevel 1 pause
