@echo off
chcp 65001 >nul
cd /d "%~dp0"
python src\import_explanations.py
if errorlevel 1 goto end
python src\build.py
:end
echo.
pause
