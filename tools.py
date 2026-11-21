"""JARVIS laptop-control tools.

Every tool is registered with a schema. The AI can only call tools listed here, with arguments
that pass validation. There is deliberately NO "run any shell command" tool: scripts must be
named in config (allowed_scripts) and always need confirmation.
"""
import os, shutil, subprocess, time, json, difflib, webbrowser, re, urllib.parse, platform
from pathlib import Path
import config, memory
from config import OS, HOME

try:
    import pyautogui
    pyautogui.FAILSAFE = True            # slam the mouse into a screen corner to abort
    pyautogui.PAUSE = 0.02
except Exception:
    pyautogui = None
try: import pyperclip
except Exception: pyperclip = None
try: import psutil
except Exception: psutil = None

NOWIN = 0x08000000 if OS == "Windows" else 0     # CREATE_NO_WINDOW

class ToolError(Exception):
    """A problem we can explain to the user in one sentence."""

# ---------------------------------------------------------------- registry
REG = {}
def tool(name, desc, params=None, confirm=None):
    """params: {arg: (type, required, description[, [enum values]])}; confirm(args) -> text if the user must approve."""
    def deco(fn):
        REG[name] = {"fn": fn, "desc": desc, "params": params or {}, "confirm": confirm}
        return fn
    return deco

def validate(name, args):
    if name not in REG: raise ToolError(f"There is no tool called {name}.")
    if not isinstance(args, dict): raise ToolError("Arguments must be an object.")
    clean = {}
    for k, spec in REG[name]["params"].items():
        typ, req, _d = spec[:3]; enum = spec[3] if len(spec) > 3 else None
        v = args.get(k)
        if v is None or v == "":
            if req: raise ToolError(f"{name} needs the argument '{k}'.")
            continue
        try:
            if typ == "int": v = int(float(v))
            elif typ == "num": v = float(v)
            elif typ == "bool": v = v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes")
            else: v = str(v)[:4000]
        except (ValueError, TypeError): raise ToolError(f"'{k}' must be a {typ}.")
        if enum is not None:
            v = str(v).lower().strip()
            if v not in enum: raise ToolError(f"'{k}' must be one of: {', '.join(enum)}.")
        clean[k] = v
    return clean

def needs_confirm(name, clean):
    c = REG[name]["confirm"]
    return c(clean) if c else None

def execute(name, args, confirmed=False):
    """Validate and run a tool. Returns {ok, message, data?, needs_confirm?}. ok is True only if the tool itself succeeded."""
    try:
        clean = validate(name, args)
        d = needs_confirm(name, clean)
        if d and not confirmed:
            return {"ok": False, "needs_confirm": True, "message": f"This will {d}."}
        res = REG[name]["fn"](**clean)
        msg, data = res if isinstance(res, tuple) else (res, None)
        return {"ok": True, "message": msg, "data": data}
    except ToolError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}

def catalog():
    lines = []
    for n, t in REG.items():
        ps = ", ".join(f"{k}{'' if v[1] else '?'}" for k, v in t["params"].items())
        lines.append(f"- {n}({ps}): {t['desc']}")
    return "\n".join(lines)

# ---------------------------------------------------------------- paths
def _folders():
    f = {}
    for n in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"):
        c = [HOME / n]
        if os.environ.get("OneDrive"): c.insert(0, Path(os.environ["OneDrive"]) / n)
        f[n.lower()] = next((p for p in c if p.exists()), HOME / n)
    f["home"] = HOME
    return f
FOLDERS = _folders()

