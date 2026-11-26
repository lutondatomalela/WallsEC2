@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "PYTHON=python") else (set "PYTHON=py -3")
echo A criar o ambiente Python do WallsEC2...
%PYTHON% -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Instalacao concluida. Execute INICIAR_WallsEC2.bat.
pause
exit /b 0
:fail
echo Falha na instalacao. Confirme Python 3.10 ou superior e acesso a Internet.
pause
exit /b 1
