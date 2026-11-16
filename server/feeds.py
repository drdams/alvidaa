"""Rows of picks per app for the Free My TV home screen (GET /api/feed?app=<name>).

Each app name maps to one or two rows: {"ok", "app", "rows": [{"title", "items": [...]}]}.
An item: {id, title, image (16:9), meta, year, overview, kind, rating, deeplink?}.

Sources, per app (French catalogues, as Catch-up TV & More reads them, plus TMDB):
  CANAL+       TMDB (its own catalogue API answers 403 to scripts): recent films / series on CANAL+ providers
  france.tv    its TV home page (api-mobile.yatta.francetv.fr)           deep links verified on an M2 Pro
  TF1+         tf1.fr public GraphQL program list                        deep links verified on an M2 Pro
  M6+          6play middleware folders (pictures shrunk here, ffmpeg)   deep links verified on an M2 Pro
  ARTE, Prime  TMDB
The TMDB key lives in keys/tmdb.key and is never sent to the page. Answers are cached 6 h in memory and in
cache/feeds.json, so a restart or a network outage still shows the last rows.
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(HERE, "keys", "tmdb.key")
CACHE_FILE = os.path.join(HERE, "cache", "feeds.json")
TTL = 6 * 3600
PER_ROW = 30

TMDB = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/"
REGION, LANG = "FR", "fr-FR"

# CANAL+ and the catalogues of its Ciné Séries offer (TMDB FR ids, checked 16/11/2026).
CANAL = "381|345|1899|350|531|2303"


def _discover(kind, providers, sort, extra=""):
    return ("/discover/%s?language=%s&watch_region=%s&with_watch_monetization_types=flatrate"
            "&include_adult=false&with_watch_providers=%s&sort_by=%s%s"
            % (kind, LANG, REGION, urllib.parse.quote(providers), sort, extra))


def _days(n):
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + n * 86400))


# App name (lowercase, as the TV lists it) -> rows: (title, [(kind, discover path), ...]).
# Several paths in one row are interleaved (films and series mixed).
def _rows(app):
    if app == "canal+":
        # "Nouveautés": CANAL+'s own catalogue API is behind an anti-bot wall, so TMDB stands in: films
        # released in the last 18 months, series with an episode in the last 4 months, now on CANAL+.
        return [
            ("Films", [("movie", _discover("movie", CANAL, "popularity.desc",
                                           "&primary_release_date.gte=%s&primary_release_date.lte=%s&vote_count.gte=20"
                                           % (_days(-540), _days(0))))]),
            ("Séries", [("tv", _discover("tv", CANAL, "popularity.desc",
                                         "&air_date.gte=%s&air_date.lte=%s&vote_count.gte=10" % (_days(-120), _days(0))))]),
        ]
    if app == "prime video":
        return [("Populaires", [
            ("movie", _discover("movie", "119", "popularity.desc", "&vote_count.gte=50")),
            ("tv", _discover("tv", "119", "popularity.desc", "&vote_count.gte=30"))])]
    news = {"arte": "234", "tf1+": "1754", "m6+": "147"}
    if app in news:
        p = news[app]
        return [("Nouveautés", [
            ("movie", _discover("movie", p, "primary_release_date.desc",
                                "&primary_release_date.lte=%s&vote_count.gte=5" % _days(0))),
            ("tv", _discover("tv", p, "first_air_date.desc",
                             "&first_air_date.lte=%s&vote_count.gte=3" % _days(0)))])]
    return []


# MARK: - france.tv: its own TV home page (api-mobile.yatta.francetv.fr, as Catch-up TV & More reads it).
# Deep links: the VIDAA app reads ?deeplink=page/program/<program_path> or page/unit/<video id>
# (DeeplinkHelper in its app bundle, "hisense" case: window.location.search).

FTV_HOME = "https://api-mobile.yatta.francetv.fr/generic/homepage?platform=apps_tv"
FTV_APP = "https://hisense-smart-tv.yatta.francetv.fr/"
FTV_ROWS = [("Sélection", "Notre sélection"), ("Top 10", "Top 10 du moment")]


def _http_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "alvidaa-feeds/1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def _ftv_image(images):
    by = {i.get("type"): i.get("urls") or {} for i in images or []}
    for t in ("background_16x9", "vignette_16x9", "lt_16x9"):
        u = by.get(t) or {}
        for w in ("w:1024", "w:800", "w:1280", "w:2500"):
            if u.get(w):
                return u[w]
    return ""


def _lab(v):
    """A label from a {label: ...} object or a plain string."""
    if isinstance(v, dict):
        return v.get("label") or ""
    return v if isinstance(v, str) else ""


def _ftv_item(x):
    image = _ftv_image(x.get("images"))
    if not image:
        return None
    kind = x.get("type") or ""
    title = x.get("label") or x.get("title") or ""
    if kind == "program" and x.get("program_path"):
        link = "page/program/" + x["program_path"]
    elif x.get("id") is not None and kind != "program":
        link = "page/unit/%s" % x["id"]
        prog = _lab(x.get("program"))
        norm = lambda v: "".join(c for c in v.lower() if c.isalnum())
        if prog and norm(prog) not in norm(title) and norm(title) not in norm(prog):
            title = prog + " — " + title
    else:
        return None
    cat = _lab(x.get("category"))
    chan = _lab(x.get("channel"))
    if chan and chan == chan.lower():       # a slug ("france-2") rather than a name
        chan = chan.replace("-", " ").title().replace("France Tv", "france.tv")
    meta = " · ".join(v for v in [cat.capitalize() if cat else "", chan, str(x.get("production_year") or "")] if v)
    return {"id": "ftv-%s-%s" % (kind, x.get("id")), "title": title.strip(), "kind": kind, "year": "",
            "image": image, "poster": "", "meta": meta, "rating": 0,
            "overview": x.get("synopsis") or x.get("description") or x.get("headline_title") or "",
            "deeplink": FTV_APP + "?deeplink=" + link}


def _francetv():
    home = _http_json(FTV_HOME).get("collections") or []
    rows = []
    for title, label in FTV_ROWS:
        col = next((c for c in home if c.get("label") == label), None)
        if col:
            items = [i for i in (_ftv_item(x) for x in col.get("items") or []) if i]
            rows.append({"title": title, "items": items[:PER_ROW]})
    return rows


# MARK: - TF1+: tf1.fr's public GraphQL program list (persisted query 483ce0f, as Catch-up TV & More uses it).
# Deep link (VIDAA app, "default" platform case): ?deeplinkTarget=SHOWPAGE&deeplink=<program id> -> Showpage.

TF1_API = "https://www.tf1.fr/graphql/web"
TF1_APP = "https://smart-tv-vidaa.prod.p.tf1.fr/?source=atf"
UA_WEB = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# Sport rows leave football out (this deployment's choice): empty NO_FOOT to keep it.
NO_FOOT = ("football", "foot ", "uefa", "fifa", "téléfoot", "telefoot", "ligue 1", "ligue des champions",
           "matchs internationaux de préparation", "coupe du monde de la fifa", "adil rami")


def _no_foot(title):
    t = (title or "").lower()
    return not any(k in t for k in NO_FOOT)


def _tf1_programs():
    variables = {"context": {"persona": "PERSONA_2", "application": "WEB", "device": "DESKTOP", "os": "WINDOWS"},
                 "filter": {"channel": ""}, "offset": 0, "limit": 500}
    url = TF1_API + "?" + urllib.parse.urlencode({"id": "483ce0f", "variables": json.dumps(variables)})
    req = urllib.request.Request(url, headers={"content-type": "application/json", "User-Agent": UA_WEB,
                                               "referer": "https://www.tf1.fr/programmes-tv"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return ((json.load(r).get("data") or {}).get("programs") or {}).get("items") or []


def _tf1_item(x, label):
    dec = x.get("decoration") or {}
    srcs = (dec.get("background") or {}).get("sources") or []
    jpg = [s for s in srcs if s.get("type") == "jpg"] or srcs
    img = next((s["url"] for s in jpg if s.get("width") == "960"), jpg[0]["url"] if jpg else "")
    if not img or not x.get("id"):
        return None
    chan = (x.get("mainChannel") or {}).get("label") or ""
    return {"id": "tf1-" + x["id"], "title": x.get("name") or "", "kind": "program", "year": "",
            "image": img, "poster": "", "meta": " · ".join(v for v in (label, chan) if v), "rating": 0,
            "overview": dec.get("description") or "",
            "deeplink": TF1_APP + "&deeplinkTarget=SHOWPAGE&deeplink=" + urllib.parse.quote(x["id"])}


def _tf1():
    progs = _tf1_programs()

    def cats(x):
        return {c.get("id") for c in x.get("categories") or []}

    def has_videos(x):
        return ((x.get("allVideos") or {}).get("total") or 0) > 0

    reality = [x for x in progs if "SGT_ENTERTAINMENT" in cats(x) and "GT_MOVIES" not in cats(x) and has_videos(x)]
    sport = [x for x in progs if "SGT_SPORT" in cats(x) and _no_foot(x.get("name")) and has_videos(x)]
    rows = [("Télé-réalité", reality, "Divertissement"), ("Sport", sport, "Sport")]
    out = []
    for title, lst, label in rows:
        items = [i for i in (_tf1_item(x, label) for x in lst) if i]
        if items:
            out.append({"title": title, "items": items[:PER_ROW]})
    return out


# MARK: - M6+: 6play's public middleware folders (as Catch-up TV & More reads them): 10 = Divertissement,
# 232 = Séries-réalité. Pictures: the program's "vignette" (2732x1536 JPEG, ~800 KB), shrunk to 640x360 on
# this Pi by ffmpeg and kept in cache/img (GET /img/m6/<image id>.jpg on the bridge).
# Deep link (VIDAA app): the app starts on the route in its own address (app-renderer: changeLocation to
# window.location), routes being /core/main/<entityType>/<entityId>: a program is /core/main/program/<id>.
# (/video-tv/<code>-p_<id> was tried first: the app opened on its home page.)

M6_FOLDER = ("https://android.middleware.6play.fr/6play/v2/platforms/m6group_androidmob/services/6play/"
             "folders/%d/programs?limit=999&offset=0&csa=6&with=parentcontext")
M6_APP = "https://hisense--m6plus.6cloud.fr/"
M6_ROWS = [("Télé-réalité", 10), ("Séries-réalité", 232)]
IMG_DIR = os.path.join(HERE, "cache", "img")


def _m6_item(x, label):
    vig = next((i for i in x.get("images") or [] if i.get("role") == "vignette" and i.get("external_key")), None)
    if not vig or not x.get("id"):
        return None
    return {"id": "m6-%s" % x["id"], "title": x.get("title") or "", "kind": "program", "year": "",
            "image": "/img/m6/%s.jpg" % vig["external_key"], "poster": "", "meta": label, "rating": 0,
            "overview": (x.get("description") or "").replace("\r", ""),
            "deeplink": M6_APP + "core/main/program/%s" % x["id"]}


def _m6():
    out, seen = [], set()
    for title, folder in M6_ROWS:
        req = urllib.request.Request(M6_FOLDER % folder, headers={"User-Agent": UA_WEB, "x-customer-name": "m6web"})
        with urllib.request.urlopen(req, timeout=20) as r:
            progs = json.load(r)
        items = []
        for x in progs:
            i = _m6_item(x, "Divertissement" if folder == 10 else "Série-réalité")
            if i and i["id"] not in seen and _no_foot(i["title"]):
                seen.add(i["id"])
                items.append(i)
        if items:
            out.append({"title": title, "items": items[:PER_ROW]})
    return out


def m6_image(key):
    """Path of the cached 640x360 JPEG for a 6play image id (fetched and shrunk once), or None."""
    if not key.isdigit() or len(key) > 12:
        return None
    path = os.path.join(IMG_DIR, "m6-%s.jpg" % key)
    if os.path.exists(path):
        return path
    import subprocess
    import tempfile
    os.makedirs(IMG_DIR, exist_ok=True)
    src = None
    try:
        req = urllib.request.Request("https://images.6play.fr/v1/images/%s/raw" % key, headers={"User-Agent": UA_WEB})
        with urllib.request.urlopen(req, timeout=30) as r:
            if not (r.headers.get("Content-Type") or "").startswith("image/"):
                return None
            raw = r.read(30 * 1024 * 1024)
        with tempfile.NamedTemporaryFile(dir=IMG_DIR, suffix=".src", delete=False) as f:
            f.write(raw)
            src = f.name
        tmp = path + ".tmp.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-vf", "scale=640:-2", "-q:v", "4", tmp],
                       check=True, timeout=60)
        os.replace(tmp, path)
        return path
    except Exception:
        return None
    finally:
        if src:
            try:
                os.unlink(src)
            except OSError:
                pass


# Apps whose rows come from their own catalogue (with deep links), not TMDB.
NATIVE = {"france.tv": _francetv, "tf1+": _tf1, "m6+": _m6}


_lock = threading.Lock()
_cache = None
_genres = {}


def _key():
    try:
        with open(KEY_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def _get(path):
    key = _key()
    if not key:
        raise RuntimeError("no TMDB key (server/keys/tmdb.key)")
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(TMDB + path + sep + "api_key=" + urllib.parse.quote(key),
                                 headers={"Accept": "application/json", "User-Agent": "alvidaa-feeds/1"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.load(r)


def _genre_names(kind):
    if kind not in _genres:
        try:
            _genres[kind] = {g["id"]: g["name"] for g in _get("/genre/%s/list?language=%s" % (kind, LANG)).get("genres", [])}
        except Exception:
            return {}
    return _genres[kind]


def _item(kind, r):
    if not r.get("backdrop_path"):
        return None
    title = r.get("title") or r.get("name") or ""
    date = r.get("release_date") or r.get("first_air_date") or ""
    year = date[:4]
    names = _genre_names(kind)
    genres = [names[g] for g in r.get("genre_ids", []) if g in names][:2]
    rating = round(r.get("vote_average") or 0, 1)
    meta = " · ".join([x for x in [("Film" if kind == "movie" else "Série"), year, " / ".join(genres)] if x])
    return {"id": "%s-%s" % (kind, r.get("id")), "title": title, "kind": kind, "year": year,
            "image": IMG + "w780" + r["backdrop_path"],
            "poster": IMG + "w342" + r["poster_path"] if r.get("poster_path") else "",
            "meta": meta, "rating": rating, "overview": r.get("overview") or ""}


def _row(sources):
    lists = []
    for kind, path in sources:
        out = []
        for page in (1, 2):
            try:
                res = _get(path + "&page=%d" % page).get("results", [])
            except Exception:
                break
            out += [i for i in (_item(kind, r) for r in res) if i]
            if len(out) >= PER_ROW:
                break
        lists.append(out)
    items, seen = [], set()
    for i in range(PER_ROW * 2):          # interleave films and series
        for l in lists:
            if i < len(l) and l[i]["id"] not in seen:
                seen.add(l[i]["id"])
                items.append(l[i])
    return items[:PER_ROW]


def _load():
    global _cache
    if _cache is None:
        try:
            with open(CACHE_FILE) as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save():
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_cache, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def feed(app):
    name = (app or "").strip().lower()
    native = NATIVE.get(name)
    spec = None if native else _rows(name)
    if not native and not spec:
        return {"ok": True, "app": app, "rows": []}
    with _lock:
        cache = _load()
        hit = cache.get(name)
        if hit and time.time() - hit.get("at", 0) < TTL:
            return hit["data"]
        try:
            if native:
                rows = native()
            else:
                rows = [{"title": t, "items": _row(src)} for t, src in spec]
            rows = [r for r in rows if r["items"]]
            data = {"ok": True, "app": app, "rows": rows}
            if rows:
                cache[name] = {"at": time.time(), "data": data}
                _save()
            return data
        except Exception as e:
            if hit:
                return hit["data"]          # stale rows beat none
            return {"ok": False, "app": app, "rows": [], "error": str(e)}
