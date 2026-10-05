@echo off
echo Starting AI Smart Security Camera...
echo.
echo Keys: Q=quit  R=reload gallery  S=snapshot
echo.
call venv\Scripts\activate.bat
python src\main.py %*
