@echo off
cd /d "%~dp0"
if exist "KaguyaStudio.exe" (
  start "" "KaguyaStudio.exe" %*
  exit /b 0
)
if not exist ".venv\Scripts\pythonw.exe" (
  echo Primeiro execute INSTALAR.bat
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m kaguya %*
