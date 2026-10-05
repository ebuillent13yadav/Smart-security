@echo off
echo Starting Warden Dashboard...
echo.
echo Opening browser at http://localhost:8501
echo Press Ctrl+C to stop.
echo.
call venv\Scripts\activate.bat
streamlit run src\dashboard.py --server.port 8501 --server.headless false
