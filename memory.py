"""Local memory for JARVIS: recent conversation, remembered facts, recent actions.
Stored only on this laptop (~/.jarvis/memory.json). Passwords and similar are never stored."""
import json, re, time, threading, copy, os
import config

FILE = config.DATA_DIR / "memory.json"
LOCK = threading.RLock()
SENSITIVE = re.compile(r"(password|passwd|passcode|\botp\b|\bpin\b|cvv|card number|secret|api[ _-]?key|token|\b\d{12,19}\b)", re.I)
NO_ARGS = {"type_text", "write_file", "run_script", "remember"}   # never keep the content of these in the action log
_state = None

def _load():
    global _state
    if _state is None:
        try: _state = json.loads(FILE.read_text(encoding="utf-8"))
        except Exception: _state = {}
        for k, v in {"history": [], "facts": {}, "actions": []}.items(): _state.setdefault(k, v)
    return _state

def _save():
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_state, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, FILE)

def is_sensitive(text): return bool(SENSITIVE.search(text or ""))

def add_turn(user, assistant):
    with LOCK:
        s = _load()
        s["history"] += [{"role": "user", "content": "[redacted]" if is_sensitive(user) else user[:500]},
                         {"role": "assistant", "content": assistant[:500]}]
        s["history"] = s["history"][-24:]; _save()

def history(n=5):
    with LOCK: return copy.deepcopy(_load()["history"][-2 * n:])

def remember(key, value):
    key, value = key.strip().lower()[:60], value.strip()[:300]
    if not key or not value: raise ValueError("Nothing to remember.")
    if is_sensitive(key + " " + value): raise ValueError("I don't store passwords or other sensitive information.")
    with LOCK: _load()["facts"][key] = value; _save()

def forget(key):
    with LOCK:
        f = _load()["facts"]; hit = [k for k in f if k == key.strip().lower()]
        for k in hit: del f[k]
        _save(); return bool(hit)

def clear(scope="all"):
    with LOCK:
        s = _load()
        if scope in ("all", "history"): s["history"] = []
        if scope in ("all", "facts"): s["facts"] = {}
        if scope in ("all", "actions"): s["actions"] = []
        _save()

def log_action(tool, args, ok, message):
    a = {} if tool in NO_ARGS else {k: v for k, v in args.items() if not is_sensitive(str(v))}
    with LOCK:
        s = _load(); s["actions"].append({"t": time.strftime("%H:%M"), "tool": tool, "args": a, "ok": ok, "msg": message[:120]})
        s["actions"] = s["actions"][-30:]; _save()

def context_text():
    """Short text given to the AI so follow-ups like 'open it again' work."""
    with LOCK:
        s = _load(); out = []
        if s["facts"]: out.append("Things the user asked you to remember: " + "; ".join(f"{k}: {v}" for k, v in s["facts"].items()))
        if s["actions"]:
            out.append("Your recent actions (newest last): " + "; ".join(
                f"{a['tool']}({', '.join(str(v) for v in a['args'].values())}) {'ok' if a['ok'] else 'failed'}" for a in s["actions"][-6:]))
        return "\n".join(out)

def fact(*keys):
    """First remembered value among these keys, or ''."""
    with LOCK:
        f = _load()["facts"]
        return next((f[k] for k in keys if k in f), "")

def snapshot():
    with LOCK:
        s = _load(); return {"facts": dict(s["facts"]), "actions": s["actions"][-15:], "turns": len(s["history"]) // 2}
