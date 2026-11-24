@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ========================================
echo        KAGUYA STUDIO V3
 echo ========================================
echo.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 studio.py
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python studio.py
  ) else (
    echo ERRO: Python 3.10 ou superior nao encontrado.
    echo Instale o Python oficial e marque Add Python to PATH.
    pause
    exit /b 1
  )
)
if errorlevel 1 (
  echo.
  echo O Studio encontrou um erro. Consulte as instrucoes em LEIA_PRIMEIRO.md
  pause
)
endlocal
