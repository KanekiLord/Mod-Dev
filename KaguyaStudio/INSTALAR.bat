@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Kaguya Studio 4 - instalacao
echo ==============================================
echo   KAGUYA STUDIO 4 - instalacao local
echo   (nada e instalado fora desta pasta)
echo ==============================================
if exist "KaguyaStudio.exe" (
  echo Esta e a versao executavel: nao precisa instalar. Use INICIAR_KAGUYA_STUDIO.bat.
  pause
  exit /b 0
)
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERRO] Python 3.10+ nao encontrado.
  echo Instale em https://www.python.org/downloads/ marcando "Add python.exe to PATH" e rode de novo.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo [ERRO] E necessario Python 3.10 ou superior.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente isolado em .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERRO] Falha ao criar o ambiente .venv
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERRO] Falha ao instalar o PySide6. Verifique a conexao e rode de novo.
  pause
  exit /b 1
)
echo.
choice /C SN /M "Instalar tambem a transcricao de voz local (faster-whisper, opcional)"
if errorlevel 2 goto atalho
".venv\Scripts\python.exe" -m pip install -r requirements-voz.txt
if errorlevel 1 echo [AVISO] Voz local nao instalada; o restante do Studio funciona normalmente.
:atalho
echo.
choice /C SN /M "Criar atalho do Kaguya Studio na Area de Trabalho"
if errorlevel 2 goto fim
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\Kaguya Studio.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='-m kaguya'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0assets\branding\kaguya.ico'; $s.Save()"
:fim
echo.
echo Pronto! Abra com INICIAR_KAGUYA_STUDIO.bat (ou pelo atalho).
pause
