@echo off
title Jarvis Laptop Agent
cd /d "%~dp0"
where python >nul 2>nul && (python jarvis.py) || (py jarvis.py)
pause
