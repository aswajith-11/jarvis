#!/usr/bin/env python3
"""JARVIS local laptop agent.

Runs on YOUR laptop, listens on 127.0.0.1 only, and requires a secret token on every request.
The website sends it requests; the local Ollama model (ai_brain.py) plans, and tools.py acts.
"""
import json, hmac, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import config, tools, memory, ai_brain

TOKEN = config.get_token()
BUSY = threading.Lock()
MAX_BODY = 64 * 1024

def log(*a):
    import time; print(time.strftime("%H:%M:%S"), *a, flush=True)

def handle(req):
    a = req.get("action", "")
    if a in ("think", "confirm"):
        if not BUSY.acquire(blocking=False): return {"message": "I'm still working on the previous request."}
        try:
            return ai_brain.think(str(req.get("text", ""))[:2000]) if a == "think" else ai_brain.confirm(bool(req.get("approve")))
        finally: BUSY.release()
    if a == "stop":
        ai_brain.STOP.set(); return {"message": "Stopping."}
    if a == "tool":                                   # direct, already-validated quick command from the website
        name, args = str(req.get("name", "")), req.get("args") or {}
        ai_brain.set_state("executing", name.replace("_", " "))
        try:
            res = tools.execute(name, args, confirmed=bool(req.get("confirm")))
        finally: ai_brain.set_state("idle")
        if res["ok"]: memory.log_action(name, args if isinstance(args, dict) else {}, True, res["message"])
        return res
    if a == "memory":
        op = req.get("op")
        if op == "forget": memory.forget(str(req.get("key", "")))
        elif op == "clear": memory.clear(str(req.get("scope", "all")))
        return {"memory": memory.snapshot(), "message": "Done."}
    if a == "refresh_apps":
        return {"message": f"Indexed {tools.build_index()} apps."}
    return {"message": "Unknown action."}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _origin_ok(self):
        o = self.headers.get("Origin", "")
        if not o: return ""
        ok = (o == "null" or o.startswith("http://localhost") or o.startswith("http://127.0.0.1")
              or (o.startswith("https://") and o.endswith(".github.io")) or o in config.ALLOWED_ORIGINS)
        return o if ok else None

    def _host_ok(self):                               # blocks DNS-rebinding attacks
        return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

    def _send(self, code, obj=None):
        o = self._origin_ok(); self.send_response(code)
        if o: self.send_header("Access-Control-Allow-Origin", o); self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Jarvis-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Type", "application/json")
        body = json.dumps(obj or {}).encode(); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _auth(self):
        if not self._host_ok() or self._origin_ok() is None: self._send(403, {"error": "forbidden"}); return False
        if not hmac.compare_digest(self.headers.get("X-Jarvis-Token", ""), TOKEN): self._send(401, {"error": "bad token"}); return False
        return True

    def do_OPTIONS(self):
        if not self._host_ok() or self._origin_ok() is None: return self._send(403, {"error": "forbidden"})
        self._send(204)

    def do_GET(self):
        if not self._auth(): return
        if self.path == "/ping":
            self._send(200, {"ok": True, "os": config.OS, "gui": tools.pyautogui is not None, "brain": ai_brain.status(), "memory": memory.snapshot()})
        elif self.path == "/state":                    # polled by the website: orb state, live stats, due reminders
            self._send(200, {**ai_brain.STATE, "stats": tools.stats(), "alerts": tools.pop_alerts()})
        else: self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth(): return
        if self.path != "/do": return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BODY: return self._send(413, {"error": "too large"})
            req = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(req, dict): raise ValueError("bad request")
            log("REQUEST", req.get("action"), str(req.get("text") or req.get("name") or "")[:80])
            self._send(200, handle(req))
        except Exception as e:
            log("ERROR", e); ai_brain.set_state("idle"); self._send(200, {"message": f"That failed: {e}"})

def main():
    try:
        server = ThreadingHTTPServer(("127.0.0.1", config.PORT), H)
    except OSError:
        print(f"\n Port {config.PORT} is already in use. JARVIS is probably already running in another window.")
        print(" Close that window (or just use the Jarvis website, it is already connected).")
        return False
    n = tools.build_index()
    st = ai_brain.status()
    print("=" * 62)
    print(" JARVIS LAPTOP AGENT  -", config.OS)
    print(f" Listening on http://127.0.0.1:{config.PORT}  (this laptop only)")
    print(f" Apps found: {n}    Keyboard control: {'yes' if tools.pyautogui else 'NO - pip install pyautogui'}")
    if not st["ollama"]: print(f" AI brain: Ollama NOT running - start the Ollama app (model: {config.MODEL})")
    elif not st["ready"]: print(f" AI brain: Ollama is running but model missing - run: ollama pull {config.MODEL}")
    else: print(f" AI brain: Ollama ready, model {config.MODEL}")
    print("\n YOUR SECRET TOKEN (paste into the Jarvis website, Laptop panel):\n")
    print("    ", TOKEN, "\n")
    pair = config.SITE_URL.rstrip("/") + "/#token=" + TOKEN
    print(" One-click link (opens Jarvis already connected):\n    ", pair, "\n")
    print(" Never share this token or put it on GitHub. Press Ctrl+C to stop.")
    print("=" * 62)
    if config.AUTO_OPEN:
        threading.Timer(1.2, lambda: webbrowser.open(pair)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print("Bye.")
    return True


if __name__ == "__main__":
    main()
