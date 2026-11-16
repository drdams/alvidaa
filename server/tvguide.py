"""Direct TV and Reprendre for the Free My TV home screen.

GET /api/tv       -> {"ok", "channels": [{id, name, logo, now, next, tonight}]}
    from the free xmltvfr.fr TNT guide (TNT + Canal+ channels), downloaded at most every 6 h into
    cache/tnt.xml.gz and parsed once per download. now/next/tonight are worked out per request.
GET /api/history  -> {"ok", "items": [...]}   (the programmes opened from the home screen, newest first)
POST /api/history  body: one item {id, title, image, meta, overview, deeplink, app} -> adds it (max 30)
"""
import gzip
import json
import os
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
GUIDE_URL = "https://xmltvfr.fr/xmltv/xmltv_tnt.xml.gz"
GUIDE_FILE = os.path.join(CACHE, "tnt.xml.gz")
GUIDE_TTL = 6 * 3600
HISTORY_FILE = os.path.join(CACHE, "history.json")
HISTORY_MAX = 30

_lock = threading.Lock()
_guide = {"at": 0, "channels": [], "progs": {}}


def _epoch(stamp):
    """'20261115055000 +0100' -> seconds since the epoch."""
    try:
        t = time.strptime(stamp[:14], "%Y%m%d%H%M%S")
        off = stamp[15:].strip() or "+0000"
        sign = -1 if off[0] == "-" else 1
        offset = sign * (int(off[1:3]) * 3600 + int(off[3:5]) * 60)
        import calendar
        return calendar.timegm(t) - offset
    except (ValueError, IndexError):
        return 0


def _download():
    os.makedirs(CACHE, exist_ok=True)
    fresh = os.path.exists(GUIDE_FILE) and time.time() - os.path.getmtime(GUIDE_FILE) < GUIDE_TTL
    if not fresh:
        try:
            req = urllib.request.Request(GUIDE_URL, headers={"User-Agent": "alvidaa-tvguide/1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(30 * 1024 * 1024)
            tmp = GUIDE_FILE + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, GUIDE_FILE)
        except Exception:
            if not os.path.exists(GUIDE_FILE):
                raise
    return os.path.getmtime(GUIDE_FILE)


def _parse():
    channels, progs = [], {}
    with gzip.open(GUIDE_FILE) as f:
        root = ET.parse(f).getroot()
    for c in root.findall("channel"):
        icon = c.find("icon")
        channels.append({"id": c.get("id"), "name": c.findtext("display-name") or c.get("id"),
                         "logo": icon.get("src") if icon is not None else ""})
    for p in root.findall("programme"):
        icon = p.find("icon")
        cats = [x.text for x in p.findall("category") if x.text]
        progs.setdefault(p.get("channel"), []).append({
            "start": _epoch(p.get("start") or ""), "stop": _epoch(p.get("stop") or ""),
            "title": p.findtext("title") or "", "sub": p.findtext("sub-title") or "",
            "desc": p.findtext("desc") or "", "cat": cats[0] if cats else "",
            "image": icon.get("src") if icon is not None else ""})
    for lst in progs.values():
        lst.sort(key=lambda x: x["start"])
    return channels, progs


def _tonight(lst, now):
    """The evening's main programme: the first of 40 min or more starting 20:50-21:30 (tomorrow's after 23:00)."""
    lt = time.localtime(now)
    day = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + (1 if lt.tm_hour >= 23 else 0), 0, 0, 0, 0, 0, -1))
    lo, hi = day + 20 * 3600 + 50 * 60, day + 21 * 3600 + 30 * 60
    return next((p for p in lst if lo <= p["start"] <= hi and p["stop"] - p["start"] >= 40 * 60), None)


def guide():
    with _lock:
        try:
            mtime = _download()
            if mtime != _guide["at"]:
                _guide["channels"], _guide["progs"] = _parse()
                _guide["at"] = mtime
        except Exception as e:
            if not _guide["channels"]:
                return {"ok": False, "error": str(e), "channels": []}
        now = time.time()
        out = []
        for c in _guide["channels"]:
            lst = _guide["progs"].get(c["id"], [])
            cur = next((p for p in lst if p["start"] <= now < p["stop"]), None)
            nxt = next((p for p in lst if p["start"] >= now), None)
            ton = _tonight(lst, now)
            out.append(dict(c, now=cur, next=nxt, tonight=ton if ton is not cur else None))
        return {"ok": True, "channels": out}


# MARK: - Reprendre: what was opened from the home screen (no playback progress: the apps keep that).

def history():
    try:
        with open(HISTORY_FILE) as f:
            return {"ok": True, "items": json.load(f)}
    except (OSError, ValueError):
        return {"ok": True, "items": []}


def add_history(item):
    if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
        return {"ok": False, "error": "id and title required"}
    keep = ("id", "title", "image", "meta", "overview", "deeplink", "app", "kind")
    clean = {k: str(item.get(k) or "")[:2000] for k in keep}
    clean["at"] = int(time.time())
    with _lock:
        items = [i for i in history()["items"] if i.get("id") != clean["id"]]
        items.insert(0, clean)
        os.makedirs(CACHE, exist_ok=True)
        tmp = HISTORY_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(items[:HISTORY_MAX], f, ensure_ascii=False)
        os.replace(tmp, HISTORY_FILE)
    return {"ok": True}
