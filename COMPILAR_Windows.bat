@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR_Windows.bat primeiro.
  exit /b 1
)
set "PY=.venv\Scripts\python.exe"
"%PY%" -m pip install -r requirements-build.txt || exit /b 1
"%PY%" -m PyInstaller --clean --noconfirm WallsEC2.spec || exit /b 1
set "SMOKE=%TEMP%\WallsEC2-smoke-%RANDOM%-%RANDOM%.json"
start "" /wait "%CD%\dist\WallsEC2\WallsEC2.exe" --smoke-test "%SMOKE%"
if errorlevel 1 exit /b 1
if not exist "%SMOKE%" exit /b 1
type "%SMOKE%"
del "%SMOKE%"
echo Compilacao e teste de arranque concluidos. Nao equivalem a validacao estrutural.
exit /b 0
