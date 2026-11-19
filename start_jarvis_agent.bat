@echo off
title Jarvis Laptop Agent
python -m pip install --quiet pyautogui
python "%~dp0agent.py"
pause
