#!/usr/bin/env python3
"""
JARVIS launcher.   Run it with:      python jarvis.py
(on Windows you can also double-click it, or use:  py jarvis.py)

It installs the few packages it needs, starts the laptop agent, and opens the Jarvis website
already connected to your laptop. Keep this window open while you use Jarvis.
"""
import sys, os, subprocess, importlib, importlib.util, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

NEEDED = {"pyautogui": "pyautogui", "pyperclip": "pyperclip", "psutil": "psutil", "PIL": "pillow"}

def ensure_packages():
    missing = [pkg for mod, pkg in NEEDED.items() if importlib.util.find_spec(mod) is None]
    if not missing or os.environ.get("JARVIS_SKIP_INSTALL"): return
    print("First run: installing", ", ".join(missing), "...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--retries", "1", "--timeout", "10", *missing])
    if r.returncode != 0:
        print("Could not install them (no internet?). Jarvis will still start, but typing and keyboard control may not work.")
    importlib.invalidate_caches()

def main():
    if sys.version_info < (3, 9):
        print("JARVIS needs Python 3.9 or newer. Download it from python.org"); return False
    ensure_packages()
    import agent
    return agent.main()

if __name__ == "__main__":
    ok = False
    try:
        ok = main()
    except KeyboardInterrupt:
        ok = True
    except Exception:
        traceback.print_exc()
        print("\nSomething went wrong. Copy the message above and send it to me.")
    if not ok:
        try: input("\nPress Enter to close this window...")
        except EOFError: pass
