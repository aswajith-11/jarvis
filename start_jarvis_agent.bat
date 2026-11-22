@echo off
title Jarvis Laptop Agent
cd /d "%~dp0"
python -m pip install --quiet -r requirements.txt
python agent.py
pause
