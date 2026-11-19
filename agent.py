#!/usr/bin/env python3
"""
Jarvis Laptop Agent
Runs on YOUR laptop and lets the Jarvis web page open apps, type, press keys,
change volume, take screenshots, lock/shutdown, find files, run commands...

Security:
  * listens on 127.0.0.1 only (not reachable from other devices)
  * every request needs the secret token printed at startup
  * dangerous actions (shutdown, restart, close app, run command) need confirmation
Optional: pip install pyautogui   (needed for typing, key presses, screenshots)
"""
import json, os, sys, shutil, subprocess, platform, secrets, hmac, difflib, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("JARVIS_PORT", "8765"))
OS = platform.system()          # Windows / Darwin / Linux
HOME = Path.home()
TOKEN_FILE = HOME / ".jarvis_token"
ALLOWED_ORIGINS = os.environ.get("JARVIS_ORIGINS", "").split(",") if os.environ.get("JARVIS_ORIGINS") else []

try:
    import pyautogui
    pyautogui.FAILSAFE = True   # slam mouse into a screen corner to abort automation
    pyautogui.PAUSE = 0.02
except Exception:
    pyautogui = None

def get_token():
    if TOKEN_FILE.exists():
        t = TOKEN_FILE.read_text().strip()
        if t:
            return t
    t = secrets.token_urlsafe(12)
    TOKEN_FILE.write_text(t)
    return t
TOKEN = get_token()

def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)

# ---------------------------------------------------------------- apps
ALIASES_WIN = {
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
    "command prompt": "cmd", "cmd": "cmd", "terminal": "wt", "powershell": "powershell",
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer",
    "settings": "ms-settings:", "task manager": "taskmgr", "control panel": "control",
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "firefox": "firefox",
    "vs code": "code", "vscode": "code", "visual studio code": "code",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt", "snipping tool": "snippingtool",
    "camera": "microsoft.windows.camera:", "clock": "ms-clock:", "store": "ms-windows-store:",
}
_index = {}
def build_index():
    """Index Start-Menu shortcuts so 'open spotify' works for any installed app."""
    _index.clear()
    if OS == "Windows":
        roots = [Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
                 Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
                 HOME / "Desktop", Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "Desktop"]
        for r in roots:
            if r.exists():
                for p in r.rglob("*"):
                    if p.suffix.lower() in (".lnk", ".url", ".exe") and "uninstall" not in p.stem.lower():
                        _index.setdefault(p.stem.lower(), str(p))
    elif OS == "Darwin":
        for r in (Path("/Applications"), Path("/System/Applications"), HOME / "Applications"):
            if r.exists():
                for p in r.glob("*.app"):
                    _index.setdefault(p.stem.lower(), str(p))

def find_app(name):
    n = name.lower().strip()
    if n in _index: return _index[n]
    starts = [k for k in _index if k.startswith(n)]
    if starts: return _index[min(starts, key=len)]
    contains = [k for k in _index if n in k]
    if contains: return _index[min(contains, key=len)]
    close = difflib.get_close_matches(n, list(_index), n=1, cutoff=0.7)
    return _index[close[0]] if close else None

def open_app(name):
    n = name.lower().strip()
    if OS == "Windows":
        if n in ALIASES_WIN:
            subprocess.Popen(["cmd", "/c", "start", "", ALIASES_WIN[n]], creationflags=0x08000000)
            return f"Opening {name}."
        p = find_app(n)
        if p:
            os.startfile(p); return f"Opening {Path(p).stem}."
        r = subprocess.run(["cmd", "/c", "start", "", n], capture_output=True, creationflags=0x08000000)
        if r.returncode == 0: return f"Opening {name}."
        return f"I could not find an app called {name}."
    if OS == "Darwin":
        r = subprocess.run(["open", "-a", name], capture_output=True)
        return f"Opening {name}." if r.returncode == 0 else f"I could not find an app called {name}."
    exe = shutil.which(n) or shutil.which(n.replace(" ", "-"))
    if exe:
        subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return f"Opening {name}."
    return f"I could not find an app called {name}."

