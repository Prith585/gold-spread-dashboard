@echo off
title Gold Arbitrage Terminal - Mobile Access Tunnel
color 0E
echo ======================================================================
echo       GOLD ARBITRAGE TERMINAL - MOBILE DATA / 4G ACCESS LAUNCHER
echo ======================================================================
echo.
echo Starting secure Cloudflare HTTPS tunnel for port 5055...
echo Once started, look for the link ending in .trycloudflare.com below!
echo.
cd /d "%~dp0"
cloudflared.exe tunnel --url http://localhost:5055
pause
