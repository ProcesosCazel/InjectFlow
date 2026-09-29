@echo off
setlocal
title InjectFlow v3.0 - Release 3.0

REM ============================================================
REM InjectFlow v3.0 - Release 3.0
REM Lanzador principal del proyecto.
REM ============================================================

cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo.
echo ============================================================
echo   InjectFlow v3.0 - Release 3.0
echo ============================================================
echo   Proyecto: %CD%
echo.

if not exist "launcher_web.py" (
    echo [ERROR] No se encontro launcher_web.py.
    echo Coloca este archivo en la raiz de AutomatizacionParametros_v3.0.
    echo.
    pause
    exit /b 1
)

set "PY_CMD="

if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
    echo [OK] Entorno detectado: .venv
    goto :python_ready
)

if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
    echo [OK] Entorno detectado: venv
    goto :python_ready
)

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=py -3"
    echo [OK] Python detectado mediante py launcher
    goto :python_ready
)

where python >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=python"
    echo [OK] Python detectado mediante PATH
    goto :python_ready
)

echo.
echo [ERROR] No se encontro Python.
echo Ejecuta INSTALAR_DEPENDENCIAS.bat despues de instalar Python.
echo.
pause
exit /b 1

:python_ready
echo.
echo Iniciando InjectFlow...
echo ------------------------------------------------------------
echo.

%PY_CMD% launcher_web.py
set "APP_EXIT=%errorlevel%"

if not "%APP_EXIT%"=="0" (
    echo.
    echo ============================================================
    echo [ERROR] InjectFlow termino con codigo %APP_EXIT%.
    echo Revisa el mensaje o traceback mostrado arriba.
    echo ============================================================
    echo.
    pause
    exit /b %APP_EXIT%
)

echo.
echo InjectFlow se cerro correctamente.
timeout /t 2 /nobreak >nul

endlocal
exit /b 0