def close_app(name):
    n = name.lower().strip().replace(" ", "")
    if OS == "Windows":
        names = {"chrome": "chrome.exe", "edge": "msedge.exe", "notepad": "notepad.exe", "vscode": "Code.exe", "code": "Code.exe",
                 "calculator": "CalculatorApp.exe", "spotify": "Spotify.exe", "word": "WINWORD.EXE", "excel": "EXCEL.EXE"}
        exe = names.get(n, n if n.endswith(".exe") else n + ".exe")
        r = subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True, text=True, creationflags=0x08000000)
        return f"Closed {name}." if r.returncode == 0 else f"{name} does not seem to be running."
    if OS == "Darwin":
        subprocess.run(["osascript", "-e", f'quit app "{name}"']); return f"Closed {name}."
    r = subprocess.run(["pkill", "-f", name]); return f"Closed {name}." if r.returncode == 0 else f"{name} does not seem to be running."

# ---------------------------------------------------------------- keys / media
VK = {"mute": 0xAD, "down": 0xAE, "up": 0xAF, "next": 0xB0, "prev": 0xB1, "stop": 0xB2, "playpause": 0xB3}
def vkey(name, times=1):
    if OS == "Windows":
        import ctypes
        for _ in range(times):
            ctypes.windll.user32.keybd_event(VK[name], 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK[name], 0, 2, 0)
        return True
    return False

def set_volume(level=None, direction=None):
    if OS == "Windows":
        if direction == "mute": vkey("mute"); return "Toggled mute."
        if direction in ("up", "down"): vkey(direction, 5); return f"Volume {direction}."
        if level is not None:
            vkey("down", 50); vkey("up", round(max(0, min(100, level)) / 2)); return f"Volume set to {level} percent."
    elif OS == "Darwin":
        if direction == "mute": subprocess.run(["osascript", "-e", "set volume with output muted"]); return "Muted."
        cur = int(subprocess.run(["osascript", "-e", "output volume of (get volume settings)"], capture_output=True, text=True).stdout.strip() or 50)
        new = level if level is not None else cur + (10 if direction == "up" else -10)
        subprocess.run(["osascript", "-e", f"set volume output volume {max(0, min(100, new))}"]); return f"Volume {max(0, min(100, new))} percent."
    elif shutil.which("pactl"):
        if direction == "mute": subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]); return "Toggled mute."
        arg = f"{level}%" if level is not None else ("+10%" if direction == "up" else "-10%")
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", arg]); return "Volume changed."
    return "Volume control is not supported on this system."

def need_gui():
    if pyautogui is None:
        raise RuntimeError("Install pyautogui first:  pip install pyautogui")

def type_text(text):
    need_gui(); time.sleep(0.3)
    if OS == "Windows" or OS == "Darwin":
        # clipboard paste handles every character and is much faster than key-by-key
        try:
            set_clip(text); pyautogui.hotkey("command" if OS == "Darwin" else "ctrl", "v"); return "Typed it."
        except Exception:
            pass
    pyautogui.write(text, interval=0.01); return "Typed it."

def set_clip(text):
    if OS == "Windows":
        subprocess.run(["clip"], input=text.encode("utf-16le"), creationflags=0x08000000, check=True)  # utf-16 for unicode
    elif OS == "Darwin":
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
    else:
        raise RuntimeError("no clipboard")

def press(keys):
    need_gui()
    parts = [k.strip().lower() for k in keys.replace("+", " ").split() if k.strip()]
    fix = {"control": "ctrl", "windows": "win", "escape": "esc", "return": "enter", "delete": "del"}
    parts = [fix.get(p, p) for p in parts]
    pyautogui.hotkey(*parts) if len(parts) > 1 else pyautogui.press(parts[0])
    return "Pressed " + " + ".join(parts) + "."

