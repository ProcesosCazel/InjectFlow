@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "RELEASE_NAME=AutomatizacionParametros_v2.0"
set "BUILD_VENV=.venv_build"
set "BUILD_WORK=build_temp"
set "BUILD_DIST=dist_build"
set "FINAL_DIST=dist\%RELEASE_NAME%"

echo ==========================================================
echo InjectFlow v2.0 - Construccion Release Candidate
echo ==========================================================
echo.

set "BASE_PY="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.14 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3.14"
)

if not defined BASE_PY (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] No se encontro Python 3.14.
        pause
        exit /b 1
    )
    set "BASE_PY=python"
)

%BASE_PY% -c "import sys,struct; assert sys.version_info[:2] >= (3,14), 'Se requiere Python 3.14 o superior'; assert struct.calcsize('P')*8 == 64, 'Se requiere Python 64 bits'; print('Python:', sys.version.split()[0], '64-bit')"
if errorlevel 1 goto :error

echo.
echo [1/8] Limpiando entorno de build anterior...
if exist "%BUILD_VENV%" rmdir /s /q "%BUILD_VENV%"
if exist "%BUILD_WORK%" rmdir /s /q "%BUILD_WORK%"
if exist "%BUILD_DIST%" rmdir /s /q "%BUILD_DIST%"
if exist "%FINAL_DIST%" rmdir /s /q "%FINAL_DIST%"
if exist "dist\%RELEASE_NAME%.zip" del /q "dist\%RELEASE_NAME%.zip"

if not exist dist mkdir dist

echo.
echo [2/8] Creando entorno Python aislado...
%BASE_PY% -m venv "%BUILD_VENV%"
if errorlevel 1 goto :error
set "PY=%CD%\%BUILD_VENV%\Scripts\python.exe"

"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%PY%" -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

echo.
echo [3/8] Ejecutando regresion automatizada...
"%PY%" -m pytest -q
if errorlevel 1 goto :error

echo.
echo [4/8] Validando entorno de release...
"%PY%" release_tools\preflight_release.py
if errorlevel 1 goto :error

echo.
echo [5/8] Construyendo InjectFlow.exe con PyInstaller...
"%PY%" -m PyInstaller --noconfirm --clean --log-level WARN --distpath "%BUILD_DIST%" --workpath "%BUILD_WORK%" InjectFlow.spec
if errorlevel 1 goto :error

if not exist "%BUILD_DIST%\InjectFlow\InjectFlow.exe" (
    echo [ERROR] PyInstaller no genero InjectFlow.exe.
    goto :error
)

echo.
echo [6/8] Preparando distribucion %RELEASE_NAME%...
move "%BUILD_DIST%\InjectFlow" "%FINAL_DIST%" >nul
if errorlevel 1 goto :error

mkdir "%FINAL_DIST%\data" >nul 2>&1
mkdir "%FINAL_DIST%\plantillas" >nul 2>&1
mkdir "%FINAL_DIST%\input" >nul 2>&1
mkdir "%FINAL_DIST%\output" >nul 2>&1

copy /y "data\Data.xlsx" "%FINAL_DIST%\data\Data.xlsx" >nul
if errorlevel 1 goto :error
copy /y "data\Mapeo.xlsx" "%FINAL_DIST%\data\Mapeo.xlsx" >nul
if errorlevel 1 goto :error
copy /y "plantillas\Haitian Zeres Gen V.xlsx" "%FINAL_DIST%\plantillas\Haitian Zeres Gen V.xlsx" >nul
if errorlevel 1 goto :error
copy /y "plantillas\Haitian Zeres Gen III.xlsx" "%FINAL_DIST%\plantillas\Haitian Zeres Gen III.xlsx" >nul
if errorlevel 1 goto :error

xcopy /e /i /y "web" "%FINAL_DIST%\web" >nul
if errorlevel 1 goto :error

copy /y "VERSION.txt" "%FINAL_DIST%\VERSION.txt" >nul
copy /y "docs\RELEASE_NOTES_V2.0.txt" "%FINAL_DIST%\LEEME_RELEASE.txt" >nul

echo.
echo [7/8] Verificando distribucion...
"%PY%" release_tools\verify_distribution.py "%FINAL_DIST%"
if errorlevel 1 goto :error

echo.
echo [8/8] Creando ZIP final...
"%PY%" -c "import shutil; shutil.make_archive(r'dist\%RELEASE_NAME%', 'zip', root_dir='dist', base_dir=r'%RELEASE_NAME%')"
if errorlevel 1 goto :error

if exist "%BUILD_WORK%" rmdir /s /q "%BUILD_WORK%"
if exist "%BUILD_DIST%" rmdir /s /q "%BUILD_DIST%"
if exist "%BUILD_VENV%" rmdir /s /q "%BUILD_VENV%"

echo.
echo ==========================================================
echo RELEASE CANDIDATE CONSTRUIDA CORRECTAMENTE
echo ==========================================================
echo EXE: %FINAL_DIST%\InjectFlow.exe
echo ZIP: dist\%RELEASE_NAME%.zip
echo.
echo Siguiente paso: ejecutar el EXE y realizar el smoke test de release.
pause
exit /b 0

:error
echo.
echo ==========================================================
echo [ERROR] La construccion de la release no fue completada.
echo ==========================================================
echo Revise los mensajes anteriores.
pause
exit /b 1