def safe_path(p):
    """Resolve a user/AI supplied path and make sure it is inside the folders JARVIS may use."""
    p = str(p).strip().strip('"').strip("'")
    if not p: raise ToolError("No path was given.")
    p = os.path.expanduser(p)
    path = Path(p)
    if not path.is_absolute():
        parts = Path(p.replace("\\", "/")).parts
        path = FOLDERS[parts[0].lower()].joinpath(*parts[1:]) if parts and parts[0].lower() in FOLDERS else HOME / p
    path = path.resolve()
    if not any(path == r or r in path.parents for r in config.ALLOWED_ROOTS):
        raise ToolError("That location is outside the folders I'm allowed to use.")
    if any(part.lower() in config.BLOCKED_PARTS for part in path.parts):
        raise ToolError("That location is protected, so I can't touch it.")
    return path

def _protected_root(path):
    return path in config.ALLOWED_ROOTS or path in FOLDERS.values()

EXEC_EXT = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".scr", ".com", ".jar", ".reg", ".lnk", ".sh", ".app"}

def _startfile(path):
    if OS == "Windows": os.startfile(str(path))
    elif OS == "Darwin": subprocess.Popen(["open", str(path)])
    else: subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ---------------------------------------------------------------- apps
ALIASES_WIN = {
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint", "command prompt": "cmd", "cmd": "cmd",
    "terminal": "wt", "powershell": "powershell", "file explorer": "explorer", "explorer": "explorer", "files": "explorer",
    "settings": "ms-settings:", "task manager": "taskmgr", "control panel": "control", "snipping tool": "snippingtool",
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge", "firefox": "firefox",
    "vs code": "code", "vscode": "code", "visual studio code": "code", "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
}
_index = {}      # lower-case app name -> ("path", file) or ("uwp", AppID)

def build_index():
    """Find installed apps (Start Menu shortcuts + Store apps) so 'open spotify' works for anything installed."""
    _index.clear()
    if OS == "Windows":
        roots = [Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
                 Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"]
        for r in roots:
            if r.exists():
                for p in r.rglob("*.lnk"):
                    if "uninstall" not in p.stem.lower(): _index.setdefault(p.stem.lower(), ("path", str(p)))
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
                                 capture_output=True, text=True, timeout=25, creationflags=NOWIN).stdout
            apps = json.loads(out or "[]"); apps = [apps] if isinstance(apps, dict) else apps
            for a in apps: _index.setdefault(a["Name"].lower(), ("uwp", a["AppID"]))
        except Exception: pass
    elif OS == "Darwin":
        for r in (Path("/Applications"), Path("/System/Applications"), HOME / "Applications"):
            if r.exists():
                for p in r.glob("*.app"): _index.setdefault(p.stem.lower(), ("path", str(p)))
    return len(_index)

def _find_app(n):
    if n in _index: return n
    starts = [k for k in _index if k.startswith(n)]
    if starts: return min(starts, key=len)
    contains = [k for k in _index if n in k]
    if contains: return min(contains, key=len)
    close = difflib.get_close_matches(n, list(_index), n=1, cutoff=0.7)
    return close[0] if close else None

@tool("open_app", "Open an installed desktop application by name (spotify, chrome, notepad, word...).",
      {"name": ("str", True, "app name")})
def open_app(name):
    n = name.lower().strip()
    if OS == "Windows":
        if n in ALIASES_WIN:
            subprocess.Popen(["cmd", "/c", "start", "", ALIASES_WIN[n]], creationflags=NOWIN); return f"Opened {name}."
        k = _find_app(n)
        if k:
            kind, ref = _index[k]
            if kind == "uwp": subprocess.Popen(["explorer", f"shell:AppsFolder\\{ref}"], creationflags=NOWIN)
            else: os.startfile(ref)
            return f"Opened {k.title()}."
        exe = shutil.which(n)
        if exe: subprocess.Popen([exe]); return f"Opened {name}."
    elif OS == "Darwin":
        if subprocess.run(["open", "-a", name], capture_output=True).returncode == 0: return f"Opened {name}."
    else:
        exe = shutil.which(n) or shutil.which(n.replace(" ", "-"))
        if exe:
            subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True); return f"Opened {name}."
    raise ToolError(f"I couldn't find an app called {name}. Try list_apps to see what's installed.")