# ---------------------------------------------------------------- system
FOLDERS = {"desktop": HOME / "Desktop", "documents": HOME / "Documents", "downloads": HOME / "Downloads",
           "pictures": HOME / "Pictures", "music": HOME / "Music", "videos": HOME / "Videos", "home": HOME}
def open_path(p):
    p = str(p)
    if OS == "Windows": os.startfile(p)
    elif OS == "Darwin": subprocess.Popen(["open", p])
    else: subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def open_folder(name):
    f = FOLDERS.get(name.lower().strip())
    if not f: return f"I don't know a folder called {name}."
    open_path(f); return f"Opening {name}."

def find_file(query, open_first=False):
    q = query.lower().strip(); hits = []
    for base in (HOME / "Desktop", HOME / "Documents", HOME / "Downloads", HOME / "Pictures", HOME / "Music", HOME / "Videos"):
        if not base.exists(): continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
            for f in files:
                if q in f.lower():
                    hits.append(os.path.join(root, f))
                    if len(hits) >= 20: break
            if len(hits) >= 20: break
    if not hits: return "I could not find a file matching " + query + ".", []
    if open_first: open_path(hits[0])
    return (f"Found {len(hits)} match{'es' if len(hits)>1 else ''}. " + ("Opening the first one." if open_first else f"Top result: {os.path.basename(hits[0])}.")), hits[:8]

def screenshot():
    need_gui()
    out = HOME / "Pictures" / "Jarvis"; out.mkdir(parents=True, exist_ok=True)
    p = out / time.strftime("screenshot_%Y%m%d_%H%M%S.png")
    pyautogui.screenshot(str(p)); return f"Screenshot saved to Pictures, Jarvis folder.", str(p)

def power(kind):
    if OS == "Windows":
        cmds = {"lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
                "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                "shutdown": ["shutdown", "/s", "/t", "10"], "restart": ["shutdown", "/r", "/t", "10"], "cancel": ["shutdown", "/a"],
                "logoff": ["shutdown", "/l"]}
    elif OS == "Darwin":
        cmds = {"lock": ["pmset", "displaysleepnow"], "sleep": ["pmset", "sleepnow"],
                "shutdown": ["osascript", "-e", 'tell app "System Events" to shut down'],
                "restart": ["osascript", "-e", 'tell app "System Events" to restart']}
    else:
        cmds = {"lock": ["loginctl", "lock-session"], "sleep": ["systemctl", "suspend"],
                "shutdown": ["systemctl", "poweroff"], "restart": ["systemctl", "reboot"]}
    c = cmds.get(kind)
    if not c: return "Not supported on this system."
    subprocess.Popen(c)
    return {"lock": "Locking your laptop.", "sleep": "Going to sleep.", "shutdown": "Shutting down in 10 seconds. Say cancel shutdown to stop.",
            "restart": "Restarting in 10 seconds. Say cancel shutdown to stop.", "cancel": "Shutdown cancelled.", "logoff": "Signing out."}[kind]

def run_cmd(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30,
                       creationflags=0x08000000 if OS == "Windows" else 0)
    out = (r.stdout or r.stderr or "").strip()
    return ("Command finished. " + out[:400]) if out else "Command finished with no output."

