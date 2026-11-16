# Free My TV on lane 1 (no root): per-app tabs, Direct TV, deep links

The [Free My TV](https://github.com/felipericardo/tv-launcher) web home screen (MIT),
served by the lane-1 bridge and opened on the TV as a custom web app. Unlike the
lane-3 port ([FREE-MY-TV-WEB-PARITY.md](FREE-MY-TV-WEB-PARITY.md)), nothing is installed
on the TV: the page talks to the bridge over `/ws` and the bridge talks MQTT.

Recorded on an [M2 Pro](../models/M2PRO/V0000.09.61U.Q0730/README.md) (`brand=evv`),
in a french household, so the catalogues are french. The structure is not.

## What the home screen does

- **Tabs per app.** Moving along the app shelf changes the tabs at the top to the
  focused app's sections (CANAL+: Films | Séries; france.tv: Sélection | Top 10;
  TF1+: Télé-réalité | Sport; M6+: Télé-réalité | Séries-réalité; Prime: Populaires),
  followed by two fixed tabs, **Direct TV** and **Reprendre**.
- **One large row**, the focused tile kept in the middle of the screen, its summary
  underneath; pictures load only near the focused tile.
- **OK opens an info sheet** (picture, rating, summary) whose button opens the title in
  its app: with a deep link where one is known (france.tv, TF1+, M6+), otherwise the
  app's home.
- **Direct TV**: the TNT channels and the Canal+ ones, each with its current programme,
  a progress bar, what's next and the evening's main programme, from the free
  [xmltvfr.fr](https://xmltvfr.fr/) guide.
- **Reprendre**: what was opened from this home screen, newest first. Real resume
  points with progress live in each provider's account; they are not reachable here
  (CANAL+'s `lists/ongoing` needs the subscriber session and sits behind an anti-bot
  wall; Prime/Netflix need the native partner context, i.e. root).

## Pieces

| Where | What |
| --- | --- |
| `server/vidaa_server.py` | bridge additions: `launch(name, url)` (deep link, **only on the app's own host**), WS `{"t":"key","key":"KEY_MENU"}`, `GET /api/feed`, `/api/tv`, `/api/history` (+ `POST`), `/api/applist` (read-only registry), `/api/screenshot`, `/api/key` (navigation keys only), `/img/m6/<id>.jpg` |
| `server/feeds.py` | rows per app: TMDB (key in `server/keys/tmdb.key`, never sent to the page) and the french catalogues (france.tv, TF1+, M6+); 6 h cache in `server/cache/` |
| `server/tvguide.py` | Direct TV (xmltvfr TNT guide, 6 h) and the Reprendre list |
| `tools/fmtv-lane1/` | `build.py` (upstream web/ + this folder → `launcher/fmtv/`), `home.js` (maintained fork), `tv-vidaa.js` (the `TV` adapter over the bridge), `rows.css`, `config.example.json` |

## Build and open

```sh
git clone https://github.com/felipericardo/tv-launcher ../tv-launcher     # tested at f2d984c
cp tools/fmtv-lane1/config.example.json tools/fmtv-lane1/config.json      # city, language, shelf order
echo '<your TMDB API key>' > server/keys/tmdb.key && chmod 600 server/keys/tmdb.key
python3 tools/fmtv-lane1/build.py
venv/bin/python server/vidaa_server.py <tv-ip>                             # as in the main README
curl "http://127.0.0.1:8765/api/open?url=http://<bridge-host>:8765/fmtv/"
```

After a rebuild, `curl http://127.0.0.1:8765/api/reload` reloads the page on the TV.
`/api/open` with the same URL does not reload an already open page; append `?v=<anything>`.

## Notes from the M2 Pro

- **CSS `url()` and parentheses.** france.tv image URLs contain `filters:quality(85)`;
  an unescaped `url(...)` drops them silently (and the CDN rejects `%28`/`%29`).
  `home.js` escapes them (`cssUrl()`).
- **M6+ pictures** are 0.8–19 MB originals and the resizing parameters are signed; the
  bridge shrinks them once with ffmpeg (640×360, ~50 KB) and caches them.
- **A bridge restart** can make the first `hello` arrive after the page gave up on the
  app list; the adapter reloads the page when it finally arrives.
- **Screenshots** (`/api/screenshot`) are rate-limited by the TV (~8–10 quick shots,
  then empty answers for minutes): the bridge takes at most one every 6 s.
