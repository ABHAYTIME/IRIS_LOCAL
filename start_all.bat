@echo off
echo Starting CrashGuard Full-Stack System...
echo ==============================================

echo [1/3] Starting Flask Hub API...
start "CrashGuard API Server" cmd /k "call .venv\Scripts\activate.bat && python driver_app\server.py"

timeout /t 3 /nobreak > nul

echo [2/3] Starting Streamlit Command Center...
start "CrashGuard Dashboard" cmd /k "call .venv\Scripts\activate.bat && streamlit run dashboard.py"

timeout /t 3 /nobreak > nul

echo [3/3] Starting AI Video Sensor...
start "CrashGuard AI Video Sensor" cmd /k "call .venv\Scripts\activate.bat && python detect_video_live.py test1.mp4"

echo ==============================================
echo All 3 components have been launched in separate windows!
echo Keep those windows open while testing.