@tool("list_apps", "Search installed applications by name. Leave query empty to list some.", {"query": ("str", False, "text to look for")})
def list_apps(query=""):
    if not _index: build_index()
    q = query.lower().strip()
    names = sorted(k for k in _index if q in k)[:25] if q else sorted(_index)[:25]
    if not names: return f"No installed app matches '{query}'.", []
    return "Found: " + ", ".join(n.title() for n in names), names

PROTECTED_PROCS = {"explorer.exe", "svchost.exe", "csrss.exe", "winlogon.exe", "system", "lsass.exe", "services.exe", "wininit.exe", "dwm.exe", "smss.exe"}

@tool("close_app", "Force-close a running application by name.", {"name": ("str", True, "app or process name")},
      confirm=lambda a: f"close {a['name']} (unsaved work in it may be lost)")
def close_app(name):
    n = name.lower().strip().replace(".exe", "")
    names = {"chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge", "vs code": "code", "vscode": "code",
             "visual studio code": "code", "word": "winword", "powerpoint": "powerpnt", "calculator": "calculatorapp", "terminal": "windowsterminal"}
    n = names.get(n, n)
    if psutil:
        killed = 0
        for p in psutil.process_iter(["name"]):
            pn = (p.info["name"] or "").lower()
            if pn in PROTECTED_PROCS: continue
            if pn.replace(".exe", "") == n or (len(n) > 3 and n in pn):
                try: p.terminate(); killed += 1
                except Exception: pass
        if killed: return f"Closed {name}."
        raise ToolError(f"{name} doesn't seem to be running.")
    if OS == "Windows":
        r = subprocess.run(["taskkill", "/IM", n + ".exe", "/F"], capture_output=True, creationflags=NOWIN)
    else:
        r = subprocess.run(["pkill", "-f", n])
    if r.returncode == 0: return f"Closed {name}."
    raise ToolError(f"{name} doesn't seem to be running.")

# ---------------------------------------------------------------- web
BROWSERS = ("chrome", "edge", "firefox")
def _browser_exe(b):
    pf = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    rel = {"chrome": "Google/Chrome/Application/chrome.exe", "edge": "Microsoft/Edge/Application/msedge.exe", "firefox": "Mozilla Firefox/firefox.exe"}[b]
    for base in pf:
        if base and (Path(base) / rel).exists(): return str(Path(base) / rel)
    return shutil.which({"chrome": "chrome", "edge": "msedge", "firefox": "firefox"}[b]) or shutil.which({"chrome": "google-chrome", "edge": "microsoft-edge", "firefox": "firefox"}[b])

def _norm_url(u):
    u = u.strip()
    if not re.match(r"^https?://", u, re.I):
        if " " in u or "." not in u: raise ToolError("That doesn't look like a website address.")
        u = "https://" + u
    if not re.match(r"^https?://[^\s]+$", u, re.I): raise ToolError("That doesn't look like a valid web address.")
    return u

def _browse(url, browser=None):
    if browser:
        exe = _browser_exe(browser)
        if exe: subprocess.Popen([exe, url]); return f"in {browser.title()}"
        webbrowser.open(url); return f"in your default browser ({browser.title()} was not found)"
    webbrowser.open(url); return "in your browser"

@tool("open_url", "Open a website address in the browser. Optional browser: chrome, edge or firefox.",
      {"url": ("str", True, "web address"), "browser": ("str", False, "chrome, edge or firefox", list(BROWSERS))})
def open_url(url, browser=None):
    u = _norm_url(url); where = _browse(u, browser); return f"Opened {u} {where}."

SITES = {"youtube": "https://www.youtube.com/results?search_query=", "google": "https://www.google.com/search?q=",
         "wikipedia": "https://en.wikipedia.org/w/index.php?search=", "github": "https://github.com/search?q=",
         "amazon": "https://www.amazon.in/s?k=", "maps": "https://www.google.com/maps/search/"}
