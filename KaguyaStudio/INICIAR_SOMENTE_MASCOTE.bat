@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 studio.py --mascote
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python studio.py --mascote
  ) else (
    echo Python 3.10 ou superior nao encontrado.
    pause
    exit /b 1
  )
)
if errorlevel 1 pause
endlocal
