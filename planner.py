"""Rule-based planner.

Turns common (including multi-step) requests into tool calls WITHOUT asking the language model.
This makes everyday commands instant and reliable even on a tiny model. If any part of the sentence
isn't understood, plan() returns None and the Ollama brain takes over.
"""
import re
import memory

VERBS = ("open|launch|start|run|go to|visit|browse|navigate|search|google|look up|look for|find|type|write|dictate|press|hit|play|close|quit|exit|"
         "take|capture|set|turn|volume|brightness|mute|unmute|lock|create|make|list|show|tell|check|what|remind|screenshot|pause|resume|next|skip|"
         "increase|decrease|lower|raise|remember|get|give|shut|restart|reboot|sleep|cancel|switch|minimi[sz]e|change|put")
SPLIT = re.compile(r"\s*[,;]?\s*\b(?:and then|then|and|after that|afterwards|also)\b\s*(?=(?:%s)\b)|\s*[,;]\s*(?=(?:%s)\b)" % (VERBS, VERBS), re.I)
BROWSER = {"chrome": "chrome", "google chrome": "chrome", "edge": "edge", "microsoft edge": "edge", "firefox": "firefox"}
BR_RE = "|".join(sorted(BROWSER, key=len, reverse=True))
SITE_URLS = {"youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com", "github": "https://github.com",
             "wikipedia": "https://www.wikipedia.org", "amazon": "https://www.amazon.in", "whatsapp": "https://web.whatsapp.com",
             "instagram": "https://www.instagram.com", "facebook": "https://www.facebook.com", "twitter": "https://x.com", "x": "https://x.com",
             "linkedin": "https://www.linkedin.com", "netflix": "https://www.netflix.com", "spotify": "https://open.spotify.com",
             "reddit": "https://www.reddit.com", "maps": "https://maps.google.com", "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai"}
SEARCH_SITES = ("youtube", "google", "wikipedia", "github", "amazon", "maps")
APP_FIRST = {"spotify", "whatsapp", "netflix"}              # these have desktop apps; prefer the app when no browser is in play
FOLDERS = "desktop|documents|downloads|pictures|music|videos|home"
EXTS = {"pdf": "pdf", "word": "docx", "docx": "docx", "excel": "xlsx", "xlsx": "xlsx", "powerpoint": "pptx", "pptx": "pptx", "ppt": "pptx",
        "png": "png", "jpg": "jpg", "jpeg": "jpg", "image": "png", "picture": "jpg", "photo": "jpg", "text": "txt", "txt": "txt", "zip": "zip",
        "mp3": "mp3", "song": "mp3", "mp4": "mp4", "video": "mp4", "csv": "csv"}
PRONOUN = re.compile(r"\b(?:open|close|play|start|run|use|do|show|launch|quit|exit|kill|repeat|redo|undo|stop|pause)\s+(?:it|that|this|them|those|these)\b|\bagain\b|\bearlier\b|\bsame\b|\bwhen i\b|\bonce i\b|\buntil\b|\bsomething\b|\banything\b|\beverything\b", re.I)
UNITS = {"second": 1 / 60, "sec": 1 / 60, "minute": 1, "min": 1, "hour": 60, "hr": 60}

def _clean(text):
    t = re.sub(r"^\s*(?:hey |hi |ok |okay )?jarvis[, ]*", "", text.strip(), flags=re.I)
    t = re.sub(r"^(?:please |kindly )?(?:can|could|would|will) you (?:please )?", "", t, flags=re.I)
    t = re.sub(r"^(?:please|i want you to|i need you to|i'd like you to|i would like you to|go ahead and)\s+", "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me|thanks|thank you)\s*[.!?]*\s*$", "", t, flags=re.I)
    return re.sub(r"[.!?]+\s*$", "", t).strip()

def _strip_browser(c, ctx):
    m = re.search(r"\s+(?:in|on|using|with|via)\s+(?:the\s+)?(%s)(?:\s+browser)?$" % BR_RE, c, re.I)
    if m: ctx["browser"] = BROWSER[m.group(1).lower()]; c = c[:m.start()]
    return c.strip()

