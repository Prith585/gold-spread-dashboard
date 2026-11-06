@echo off
title Gold Spot vs Futures Spread Arbitrage Terminal
echo =====================================================================
echo    GOLD SPOT / FUT SPREAD ARBITRAGE DASHBOARD (MCX ^& ALL INDIA BULLION)
echo =====================================================================
echo Starting backend server on http://localhost:5055 ...
cd /d "%~dp0"

start "" http://localhost:5055
python app.py
pause
