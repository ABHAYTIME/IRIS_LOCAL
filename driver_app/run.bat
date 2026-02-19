@echo off
echo ============================================
echo   CrashGuard-S ^| Ambulance Driver App
echo ============================================
echo.
echo [1/2] Installing dependencies...
pip install flask opencv-python
echo.
echo [2/2] Starting server...
echo.
echo Open your browser at: http://localhost:5000
echo Press Ctrl+C to stop.
echo.
cd /d "%~dp0"
python server.py
pause
