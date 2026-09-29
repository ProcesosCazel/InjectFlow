@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title InjectFlow v3.0 - Crear EXE

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "BUILD_VENV=.venv-build"
set "APP_DIST=dist\InjectFlow"

echo.
echo ============================================================
echo   InjectFlow v3.0 - Build Windows
echo ============================================================
echo.

if not exist "launcher_web.py" goto :missing_project
if not exist "InjectFlow.spec" goto :missing_project
if not exist "data\Data.xlsx" goto :missing_project
if not exist "data\Mapeo.xlsx" goto :missing_project
if not exist "data\Moldes.xlsx" goto :missing_project
if not exist "plantillas\Haitian Zeres Gen V.xlsx" goto :missing_project
if not exist "plantillas\Haitian Zeres Gen III_500.xlsx" goto :missing_project
if not exist "plantillas\Haitian Zeres Gen III_800.xlsx" goto :missing_project
if not exist "plantillas\Haitian Zeres Gen III_1080.xlsx" goto :missing_project
if not exist "web\index.html" goto :missing_project

where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro el Python Launcher ^(py.exe^).
    echo Instala Python 3.14 de 64 bits y vuelve a ejecutar este archivo.
    goto :fail
)

py -3.14 -c "import sys; assert sys.maxsize == 9223372036854775807; print(sys.version)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro Python 3.14 de 64 bits.
    echo InjectFlow v3.0 se construye con Python 3.14 x64.
    goto :fail
)

if not exist "%BUILD_VENV%\Scripts\python.exe" (
    echo [1/7] Creando entorno limpio de build...
    py -3.14 -m venv "%BUILD_VENV%"
    if errorlevel 1 goto :fail
) else (
    echo [1/7] Entorno de build existente: %BUILD_VENV%
)

set "PY=%BUILD_VENV%\Scripts\python.exe"

echo [2/7] Instalando dependencias...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PY%" -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :fail

REM Verificacion temprana de dependencia COM requerida por Excel/pywin32.
"%PY%" -c "import win32timezone" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pywin32 no expone win32timezone en el entorno de build.
    echo Revisa la instalacion de pywin32 antes de continuar.
    goto :fail
)

echo [3/7] Ejecutando regresion...
"%PY%" -m pytest -q
if errorlevel 1 (
    echo [ERROR] La regresion fallo. No se generara el EXE.
    goto :fail
)

echo [4/7] Limpiando build anterior...
if exist "build\InjectFlow" rmdir /s /q "build\InjectFlow"
if exist "%APP_DIST%" rmdir /s /q "%APP_DIST%"

echo [5/7] Generando InjectFlow.exe...
"%PY%" -m PyInstaller --noconfirm --clean InjectFlow.spec
if errorlevel 1 goto :fail

if not exist "%APP_DIST%\InjectFlow.exe" (
    echo [ERROR] PyInstaller termino sin crear InjectFlow.exe.
    goto :fail
)

REM Confirma que win32timezone quedo dentro del archivo PYZ generado.
if not exist "build\InjectFlow\PYZ-00.pyz" (
    echo [ERROR] No se encontro el archivo PYZ del build para validacion.
    goto :fail
)
"%BUILD_VENV%\Scripts\pyi-archive_viewer.exe" -l "build\InjectFlow\PYZ-00.pyz" | findstr /I /C:"win32timezone" >nul
if errorlevel 1 (
    echo [ERROR] El build no contiene win32timezone. No se distribuira este EXE.
    goto :fail
)

echo [OK] Dependencia COM win32timezone incluida en el ejecutable.

echo [6/7] Copiando archivos editables de produccion...
mkdir "%APP_DIST%\data" >nul 2>&1
copy /y "data\Data.xlsx" "%APP_DIST%\data\Data.xlsx" >nul
if errorlevel 1 goto :fail
copy /y "data\Mapeo.xlsx" "%APP_DIST%\data\Mapeo.xlsx" >nul
if errorlevel 1 goto :fail
copy /y "data\Moldes.xlsx" "%APP_DIST%\data\Moldes.xlsx" >nul
if errorlevel 1 goto :fail
copy /y "VERSION.txt" "%APP_DIST%\VERSION.txt" >nul
if errorlevel 1 goto :fail
copy /y "DEVELOPMENT_NOTES_v3.0.txt" "%APP_DIST%\DEVELOPMENT_NOTES_v3.0.txt" >nul
if errorlevel 1 goto :fail

robocopy "plantillas" "%APP_DIST%\plantillas" *.xlsx /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
robocopy "web" "%APP_DIST%\web" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail

mkdir "%APP_DIST%\input" >nul 2>&1
mkdir "%APP_DIST%\output" >nul 2>&1

REM Historial.csv no se copia: una instalacion nueva inicia con historial vacio.
REM InjectFlow lo crea automaticamente en la primera generacion exitosa.

echo [7/7] Verificando estructura final...
if not exist "%APP_DIST%\_internal" goto :invalid_dist
if not exist "%APP_DIST%\data\Data.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\data\Mapeo.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\data\Moldes.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\VERSION.txt" goto :invalid_dist
if not exist "%APP_DIST%\DEVELOPMENT_NOTES_v3.0.txt" goto :invalid_dist
if not exist "%APP_DIST%\web\index.html" goto :invalid_dist
if not exist "%APP_DIST%\web\js\main.js" goto :invalid_dist
if not exist "%APP_DIST%\web\css\styles.css" goto :invalid_dist
if not exist "%APP_DIST%\plantillas\Haitian Zeres Gen V.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\plantillas\Haitian Zeres Gen III_500.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\plantillas\Haitian Zeres Gen III_800.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\plantillas\Haitian Zeres Gen III_1080.xlsx" goto :invalid_dist

echo.
echo ============================================================
echo   BUILD COMPLETADO CORRECTAMENTE
echo ============================================================
echo.
echo Ejecutable:
echo   %CD%\%APP_DIST%\InjectFlow.exe
echo.
echo Para distribuir InjectFlow, copia la carpeta completa:
echo   %CD%\%APP_DIST%
echo.
echo No copies solamente InjectFlow.exe: necesita _internal, data,
echo plantillas y web en la misma carpeta de distribucion.
echo.
pause
exit /b 0

:missing_project
echo [ERROR] Faltan archivos maestros requeridos para construir InjectFlow.
goto :fail

:invalid_dist
echo [ERROR] El EXE fue creado, pero la estructura final quedo incompleta.
goto :fail

:fail
echo.
echo ============================================================
echo   BUILD CANCELADO / CON ERROR
echo ============================================================
echo Revisa el mensaje mostrado arriba. No uses el contenido de dist.
echo.
pause
exit /b 1