@tool("web_search", "Search the web, or search inside a site (youtube, google, wikipedia, github, amazon, maps) in the browser.",
      {"query": ("str", True, "what to search for"), "site": ("str", False, "site to search in, default google", list(SITES)),
       "browser": ("str", False, "chrome, edge or firefox", list(BROWSERS))})
def web_search(query, site="google", browser=None):
    where = _browse(SITES[site] + urllib.parse.quote_plus(query), browser)
    return f"Searched {site.title()} for '{query}' {where}."

# ---------------------------------------------------------------- files & folders
@tool("open_folder", "Open one of your standard folders (desktop, documents, downloads, pictures, music, videos, home).",
      {"name": ("str", True, "folder name", list(FOLDERS))})
def open_folder(name):
    _startfile(FOLDERS[name]); return f"Opened your {name} folder."

@tool("open_path", "Open a specific file or folder by path (relative paths start in your home folder).", {"path": ("str", True, "path")},
      confirm=lambda a: (f"open the program file {Path(a['path']).name}" if Path(a["path"]).suffix.lower() in EXEC_EXT else None))
def open_path(path):
    p = safe_path(path)
    if not p.exists(): raise ToolError(f"{p.name} doesn't exist.")
    _startfile(p); return f"Opened {p.name}."

def _scan(q="", ext=None, folder=None, limit=4000):
    bases = [FOLDERS[folder]] if folder else [FOLDERS[k] for k in ("desktop", "documents", "downloads", "pictures", "music", "videos")]
    out, q = [], q.lower().strip(); ext = ("." + ext.lower().lstrip(".")) if ext else None
    n = 0
    for base in bases:
        if not base.exists(): continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".git")]
            for f in files:
                n += 1
                if n > limit * 10: return out
                if (not q or q in f.lower()) and (not ext or f.lower().endswith(ext)):
                    out.append(os.path.join(root, f))
    return out

@tool("find_file", "Find files whose name contains the query (searches desktop, documents, downloads, pictures, music, videos). open=true opens the first match.",
      {"query": ("str", True, "part of the file name"), "open": ("bool", False, "open the first match")})
def find_file(query, open=False):
    hits = _scan(q=query)[:20]
    if not hits: raise ToolError(f"I couldn't find a file matching '{query}'.")
    if open and Path(hits[0]).suffix.lower() not in EXEC_EXT: _startfile(hits[0])
    return f"Found {len(hits)} match{'es' if len(hits) > 1 else ''}; first is {os.path.basename(hits[0])}.", hits[:8]

@tool("find_latest_file", "Find the most recently modified file of a type, e.g. the latest pdf. open=true opens it.",
      {"ext": ("str", True, "file type like pdf, docx, png"), "folder": ("str", False, "limit to one folder", [k for k in FOLDERS if k != "home"]),
       "open": ("bool", False, "open it")})
def find_latest_file(ext, folder=None, open=False):
    hits = _scan(ext=ext, folder=folder)
    if not hits: raise ToolError(f"I couldn't find any .{ext.lstrip('.')} files.")
    hits.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    if open: _startfile(hits[0])
    return f"The latest is {os.path.basename(hits[0])} in {os.path.dirname(hits[0])}.", hits[:5]

@tool("create_folder", "Create a folder (and any missing parents). Path like 'desktop/Projects'.", {"path": ("str", True, "folder path")})
def create_folder(path):
    p = safe_path(path); existed = p.exists(); p.mkdir(parents=True, exist_ok=True)
    return (f"The folder {p.name} already exists." if existed else f"Created the folder {p.name} in {p.parent.name}."), str(p)

@tool("list_dir", "List what is inside a folder.", {"path": ("str", True, "folder path or name like downloads")})
def list_dir(path):
    p = safe_path(path)
    if not p.is_dir(): raise ToolError(f"{p.name} is not a folder.")
    items = sorted(os.listdir(p))[:60]
    return f"{p.name} has {len(items)} item(s) shown: " + ", ".join(items[:15]), items

