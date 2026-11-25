@echo off
setlocal EnableExtensions
chcp 65001 >nul
pushd "%~dp0"
if errorlevel 1 (
  echo Impossible d'ouvrir le dossier du QCM : "%~dp0"
  pause
  exit /b 1
)
if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" (
  "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" app\cli.py %*
) else (
  py -3 app\cli.py %*
)
set "qcm_exit=%errorlevel%"
popd
if not "%qcm_exit%"=="0" pause
exit /b %qcm_exit%
