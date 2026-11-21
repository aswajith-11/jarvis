"""JARVIS configuration. Override anything via environment variables or ~/.jarvis/config.json."""
import os, json, secrets, platform
from pathlib import Path

OS = platform.system()                       # Windows / Darwin / Linux
HOME = Path.home()
DATA_DIR = Path(os.environ.get("JARVIS_HOME", HOME / ".jarvis"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_defaults = {
    "port": 8765,
    "ollama_url": "http://127.0.0.1:11434",
    "model": "llama3.2:1b",          # upgrade later, e.g. "llama3.2:3b" or "qwen2.5:7b"
    "max_steps": 8,                  # max tool calls for one request
    "num_ctx": 4096,
    "llm_timeout": 180,              # seconds to wait for Ollama
    "allowed_origins": [],           # extra web origins allowed to talk to the agent
    "allowed_roots": [],             # extra folders JARVIS may read/write (your home folder is always allowed)
    # Scripts the AI may run BY NAME, always after you confirm. Example:
    # "backup": ["C:\\Users\\you\\scripts\\backup.bat"]
    "allowed_scripts": {},
}
_user = {}
_f = DATA_DIR / "config.json"
if _f.exists():
    try: _user = json.loads(_f.read_text(encoding="utf-8"))
    except Exception: print("Warning: could not read", _f)
_cfg = {**_defaults, **_user}

PORT = int(os.environ.get("JARVIS_PORT", _cfg["port"]))
OLLAMA_URL = os.environ.get("OLLAMA_URL", _cfg["ollama_url"]).rstrip("/")
MODEL = os.environ.get("JARVIS_MODEL", _cfg["model"])
MAX_STEPS = int(_cfg["max_steps"])
NUM_CTX = int(_cfg["num_ctx"])
LLM_TIMEOUT = int(_cfg["llm_timeout"])
ALLOWED_ORIGINS = list(_cfg["allowed_origins"])
ALLOWED_SCRIPTS = dict(_cfg["allowed_scripts"])
_roots = [HOME] + [Path(p) for p in _cfg["allowed_roots"]]
ALLOWED_ROOTS = [r.resolve() for r in _roots if r.exists()]
# Folders the AI can never touch, even inside the home folder (browser passwords, SSH keys, this app's token...)
BLOCKED_PARTS = {".ssh", ".jarvis", ".aws", ".gnupg", "appdata", ".config", "library"}

def get_token():
    """Secret token the website must send. Lives only on this laptop, never in the repo."""
    f = DATA_DIR / "token"
    old = HOME / ".jarvis_token"
    if f.exists() and f.read_text().strip():
        return f.read_text().strip()
    t = old.read_text().strip() if old.exists() and old.read_text().strip() else secrets.token_urlsafe(16)
    f.write_text(t)
    try: os.chmod(f, 0o600)
    except Exception: pass
    return t