@tool("move_path", "Move or rename a file or folder.", {"src": ("str", True, "from"), "dst": ("str", True, "to")},
      confirm=lambda a: f"move {a['src']} to {a['dst']}")
def move_path(src, dst):
    s, d = safe_path(src), safe_path(dst)
    if not s.exists(): raise ToolError(f"{s.name} doesn't exist.")
    if _protected_root(s): raise ToolError("I won't move a main folder.")
    if d.is_dir(): d = d / s.name
    d.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(s), str(d)); return f"Moved {s.name}."

@tool("delete_path", "Delete a file or folder (it is moved to Jarvis_Trash in your home folder, so it can be recovered).", {"path": ("str", True, "path")},
      confirm=lambda a: f"delete {a['path']} (moved to the Jarvis_Trash folder)")
def delete_path(path):
    p = safe_path(path)
    if not p.exists(): raise ToolError(f"{p.name} doesn't exist.")
    if _protected_root(p): raise ToolError("I won't delete a main folder.")
    t = HOME / "Jarvis_Trash"; t.mkdir(exist_ok=True)
    shutil.move(str(p), str(t / (p.name + time.strftime(".%H%M%S")))); return f"Moved {p.name} to Jarvis_Trash."

@tool("read_file", "Read a text file (first 4000 characters).", {"path": ("str", True, "file path")})
def read_file(path):
    p = safe_path(path)
    if not p.is_file(): raise ToolError(f"{p.name} isn't a file.")
    return f"Contents of {p.name}:\n" + p.read_text(errors="replace")[:4000]

@tool("write_file", "Create a text file with the given content (asks first if it would overwrite).", {"path": ("str", True, "file path"), "content": ("str", True, "text")},
      confirm=lambda a: (f"overwrite the existing file {a['path']}" if safe_path_exists(a["path"]) else None))
def write_file(path, content):
    p = safe_path(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, encoding="utf-8"); return f"Saved {p.name}.", str(p)

def safe_path_exists(path):
    try: return safe_path(path).exists()
    except ToolError: return False

# ---------------------------------------------------------------- keyboard / media / screen
def _need_gui():
    if pyautogui is None: raise ToolError("Typing and key presses need the pyautogui package. Run: pip install pyautogui")

@tool("type_text", "Type text into the window that currently has focus. Open the app first and wait 2 seconds.", {"text": ("str", True, "text to type")})
def type_text(text):
    _need_gui(); time.sleep(0.4)
    if text.isascii() and len(text) <= 400:
        pyautogui.write(text, interval=0.01)
    elif pyperclip:
        old = None
        try: old = pyperclip.paste()
        except Exception: pass
        pyperclip.copy(text); pyautogui.hotkey("command" if OS == "Darwin" else "ctrl", "v"); time.sleep(0.4)
        if old is not None:
            try: pyperclip.copy(old)
            except Exception: pass
    else: raise ToolError("Long or non-English text needs the pyperclip package. Run: pip install pyperclip")
    return f"Typed {len(text)} characters."

DANGEROUS_KEYS = {"alt f4", "ctrl alt delete", "ctrl shift esc"}
_KEYFIX = {"control": "ctrl", "windows": "win", "escape": "esc", "return": "enter", "delete": "del", "command": "win" if OS == "Windows" else "command"}
def _keys(k):
    parts = [_KEYFIX.get(p, p) for p in re.split(r"[\s+,]+", k.lower().strip()) if p]
    if not parts or len(parts) > 5 or not all(re.fullmatch(r"[a-z0-9]{1,12}", p) for p in parts): raise ToolError("Those aren't valid keys.")
    return parts

