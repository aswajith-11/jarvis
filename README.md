# JARVIS - personal AI laptop agent (local Ollama brain)

JARVIS understands natural language, plans multi-step tasks, and controls your Windows laptop.
The AI runs **locally in Ollama**: no cloud AI, no API key, no cost.

```
 Website (GitHub Pages)  --token-->  agent.py on YOUR laptop (127.0.0.1:8765)
 index.html style.css script.js         |-- ai_brain.py  talks to Ollama, plans step by step
                                        |-- tools.py     the only things JARVIS can do
                                        |-- memory.py    local memory (~/.jarvis/memory.json)
                                        '-- config.py    settings
```

## Files
| File | Purpose |
|---|---|
| index.html, style.css, script.js | The interface (host on GitHub Pages) |
| agent.py | Secure local server (localhost only, token required) |
| ai_brain.py | Ollama connection + validated multi-step planner |
| tools.py | Laptop-control tools (apps, files, keys, volume, power...) |
| memory.py | Local memory, with a panel to view/delete it |
| config.py | Settings (model, port, approved scripts...) |
| start_jarvis_agent.bat | Windows launcher |
| requirements.txt, .gitignore | Dependencies; keeps secrets out of GitHub |

## Install (Windows 11)
1. **Python 3.10+** from python.org (tick "Add Python to PATH").
2. **Ollama** is already installed. Make sure the model exists: `ollama pull llama3.2:1b`
3. Copy all files into one folder on your laptop. Double-click **start_jarvis_agent.bat**.
   It prints a **secret token**. Keep the window open.
4. Open your Jarvis website, click the **💻** icon, paste the token, **Save & connect**.
   The top bar should show `● Agent online` and `Brain: llama3.2:1b`.

## Update your GitHub site
Replace `index.html` and add `style.css` and `script.js` in your repository. Do **not** upload `agent.py`'s data:
the token and memory live in `~/.jarvis/` on your laptop, not in the project folder. `.gitignore` already protects them.
(agent.py and the other .py files may be in the repo too; they contain no secrets.)

## Things to say
- "Open Chrome and search for artificial intelligence." - "Open Notepad and type hello team."
- "Find my latest PDF." - "Create a folder named Projects on my desktop." - "Open my downloads folder."
- "Which applications do I have with 'code' in the name?" - "Take a screenshot." - "Set volume to 30."
- Follow-ups: "Open it again." "Close the app you opened earlier."
- "Remember that my favourite editor is VS Code." (Never passwords.)
Quick commands (volume, media, lock, "open spotify"...) run instantly; everything else goes to the AI.
Stop anything with the **■** button, the **Esc** key, or by clicking the orb.

## Choosing a better model
`llama3.2:1b` is tiny and will sometimes misunderstand complex requests. JARVIS checks every step, so mistakes are
caught rather than executed, but a bigger model is far more capable. Your RTX 2050 (4 GB) can run a 3B model well:
```
ollama pull llama3.2:3b
```
Then create `C:\Users\<you>\.jarvis\config.json`:
```json
{ "model": "llama3.2:3b" }
```
Restart the agent. Other options: `"max_steps"`, `"allowed_scripts"`, `"allowed_origins"`, `"port"`.

## Approved scripts
The AI can never run arbitrary shell commands. To let it run a script you trust, name it in `config.json`:
```json
{ "allowed_scripts": { "backup": ["C:\\Users\\you\\scripts\\backup.bat"] } }
```
Then say "run the backup script". It always asks for confirmation first.

## Security
- Agent listens on 127.0.0.1 only; every request needs your token; origin and host headers are checked.
- The AI can only call whitelisted tools with validated arguments. There is no shell tool.
- Files: only inside your user folder; `.ssh`, `AppData`, `.jarvis` and similar are blocked. Deletes go to `Jarvis_Trash`.
- Always asks yes/no before: delete, move, overwrite, close an app, shutdown/restart/sign out, run a script, open program files.
- JARVIS only reports success when a tool confirms it; failures are reported as failures.
- Move the mouse to a screen corner to abort any typing/key automation (pyautogui failsafe).
- Never share or commit `~/.jarvis/token`. Delete it and restart the agent to get a new one.

## Troubleshooting
- **Agent offline**: run the .bat; check the token. Use Chrome or Edge (Firefox/Safari may block https pages from reaching localhost).
  Chrome may ask to allow access to local devices: allow it.
- **Ollama not running / model missing**: the Laptop panel tells you exactly what to run.
- **Slow replies**: the first request loads the model. Close other GPU-heavy apps or use a smaller model.
- **Typing does nothing**: `pip install pyautogui pyperclip`, and click into the target window; JARVIS types into whatever has focus.

## Honest limits
- Tested on Linux with a simulated Ollama server; Windows-only actions (launching apps, volume, lock, Start Menu search) are written
  for Windows 11 but need your first run to confirm.
- "Close Chrome when I finish" (a deferred action) isn't scheduled; JARVIS will ask you to tell it when you're done.
- Voice input/output use your browser's built-in speech features (Chrome/Edge recommended).
