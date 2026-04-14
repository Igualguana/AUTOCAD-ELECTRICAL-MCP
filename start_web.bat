@echo off
REM ═══════════════════════════════════════════════════════════════════════════
REM  AutoCAD Electrical — AI Control Center
REM  Modo B: Interfaz web local + Ollama (sin Claude)
REM ═══════════════════════════════════════════════════════════════════════════

title AutoCAD Electrical - AI Control Center

cd /d "%~dp0"

echo.
echo  ══════════════════════════════════════════════════
echo   AutoCAD Electrical - AI Control Center
echo   Iniciando servidor web en http://127.0.0.1:8080
echo  ══════════════════════════════════════════════════
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.11+ desde python.org
    pause
    exit /b 1
)

REM Check fastapi/uvicorn
python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando dependencias web...
    pip install fastapi uvicorn[standard] httpx
    echo.
)

REM Start server
python start_web.py %*

pause