# ---------------------------------------------------------------- dispatcher
DANGEROUS = {"shutdown", "restart", "logoff", "close_app", "run_cmd"}
def handle(req):
    a = req.get("action", "")
    if a in DANGEROUS and not req.get("confirm"):
        what = {"shutdown": "shut down your laptop", "restart": "restart your laptop", "logoff": "sign you out",
                "close_app": f"force close {req.get('name','that app')}", "run_cmd": "run the command: " + str(req.get("cmd", ""))[:80]}[a]
        return {"needs_confirm": True, "message": f"This will {what}."}
    if a == "open_app": return {"message": open_app(req["name"])}
    if a == "close_app": return {"message": close_app(req["name"])}
    if a == "open_url":
        import webbrowser; webbrowser.open(req["url"]); return {"message": "Opening it in your browser."}
    if a == "open_folder": return {"message": open_folder(req["name"])}
    if a == "find_file":
        m, hits = find_file(req["query"], req.get("open", False)); return {"message": m, "files": hits}
    if a == "type": return {"message": type_text(req["text"])}
    if a == "press": return {"message": press(req["keys"])}
    if a == "volume": return {"message": set_volume(req.get("level"), req.get("direction"))}
    if a == "media":
        k = req.get("key");
        if vkey({"play": "playpause", "pause": "playpause", "next": "next", "prev": "prev", "stop": "stop"}[k]) : return {"message": "Done."}
        if pyautogui: pyautogui.press({"play": "playpause", "pause": "playpause", "next": "nexttrack", "prev": "prevtrack", "stop": "stop"}[k]); return {"message": "Done."}
        return {"message": "Media keys are not supported here."}
    if a == "screenshot":
        m, p = screenshot(); return {"message": m, "path": p}
    if a in ("lock", "sleep", "shutdown", "restart", "logoff", "cancel"): return {"message": power(a)}
    if a == "run_cmd": return {"message": run_cmd(req["cmd"])}
    if a == "show_desktop": return {"message": press("win d" if OS == "Windows" else "command f3")}
    if a == "switch_window": return {"message": press("alt tab" if OS != "Darwin" else "command tab")}
    if a == "refresh_apps": build_index(); return {"message": f"Indexed {len(_index)} apps."}
    return {"message": f"Unknown action {a}."}


# ---------------------------------------------------------------- local AI brain (Ollama)
OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.environ.get("JARVIS_MODEL", "llama3.2:1b")
AI_ACTIONS = {"open_app", "open_url", "open_folder", "find_file", "volume",
              "media", "screenshot", "show_desktop", "switch_window", "type",
              "press", "lock", "sleep", "shutdown", "restart", "logoff", "close_app"}

