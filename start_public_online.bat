@echo off
title LiveOps Scheduler - Online Public Tunnel
echo ========================================================
echo   Starting LiveOps Scheduler + Cloudflare Online Tunnel
echo ========================================================
echo.

:: Start python server in background if not already running
start /b "" python run_server.py

:: Give server 2 seconds to start
timeout /t 2 /nobreak >nul

:: Start Cloudflare tunnel
echo Starting Cloudflare Online Tunnel...
echo.
cloudflared.exe tunnel --url http://127.0.0.1:8050

pause
