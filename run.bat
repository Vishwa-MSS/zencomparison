@echo off
cd /d "%~dp0"
echo Starting ZEN Comparison...
".venv\Scripts\streamlit.exe" run app.py
pause
