@echo off
title LiveOps Management App
echo ====================================================
echo Starting LiveOps Workforce Management Server...
echo ====================================================
cd /d "%~dp0"
"C:\Users\Ahmed\AppData\Local\Python\bin\python.exe" run_server.py
pause