@tool("press_keys", "Press a key or shortcut such as 'enter', 'ctrl s', 'alt tab', 'win d', 'ctrl shift t'.", {"keys": ("str", True, "keys separated by spaces")},
      confirm=lambda a: (f"press {a['keys']}" if " ".join(_keys(a["keys"])) in DANGEROUS_KEYS else None))
def press_keys(keys):
    _need_gui(); parts = _keys(keys)
    pyautogui.hotkey(*parts) if len(parts) > 1 else pyautogui.press(parts[0])
    return "Pressed " + " + ".join(parts) + "."

VK = {"mute": 0xAD, "down": 0xAE, "up": 0xAF, "next": 0xB0, "prev": 0xB1, "stop": 0xB2, "playpause": 0xB3}
def _vkey(name, times=1):
    if OS != "Windows": return False
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(VK[name], 0, 0, 0); ctypes.windll.user32.keybd_event(VK[name], 0, 2, 0)
    return True

@tool("set_volume", "Change system volume: give level 0-100, or direction up, down or mute.",
      {"level": ("int", False, "0-100"), "direction": ("str", False, "up, down or mute", ["up", "down", "mute"])})
def set_volume(level=None, direction=None):
    if level is None and direction is None: raise ToolError("Tell me a volume level or up, down or mute.")
    if OS == "Windows":
        if direction == "mute": _vkey("mute"); return "Toggled mute."
        if direction: _vkey(direction, 5); return f"Turned the volume {direction}."
        _vkey("down", 50); _vkey("up", round(max(0, min(100, level)) / 2)); return f"Set the volume to about {level} percent."
    if OS == "Darwin":
        if direction == "mute": subprocess.run(["osascript", "-e", "set volume with output muted"]); return "Muted."
        cur = int(subprocess.run(["osascript", "-e", "output volume of (get volume settings)"], capture_output=True, text=True).stdout.strip() or 50)
        new = level if level is not None else cur + (10 if direction == "up" else -10)
        subprocess.run(["osascript", "-e", f"set volume output volume {max(0, min(100, new))}"]); return f"Volume is now {max(0, min(100, new))} percent."
    if shutil.which("pactl"):
        if direction == "mute": subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]); return "Toggled mute."
        arg = f"{level}%" if level is not None else ("+10%" if direction == "up" else "-10%")
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", arg]); return "Changed the volume."
    raise ToolError("Volume control isn't supported on this system.")

@tool("media_control", "Media keys: play, pause, next, prev, stop.", {"key": ("str", True, "play, pause, next, prev or stop", ["play", "pause", "next", "prev", "stop"])})
def media_control(key):
    m = {"play": "playpause", "pause": "playpause", "next": "next", "prev": "prev", "stop": "stop"}[key]
    if _vkey(m): return f"Sent {key}."
    if pyautogui:
        pyautogui.press({"playpause": "playpause", "next": "nexttrack", "prev": "prevtrack", "stop": "stop"}[m]); return f"Sent {key}."
    raise ToolError("Media keys aren't supported here.")

@tool("screenshot", "Take a screenshot and save it in Pictures/Jarvis.")
def screenshot():
    _need_gui()
    out = FOLDERS["pictures"] / "Jarvis"; out.mkdir(parents=True, exist_ok=True)
    p = out / time.strftime("screenshot_%Y%m%d_%H%M%S.png"); pyautogui.screenshot(str(p))
    return "Saved a screenshot in Pictures, in the Jarvis folder.", str(p)

# ---------------------------------------------------------------- system
@tool("system_info", "Report battery, CPU, memory, disk and system details.")
def system_info():
    d = {"system": f"{platform.system()} {platform.release()}", "cpu_threads": os.cpu_count()}
    if psutil:
        d["cpu_percent"] = psutil.cpu_percent(interval=0.4)
        m = psutil.virtual_memory(); d["memory"] = f"{m.percent}% of {round(m.total / 2**30)} GB used"
        du = shutil.disk_usage(HOME); d["disk"] = f"{round(du.free / 2**30)} GB free"
        b = psutil.sensors_battery()
        if b: d["battery"] = f"{round(b.percent)}%, {'charging' if b.power_plugged else 'on battery'}"
    txt = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in d.items())
    return txt, d

