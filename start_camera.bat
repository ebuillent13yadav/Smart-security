@echo off
echo Starting AI Smart Security Camera...
echo.
echo Keys: Q=quit  R=reload  S=snapshot  N=network toggle (4G/5G)  A=reset alarm
echo.
call venv\Scripts\activate.bat
python src\main.py %*
