#!/usr/bin/env python3
"""Builds the Free My TV web home screen for the lane-1 bridge (server/vidaa_server.py).

    git clone https://github.com/felipericardo/tv-launcher ../tv-launcher   # tested at f2d984c (MIT)
    cp tools/fmtv-lane1/config.example.json tools/fmtv-lane1/config.json    # your city, language, shelf
    python3 tools/fmtv-lane1/build.py                                        # -> launcher/fmtv/
    curl "http://127.0.0.1:8765/api/open?url=http://<this-host>:8765/fmtv/"

From upstream web/, with:
  - tv.js   <- tv-vidaa.js (apps, inputs, launches and deep links over the bridge's WebSocket);
  - home.js <- home.js here, a maintained fork: tabs per focused app (GET /api/feed, server/feeds.py) plus
               "Direct TV" (GET /api/tv) and "Reprendre" (GET/POST /api/history, server/tvguide.py), one large
               row centred on the focused tile, an info sheet on OK that opens the title in its app;
  - rows.css appended to home.css. An optional rugby.js/rugby.css next to this file is picked up if present.
The TMDB key stays on the bridge (server/keys/tmdb.key): the page has none, so upstream's own picks are off.
After a rebuild: curl http://127.0.0.1:8765/api/reload  (the page reloads itself on the TV).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FMTV = os.environ.get("FMTV_SRC") or os.path.join(os.path.dirname(REPO), "tv-launcher")
OUT = os.path.join(REPO, "launcher", "fmtv")

if not os.path.isdir(os.path.join(FMTV, "web")):
    sys.exit("Free My TV sources not found at %s (clone felipericardo/tv-launcher there or set FMTV_SRC)" % FMTV)
sys.path.insert(0, os.path.join(FMTV, "tools"))
import webapp  # noqa: E402

cfg_path = os.path.join(HERE, "config.json")
if not os.path.exists(cfg_path):
    cfg_path = os.path.join(HERE, "config.example.json")
with open(cfg_path, encoding="utf-8") as f:
    CONFIG = json.load(f)
CONFIG["tmdbKey"] = ""          # kept server-side (feeds.py), never in the page


def read(name):
    with open(os.path.join(HERE, name), "rb") as f:
        return f.read()


def patch(name, old, new):
    """Exact, single replacement in an upstream file: fails loudly if upstream changed."""
    text = files[name].decode("utf-8")
    if text.count(old) != 1:
        sys.exit("%s: anchor not found exactly once: %r" % (name, old[:60]))
    files[name] = text.replace(old, new).encode("utf-8")


files = webapp.files(CONFIG, "tools/fmtv-lane1/build.py")
files["tv.js"] = read("tv-vidaa.js")
files["home.js"] = read("home.js")
files["home.css"] += read("rows.css")
if os.path.exists(os.path.join(HERE, "rugby.js")):
    files["rugby.js"] = read("rugby.js")
    files["home.css"] += read("rugby.css")
    patch("index.html", '<script src="home.js"></script>', '<script src="rugby.js"></script>\n<script src="home.js"></script>')
webapp.preview(files, OUT)
print("%d files -> %s (config: %s)" % (len(files), OUT, os.path.basename(cfg_path)))
