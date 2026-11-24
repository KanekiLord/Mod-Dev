@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Executando testes automatizados, sem usar Codex ou Claude reais...
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m unittest discover -s tests -v
) else (
  python -m unittest discover -s tests -v
)
pause
endlocal
