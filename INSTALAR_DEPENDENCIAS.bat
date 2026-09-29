@echo off
setlocal
cd /d "%~dp0"

echo ================================================
echo InjectFlow v3.0 - Dependencias de codigo fuente
echo ================================================
echo.

echo Este instalador solo es necesario para ejecutar el CODIGO FUENTE.
echo La distribucion final con InjectFlow.exe no requiere Python.
echo.

set "PY="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.14 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=py -3.14"
)
if not defined PY set "PY=python"

%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: No fue posible instalar las dependencias.
    pause
    exit /b 1
)

%PY% -c "import webview, importlib.metadata as m; print('PyWebView:', m.version('pywebview'))"
if errorlevel 1 (
    echo ERROR: PyWebView no pudo importarse.
    pause
    exit /b 1
)

echo.
echo Dependencias instaladas correctamente.
echo Ejecutar codigo fuente con: py -3.14 launcher_web.py
pause
endlocal
