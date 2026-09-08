@echo off
setlocal
cd /d "%~dp0"

if exist ".venv_build" rmdir /s /q ".venv_build"
if exist "build_temp" rmdir /s /q "build_temp"
if exist "dist_build" rmdir /s /q "dist_build"
if exist ".pytest_cache" rmdir /s /q ".pytest_cache"

for /d /r %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D"
del /s /q *.pyc >nul 2>&1

echo Temporales de build eliminados.
pause
endlocal
