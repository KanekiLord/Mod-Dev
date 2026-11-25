@echo off
rem Abre o Studio com dados temporarios e CLIs SIMULADAS (nao usa suas contas nem seus arquivos).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo A demonstracao precisa da instalacao com Python: execute INSTALAR.bat
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m kaguya --demo
