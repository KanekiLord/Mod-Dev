@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primeiro execute INSTALAR.bat
  pause
  exit /b 1
)
echo Executando os testes automatizados (CLIs simuladas; nao usa suas assinaturas)...
set QT_QPA_PLATFORM=offscreen
".venv\Scripts\python.exe" -m unittest discover -s tests -t . -v
pause
