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

REM ============================================================
REM 0. Validar archivos maestros del proyecto
REM ============================================================
if not exist "launcher_web.py" goto :missing_project
if not exist "InjectFlow.spec" goto :missing_project
if not exist "requirements.txt" goto :missing_project
if not exist "requirements-build.txt" goto :missing_project
if not exist "VERSION.txt" goto :missing_project
if not exist "RELEASE_3.0.txt" goto :missing_project

if not exist "data\Data.xlsx" goto :missing_project
if not exist "data\Mapeo.xlsx" goto :missing_project
if not exist "data\Moldes.xlsx" goto :missing_project

if not exist "plantillas\Haitian Zeres Gen V.xlsx" goto :missing_project
if not exist "plantillas\Haitian Zeres Gen III_500.xlsx" goto :missing_project
if not exist "plantillas\Haitian Zeres Gen III_800.xlsx" goto :missing_project
if not exist "plantillas\Haitian Zeres Gen III_1080.xlsx" goto :missing_project
if not exist "plantillas\Haitian Jupiter TwoShot_1080.xlsx" goto :missing_project

if not exist "web\index.html" goto :missing_project
if not exist "web\js\main.js" goto :missing_project
if not exist "web\css\styles.css" goto :missing_project
if not exist "web\assets\LogoCazel.webp" goto :missing_project

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

REM ============================================================
REM 1. Entorno limpio de build
REM ============================================================
if not exist "%BUILD_VENV%\Scripts\python.exe" (
    echo [1/8] Creando entorno limpio de build...
    py -3.14 -m venv "%BUILD_VENV%"
    if errorlevel 1 goto :fail
) else (
    echo [1/8] Entorno de build existente: %BUILD_VENV%
)

set "PY=%BUILD_VENV%\Scripts\python.exe"

REM ============================================================
REM 2. Dependencias
REM ============================================================
echo [2/8] Instalando dependencias...
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

REM ============================================================
REM 3. Regresion
REM ============================================================
echo [3/8] Ejecutando regresion...
"%PY%" -m pytest -q
if errorlevel 1 (
    echo [ERROR] La regresion fallo. No se generara el EXE.
    goto :fail
)

REM ============================================================
REM 4. Limpiar build/dist anterior
REM ============================================================
echo [4/8] Limpiando build anterior...
if exist "build\InjectFlow" rmdir /s /q "build\InjectFlow"
if exist "%APP_DIST%" rmdir /s /q "%APP_DIST%"

REM ============================================================
REM 5. PyInstaller
REM ============================================================
echo [5/8] Generando InjectFlow.exe...
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

REM ============================================================
REM 6. Copiar recursos externos editables de produccion
REM ============================================================
echo [6/8] Copiando data, plantillas y web a dist...

mkdir "%APP_DIST%\data" >nul 2>&1
copy /y "data\Data.xlsx" "%APP_DIST%\data\Data.xlsx" >nul
if errorlevel 1 goto :fail
copy /y "data\Mapeo.xlsx" "%APP_DIST%\data\Mapeo.xlsx" >nul
if errorlevel 1 goto :fail
copy /y "data\Moldes.xlsx" "%APP_DIST%\data\Moldes.xlsx" >nul
if errorlevel 1 goto :fail

copy /y "VERSION.txt" "%APP_DIST%\VERSION.txt" >nul
if errorlevel 1 goto :fail
copy /y "RELEASE_3.0.txt" "%APP_DIST%\RELEASE_3.0.txt" >nul
if errorlevel 1 goto :fail
copy /y "LEEME.txt" "%APP_DIST%\LEEME.txt" >nul
if errorlevel 1 goto :fail

REM Las plantillas y el frontend se mantienen FUERA de _internal para que
REM puedan actualizarse sin recompilar el ejecutable.
robocopy "plantillas" "%APP_DIST%\plantillas" *.xlsx /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail

robocopy "web" "%APP_DIST%\web" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail

mkdir "%APP_DIST%\input" >nul 2>&1
mkdir "%APP_DIST%\output" >nul 2>&1

REM Historial.csv no se copia: una instalacion nueva inicia con historial vacio.
REM InjectFlow lo crea automaticamente en la primera generacion exitosa.

REM ============================================================
REM 7. Verificar estructura de distribucion
REM ============================================================
echo [7/8] Verificando estructura final de dist...

if not exist "%APP_DIST%\InjectFlow.exe" goto :invalid_dist
if not exist "%APP_DIST%\_internal" goto :invalid_dist

if not exist "%APP_DIST%\data\Data.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\data\Mapeo.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\data\Moldes.xlsx" goto :invalid_dist

if not exist "%APP_DIST%\VERSION.txt" goto :invalid_dist
if not exist "%APP_DIST%\RELEASE_3.0.txt" goto :invalid_dist
if not exist "%APP_DIST%\LEEME.txt" goto :invalid_dist

if not exist "%APP_DIST%\web\index.html" goto :invalid_dist
if not exist "%APP_DIST%\web\js\main.js" goto :invalid_dist
if not exist "%APP_DIST%\web\css\styles.css" goto :invalid_dist
if not exist "%APP_DIST%\web\assets\LogoCazel.webp" goto :invalid_dist

if not exist "%APP_DIST%\plantillas\Haitian Zeres Gen V.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\plantillas\Haitian Zeres Gen III_500.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\plantillas\Haitian Zeres Gen III_800.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\plantillas\Haitian Zeres Gen III_1080.xlsx" goto :invalid_dist
if not exist "%APP_DIST%\plantillas\Haitian Jupiter TwoShot_1080.xlsx" goto :invalid_dist

if not exist "%APP_DIST%\input" goto :invalid_dist
if not exist "%APP_DIST%\output" goto :invalid_dist

REM ============================================================
REM 8. Resumen final
REM ============================================================
echo [8/8] Build validado.
echo.
echo ============================================================
echo   BUILD COMPLETADO CORRECTAMENTE
echo ============================================================
echo.
echo Ejecutable:
echo   %CD%\%APP_DIST%\InjectFlow.exe
echo.
echo Estructura de distribucion creada:
echo   InjectFlow.exe
echo   _internal\
echo   data\
echo   plantillas\
echo   web\
echo   input\
echo   output\
echo.
echo Para distribuir InjectFlow, copia la carpeta COMPLETA:
echo   %CD%\%APP_DIST%
echo.
echo IMPORTANTE: No copies solamente InjectFlow.exe.
echo El programa necesita _internal, data, plantillas y web junto al EXE.
echo.
pause
exit /b 0

:missing_project
echo [ERROR] Faltan archivos maestros requeridos para construir InjectFlow.
echo Verifica especialmente data, plantillas, web, VERSION.txt y RELEASE_3.0.txt.
goto :fail

:invalid_dist
echo [ERROR] El EXE fue creado, pero la estructura final de dist quedo incompleta.
echo La carpeta incompleta se eliminara para evitar distribuirla por error.
goto :fail

:fail
echo.
echo ============================================================
echo   BUILD CANCELADO / CON ERROR
echo ============================================================
if exist "%APP_DIST%" (
    echo Eliminando distribucion incompleta: %APP_DIST%
    rmdir /s /q "%APP_DIST%"
)
echo Revisa el mensaje mostrado arriba y vuelve a ejecutar el build.
echo.
pause
exit /b 1