def ask_local_ai(messages):
    """Ask Ollama to understand the request and return a constrained JSON plan."""
    import urllib.request
    system = (
        "You are Jarvis, a helpful Windows laptop assistant. Understand natural language, "
        "including indirect and multi-step requests. Return ONLY one JSON object, no markdown. "
        "Schema: {\"type\":\"chat\",\"reply\":\"...\"} OR "
        "{\"type\":\"search\",\"query\":\"...\",\"reply\":\"...\"} OR "
        "{\"type\":\"action\",\"action\":{\"action\":\"...\",\"name\":\"...\","
        "\"url\":\"...\",\"query\":\"...\",\"open\":false,\"level\":50,"
        "\"direction\":\"up|down|mute\",\"key\":\"play|pause|next|prev|stop\","
        "\"text\":\"...\",\"keys\":\"ctrl s\"}} OR "
        "{\"type\":\"clarify\",\"reply\":\"...\"}. "
        "Allowed action names ONLY: open_app, open_url, open_folder, find_file, volume, "
        "media, screenshot, show_desktop, switch_window, type, press, lock, sleep, "
        "shutdown, restart, logoff, close_app. Never invent an action. "
        "For general knowledge, explanations, greetings, planning or conversation, use chat. "
        "For current facts or finding information online, use search with a short query. "
        "For opening an installed desktop app use open_app. For opening a website use open_url "
        "with a full https URL. For file searches use find_file. Ask a concise clarification "
        "when the target is ambiguous. Never request or reveal passwords, tokens or secrets. "
        "Never use shell commands, scripts, arbitrary code, registry edits, or security bypasses. "
        "Do not claim an action succeeded; the app will report its result. "
        "For dangerous actions like shutdown, restart, logoff or force-closing an app, "
        "the app will ask the user for confirmation."
    )
    clean = []
    for item in messages[-12:]:
        role = item.get("role")
        content = str(item.get("content", ""))[:2000]
        if role in ("user", "assistant") and content:
            clean.append({"role": role, "content": content})
    payload = json.dumps({
        "model": OLLAMA_MODEL, "stream": False, "format": "json",
        "messages": [{"role": "system", "content": system}] + clean,
        "options": {"temperature": 0.2}
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    raw = data.get("message", {}).get("content", "")
    plan = json.loads(raw)
    if not isinstance(plan, dict):
        raise ValueError("The AI returned an invalid plan.")
    kind = plan.get("type")
    if kind not in ("chat", "search", "action", "clarify"):
        raise ValueError("The AI returned an unsupported response.")
    if kind == "action":
        action = plan.get("action")
        if not isinstance(action, dict) or action.get("action") not in AI_ACTIONS:
            raise ValueError("The AI requested an action that is not allowed.")
        if action.get("action") == "open_app" and not str(action.get("name", "")).strip():
            raise ValueError("Please tell me which application to open.")
        if action.get("action") == "open_url":
            url = str(action.get("url", ""))
            if not url.startswith(("https://", "http://")) or len(url) > 2000:
                raise ValueError("I need a valid website address before opening it.")
        if action.get("action") == "find_file":
            action["query"] = str(action.get("query", ""))[:160]
            if not action["query"]:
                raise ValueError("Please tell me which file to find.")
        if action.get("action") == "type":
            action["text"] = str(action.get("text", ""))[:2000]
        if action.get("action") == "press":
            action["keys"] = str(action.get("keys", ""))[:80]
        plan["action"] = action
    return plan

# ---------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _origin_ok(self):
        o = self.headers.get("Origin", "")
        if not o: return ""
        ok = (o in ("null",) or o.startswith("http://localhost") or o.startswith("http://127.0.0.1")
              or (o.startswith("https://") and o.endswith(".github.io")) or o in ALLOWED_ORIGINS)
        return o if ok else None
    def _host_ok(self):
        return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")   # blocks DNS-rebinding
    def _send(self, code, obj=None):
        o = self._origin_ok()
        self.send_response(code)
        if o: self.send_header("Access-Control-Allow-Origin", o); self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Jarvis-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Type", "application/json")
        body = json.dumps(obj or {}).encode(); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self):
        if not self._host_ok() or self._origin_ok() is None: return self._send(403, {"error": "forbidden"})
        self._send(204)
    def _auth(self):
        if not self._host_ok() or self._origin_ok() is None: self._send(403, {"error": "forbidden"}); return False
        if not hmac.compare_digest(self.headers.get("X-Jarvis-Token", ""), TOKEN): self._send(401, {"error": "bad token"}); return False
        return True
    def do_GET(self):
        if self.path == "/ping" and self._auth():
            self._send(200, {"ok": True, "os": OS, "gui": pyautogui is not None,
                             "ai": True, "model": OLLAMA_MODEL})
    def do_POST(self):
        if self.path not in ("/do", "/ask") or not self._auth(): return
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 20000: return self._send(413, {"error": "request too large"})
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/ask":
                plan = ask_local_ai(req.get("messages", []))
                if plan.get("type") == "action":
                    log("AI PLAN", plan.get("action", {}).get("action"))
                self._send(200, plan)
            else:
                log("ACTION", {k: v for k, v in req.items()})
                self._send(200, handle(req))
        except Exception as e:
            log("ERROR", e)
            message = ("Local AI is unavailable. Check that Ollama is running and "
                       f"that model '{OLLAMA_MODEL}' is installed. Details: {e}")
            self._send(200, {"type": "error", "message": message})

if __name__ == "__main__":
    build_index()
    print("=" * 60)
    print(" JARVIS LAPTOP AGENT  -  running on", OS)
    print(f" Listening on http://127.0.0.1:{PORT}  (this laptop only)")
    print(f" Indexed {len(_index)} apps.   pyautogui: {'yes' if pyautogui else 'NO (pip install pyautogui)'}")
    print("\n YOUR SECRET TOKEN (paste it into Jarvis > Laptop panel):\n")
    print("   ", TOKEN, "\n")
    print(" Keep this window open. Press Ctrl+C to stop.")
    print("=" * 60)
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
    except KeyboardInterrupt:
        print("Bye.")
