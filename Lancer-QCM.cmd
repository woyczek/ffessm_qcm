@echo off
setlocal EnableExtensions
chcp 65001 >nul
rem PUSHD attribue temporairement une lettre aux chemins UNC.
pushd "%~dp0"
if errorlevel 1 (
  echo Impossible d'ouvrir le dossier du QCM : "%~dp0"
  pause
  exit /b 1
)
if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" (
  "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" app\serve.py %*
) else (
  py -3 app\serve.py %*
)
set "qcm_exit=%errorlevel%"
popd
if not "%qcm_exit%"=="0" (
  echo.
  echo Si Python est absent, installe Python 3.10 ou plus recent depuis python.org.
  pause
)
exit /b %qcm_exit%
