# Jarvis Personal AI (with laptop control)

Two parts:
1. `index.html` - the Jarvis interface (host it on GitHub Pages).
2. `agent.py` - a small helper that runs on YOUR laptop and does the real work
   (open apps, type, press keys, volume, screenshots, lock, shutdown, find files, run commands).

## Step 1: Put the interface on GitHub Pages
1. Create a repository on github.com, upload `index.html`, `agent.py`, `start_jarvis_agent.bat`, `README.md`.
2. Settings > Pages > Branch `main` / root > Save.
3. Your Jarvis is at `https://<username>.github.io/<repo>/`.

## Step 2: Run the agent on your laptop (Windows)
1. Install Python from python.org (tick "Add Python to PATH").
2. Download `agent.py` and `start_jarvis_agent.bat` into one folder. Double-click the .bat file.
3. A window prints a secret token. Keep the window open.
4. Open your Jarvis page, click the laptop icon at the top, paste the token, Save. It should say Connected.

(Mac/Linux: `pip3 install pyautogui` then `python3 agent.py`.)

## Commands
open spotify / open chrome / open notepad - close chrome - type hello world - press ctrl s -
volume 40 / mute / next song / pause - take a screenshot - open downloads - find file resume -
open file resume - lock the laptop - sleep - show desktop - switch window -
run command ipconfig - shut down / restart (asks you to confirm first).

## Safety
- The agent only listens on 127.0.0.1, so other devices cannot reach it.
- Every request needs your secret token (stored in `~/.jarvis_token`); wrong origins and wrong hosts are rejected.
- Shutdown, restart, sign out, close app and run command always ask "yes/no" first.
- Never share your token. Delete `~/.jarvis_token` and restart the agent to get a new one.
- Moving the mouse to a screen corner aborts any typing/key automation (pyautogui failsafe).

## Limits
- Chrome and Edge work best. Chrome may ask permission for the page to reach devices on your network - allow it.
- Firefox and Safari may block an https page from talking to localhost.
- Commands are matched by keywords, not free-form AI. Ask me to add an AI brain if you want open-ended tasks.