def _msg(s):
    return re.sub(r"^(?:this|the following|the)\s+(?:message|text|sentence|line)\s*[:,-]?\s*", "", s.strip(), flags=re.I).strip("\"'“”")

def _num(s):
    return float(s)

def _clause(c0, ctx, steps):
    """Parse ONE clause into steps. Returns False if it isn't understood."""
    c = _strip_browser(c0.strip(), ctx); l = c.lower().strip()
    if not l: return False
    add = lambda tool, **a: steps.append((tool, a)) or True
    if PRONOUN.search(l) and not re.match(r"^(?:type|write|dictate|remember|remind)\b", l): return False   # needs conversation context -> the LLM

    # ----- typing
    m = re.match(r"^(?:type|write|dictate)\s+(.+?)\s+(?:in|into|on)\s+(notepad|wordpad|word)$", c, re.I)
    if m: add("open_app", name=m.group(2).lower()); return add("type_text", text=_msg(m.group(1)))
    m = re.match(r"^(?:type|dictate)\s+(.+)$", c, re.I)
    if m: return add("type_text", text=_msg(m.group(1)))
    # ----- memory / reminders
    m = re.match(r"^remember (?:that )?(?:my )?(.+?)\s+(?:is|are|=)\s+(.+)$", c, re.I)
    if m: return add("remember", key=m.group(1).strip(), value=m.group(2).strip())
    m = re.match(r"^remind me (?:in|after)\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\s*(?:to|about|that)?\s*(.*)$", c, re.I)
    if not m: m = re.match(r"^set (?:a )?(?:timer|reminder|alarm) (?:for|of)\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\s*(?:to|for|about)?\s*(.*)$", c, re.I)
    if m:
        mins = _num(m.group(1)) * UNITS[re.sub(r"s$", "", m.group(2).lower())]
        return add("set_timer", minutes=mins, label=m.group(3).strip())
    # ----- volume / brightness / media / power
    m = re.match(r"^(?:(?:set|turn|change|put)\s+)?(?:the\s+)?volume\s+(?:to\s+|at\s+)?(\d{1,3})\s*(?:%|percent)?$", l)
    if m: return add("set_volume", level=int(m.group(1)))
    if re.match(r"^(?:turn\s+)?(?:the\s+)?volume\s+up$|^(?:increase|raise)\s+(?:the\s+)?volume$|^louder$", l): return add("set_volume", direction="up")
    if re.match(r"^(?:turn\s+)?(?:the\s+)?volume\s+down$|^(?:decrease|lower|reduce)\s+(?:the\s+)?volume$|^quieter$", l): return add("set_volume", direction="down")
    if re.match(r"^(?:un)?mute(?:\s+(?:the\s+)?(?:sound|volume|laptop|audio))?$", l): return add("set_volume", direction="mute")
    m = re.match(r"^(?:(?:set|turn|change|put)\s+)?(?:the\s+)?(?:screen\s+)?brightness\s+(?:to\s+|at\s+)?(\d{1,3})\s*(?:%|percent)?$", l)
    if m: return add("set_brightness", level=int(m.group(1)))
    if re.match(r"^(?:pause|resume|play|stop)(?:\s+(?:the\s+)?(?:music|song|video|media|playback))?$", l) and l != "stop":
        return add("media_control", key="pause" if l.startswith("pause") else "play")
    if re.match(r"^(?:next|skip)(?:\s+(?:the\s+)?(?:song|track))?$", l): return add("media_control", key="next")
    if re.match(r"^(?:previous|last)\s+(?:song|track)$", l): return add("media_control", key="prev")
    if re.match(r"^(?:take\s+(?:a\s+)?|capture\s+(?:the\s+)?)?screenshot$|^(?:take|capture)\s+(?:a\s+)?screen\s?shot$", l): return add("screenshot")
    if re.match(r"^lock(?:\s+(?:the\s+)?(?:laptop|pc|computer|screen))?$", l): return add("power", kind="lock")
    if re.match(r"^(?:go to sleep|sleep|put (?:the )?(?:laptop|pc|computer) to sleep)$", l): return add("power", kind="sleep")
    if re.match(r"^(?:shut ?down|turn off)(?:\s+(?:the\s+)?(?:laptop|pc|computer))?$", l): return add("power", kind="shutdown")
    if re.match(r"^(?:restart|reboot)(?:\s+(?:the\s+)?(?:laptop|pc|computer))?$", l): return add("power", kind="restart")
    if re.match(r"^cancel\s+(?:the\s+)?(?:shutdown|restart)$", l): return add("power", kind="cancel_shutdown")
    m = re.match(r"^(?:press|hit)\s+([a-z0-9+ ]{1,30})$", l)
    if m: return add("press_keys", keys=m.group(1))
    if re.match(r"^(?:show\s+(?:the\s+)?desktop|minimi[sz]e\s+(?:all|everything))$", l): return add("press_keys", keys="win d")
    if re.match(r"^switch\s+(?:the\s+)?(?:window|app)s?$", l): return add("press_keys", keys="alt tab")

    # ----- info
    if re.match(r"^(?:what(?:'s| is)?\s+|get\s+(?:me\s+)?|tell me\s+|give me\s+|show\s+(?:me\s+)?)?(?:the\s+)?(?:current\s+)?(?:time|date)(?:\s+(?:is it|now|today))?$|^what\s+(?:day|time)\s+is\s+it(?:\s+today)?$", l): return add("get_time")
    if re.match(r"^(?:show\s+|check\s+|give me\s+|tell me\s+)?(?:my\s+|the\s+)?(?:system\s+(?:info|status|stats)|battery(?:\s+(?:level|status|percentage))?|cpu(?:\s+usage)?|memory(?:\s+usage)?|ram(?:\s+usage)?)$|^how(?:'s| is) my (?:laptop|pc|computer|system)(?: doing)?$", l):
        return add("system_info")
    m = re.match(r"^(?:what(?:'s| is)\s+)?(?:the\s+)?weather(?:\s+(?:like\s+)?(?:in|for|at)\s+(.+?))?(?:\s+(?:today|now|right now))?$", l)
    if m:
        city = (m.group(1) or "").strip() or memory.fact("city", "location", "home city")
        return add("weather", city=city) if city else False
    if re.match(r"^(?:list|show|tell me|give me|what|which)\b.*\b(?:apps|applications|programs)\b", l):
        q = re.search(r"\b(?:with|containing|named|called|matching|like)\s+[\"']?(\w+)", l)
        return add("list_apps", query=q.group(1) if q else "")
    if m: return add("list_apps", query=(m.group(1) or "").strip())

    # ----- folders & files
    m = re.match(r"^(?:create|make)\s+(?:a\s+|an\s+)?(?:new\s+)?folder\s+(?:named\s+|called\s+|with the name\s+)?[\"'“]?(.+?)[\"'”]?(?:\s+(?:on|in|inside|under)\s+(?:my\s+|the\s+)?(%s)(?:\s+folder)?)?$" % FOLDERS, c, re.I)
    if m: return add("create_folder", path=f"{(m.group(2) or 'desktop').lower()}/{m.group(1).strip()}")
    m = re.match(r"^(?:open|show)\s+(?:my\s+|the\s+)?(%s)(?:\s+folder)?$" % FOLDERS, l)
    if m: return add("open_folder", name=m.group(1))
    m = re.match(r"^(?:find|open|show|get)\s+(?:me\s+)?(?:my\s+|the\s+)?(?:latest|newest|most recent|last)\s+(?:downloaded\s+)?(\w+)(?:\s+file)?(?:\s+(?:in|from)\s+(?:my\s+)?(%s))?$" % FOLDERS[:-5], l)
    if m and m.group(1) in EXTS:
        a = {"ext": EXTS[m.group(1)], "open": l.startswith("open")}
        if m.group(2): a["folder"] = m.group(2)
        return add("find_latest_file", **a)
    m = re.match(r"^open\s+file\s+(?:named\s+|called\s+)?(.+)$", l)
    if m: return add("find_file", query=m.group(1), open=True)
    m = re.match(r"^(?:find|locate|search for)\s+(?:the\s+|my\s+)?file\s+(?:named\s+|called\s+)?(.+)$", l)
    if m: return add("find_file", query=m.group(1))

    # ----- web
    m = re.match(r"^(?:open|launch|start)\s+(?:the\s+)?(%s)(?:\s+browser)?$" % BR_RE, l)
    if m: ctx["browser"] = BROWSER[m.group(1)]; return add("open_app", name=m.group(1))
    m = re.match(r"^(?:open|go to|visit|browse(?: to)?|navigate to|take me to)\s+(?:the\s+)?(?:website\s+)?(%s)(?:\.com)?(?:\s+(?:website|site))?$" % "|".join(SITE_URLS), l)
    if m:
        site = m.group(1)
        if site in APP_FIRST and not ctx["browser"]: ctx["opened"] = site; return add("open_app", name=site)
        ctx["site"] = site; return add("open_url", url=SITE_URLS[site], **({"browser": ctx["browser"]} if ctx["browser"] else {}))
    m = re.match(r"^(?:open|go to|visit|browse(?: to)?)\s+((?:https?://)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?)$", l)
    if m: return add("open_url", url=m.group(1), **({"browser": ctx["browser"]} if ctx["browser"] else {}))
    m = re.match(r"^(?:search|google|look up|look for)\s+(?:for\s+)?(.+?)(?:\s+(?:on|in)\s+(%s))?$" % "|".join(SEARCH_SITES), c, re.I)
    if m:
        site = (m.group(2) or ctx["site"] or "google").lower()
        a = {"query": m.group(1).strip("\"'“”"), "site": site if site in SEARCH_SITES else "google"}
        if ctx["browser"]: a["browser"] = ctx["browser"]
        return add("web_search", **a)
    m = re.match(r"^play\s+(.+?)(?:\s+on\s+youtube)?$", c, re.I)
    if m and not re.search(r"\bon\s+spotify\b", l):
        a = {"query": m.group(1).strip("\"'“”"), "site": "youtube"}
        if ctx["browser"]: a["browser"] = ctx["browser"]
        return add("web_search", **a)

    # ----- apps
    m = re.match(r"^(?:close|quit|exit|kill)\s+(?:the\s+)?(.+?)(?:\s+(?:app|application|window|program))?$", l)
    if m and len(m.group(1).split()) <= 3: return add("close_app", name=m.group(1))
    m = re.match(r"^(?:open|launch|start|run)\s+(?:the\s+)?(.+?)(?:\s+(?:app|application|program))?$", l)
    if m and len(m.group(1).split()) <= 4 and not re.search(r"\b(file|folder|my|mode|command|script)\b", m.group(1)):
        ctx["opened"] = m.group(1); return add("open_app", name=m.group(1))
    return False

