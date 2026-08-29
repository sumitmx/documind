@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found at .venv\Scripts\python.exe
    echo Create it first with: python -m venv .venv
    echo Then install dependencies with: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting DocuMind portal...
echo Open http://127.0.0.1:8000 in your browser once it's ready.
echo Press Ctrl+C to stop the server.
echo.

".venv\Scripts\python.exe" -m backend.api.server

pause