@tool("get_time", "Get the current date and time.")
def get_time(): return time.strftime("It is %I:%M %p on %A, %d %B %Y."), None

POWER = ["lock", "sleep", "shutdown", "restart", "logoff", "cancel_shutdown"]
@tool("power", "Lock, sleep, shutdown, restart, logoff, or cancel_shutdown.", {"kind": ("str", True, "power action", POWER)},
      confirm=lambda a: {"shutdown": "shut down your laptop", "restart": "restart your laptop", "logoff": "sign you out"}.get(a["kind"]))
def power(kind):
    cmds = {"Windows": {"lock": ["rundll32.exe", "user32.dll,LockWorkStation"], "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                        "shutdown": ["shutdown", "/s", "/t", "10"], "restart": ["shutdown", "/r", "/t", "10"], "logoff": ["shutdown", "/l"], "cancel_shutdown": ["shutdown", "/a"]},
            "Darwin": {"lock": ["pmset", "displaysleepnow"], "sleep": ["pmset", "sleepnow"],
                       "shutdown": ["osascript", "-e", 'tell app "System Events" to shut down'], "restart": ["osascript", "-e", 'tell app "System Events" to restart']},
            "Linux": {"lock": ["loginctl", "lock-session"], "sleep": ["systemctl", "suspend"], "shutdown": ["systemctl", "poweroff"], "restart": ["systemctl", "reboot"]}}[OS if OS in ("Windows", "Darwin") else "Linux"]
    c = cmds.get(kind)
    if not c: raise ToolError("That isn't supported on this system.")
    subprocess.Popen(c, creationflags=NOWIN)
    return {"lock": "Locking your laptop.", "sleep": "Going to sleep.", "shutdown": "Shutting down in 10 seconds. Say cancel shutdown to stop it.",
            "restart": "Restarting in 10 seconds. Say cancel shutdown to stop it.", "logoff": "Signing you out.", "cancel_shutdown": "Shutdown cancelled."}[kind]

@tool("run_script", "Run one of the approved scripts by name (only scripts the user has listed in config).", {"name": ("str", True, "script name")},
      confirm=lambda a: f"run the approved script '{a['name']}'")
def run_script(name):
    cmd = config.ALLOWED_SCRIPTS.get(name)
    if not cmd: raise ToolError(f"'{name}' is not an approved script. Approved: {', '.join(config.ALLOWED_SCRIPTS) or 'none'}.")
    r = subprocess.run(cmd if isinstance(cmd, list) else [cmd], capture_output=True, text=True, timeout=60, creationflags=NOWIN)
    out = (r.stdout or r.stderr or "").strip()[:400]
    if r.returncode != 0: raise ToolError(f"The script '{name}' failed (code {r.returncode}). {out}")
    return f"The script '{name}' finished. {out}".strip()

@tool("wait", "Wait a few seconds (for example after opening an app, before typing).", {"seconds": ("num", True, "1-10")})
def wait(seconds):
    time.sleep(max(0, min(10, seconds))); return f"Waited {seconds:g} seconds."

# ---------------------------------------------------------------- memory tools
@tool("remember", "Remember a preference or fact the user asked you to keep (never passwords).", {"key": ("str", True, "short label"), "value": ("str", True, "the fact")})
def remember(key, value):
    try: memory.remember(key, value)
    except ValueError as e: raise ToolError(str(e))
    return f"I'll remember that {key} is {value}."

@tool("forget", "Forget a remembered fact.", {"key": ("str", True, "label to forget")})
def forget(key):
    if memory.forget(key): return f"Forgot {key}."
    raise ToolError(f"I had nothing saved as {key}.")
