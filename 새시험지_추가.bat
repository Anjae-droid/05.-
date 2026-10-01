@echo off
chcp 65001 >nul
cd /d "%~dp0"
python src\extract_pdf.py
if errorlevel 1 goto end
python src\build.py
:end
echo.
pause