def _tidy(steps):
    """Remove redundant steps and add short waits where an app must finish opening first."""
    out = list(steps)
    # opening a browser is pointless if a later step opens a page in that same browser
    for i, (t, a) in enumerate(out):
        if t == "open_app" and a["name"] in BROWSER:
            b = BROWSER[a["name"]]
            if any(t2 in ("open_url", "web_search") and a2.get("browser") == b for t2, a2 in out[i + 1:]): out[i] = None
    out = [s for s in out if s]
    # "visit youtube" immediately followed by "search ... on youtube" -> just search
    res = []
    for i, (t, a) in enumerate(out):
        nxt = out[i + 1] if i + 1 < len(out) else None
        if t == "open_url" and nxt and nxt[0] == "web_search" and a["url"] == SITE_URLS.get(nxt[1]["site"]): continue
        res.append((t, a))
    final = []
    for i, (t, a) in enumerate(res):
        final.append((t, a))
        nxt = res[i + 1] if i + 1 < len(res) else None
        if t == "open_app" and nxt and nxt[0] in ("type_text", "press_keys"): final.append(("wait", {"seconds": 2.5}))
    return final

def plan(text):
    """Return a list of (tool, args) or None if the request needs the language model."""
    if not text or len(text) > 400: return None
    t = _clean(text)
    parts = [p for p in SPLIT.split(t) if p and p.strip()]
    if not parts or len(parts) > 6: return None
    ctx = {"browser": None, "site": None, "opened": None}; steps = []
    for p in parts:
        if not _clause(p, ctx, steps): return None
    steps = _tidy(steps)
    return steps or None
