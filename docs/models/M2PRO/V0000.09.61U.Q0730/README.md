# M2 Pro (Vidda laser projector) / V0000.09.61U.Q0730 — launcher lane, `brand=evv`, deep links into french streaming apps (SoC not measured, FR)

**Status:** verified on 2026-11-16 on the owner's unit: pairing (once the brand token is
`evv`), the lane-1 launcher page opened with a custom `launchapp`, a Free My TV home
screen with per-app tabs driven over the bridge, and **title deep links into france.tv,
TF1+ and M6+**, each confirmed on screen by the owner. Root was **not attempted**.

> **Applies to the Hisense/Vidda `M2 Pro` laser projector running `V0000.09.61U.Q0730`**
> (VIDAA `U09.61` by the firmware string; not read from the system menu). UPnP
> descriptor: `transport_protocol=3290`, `brand=evv`, `region=0`, `platform=1`,
> `voice=2`, `vidaa_support=1`, connected over Wi-Fi. Other Vidda-branded devices
> probably share `brand=evv`; none was tested.

> **Contributed by [@drdams](https://github.com/drdams).** Own device, French household,
> recorded in one owner-supervised session. The bridge changes and the Free My TV
> lane-1 port described here are in this branch; the french catalogue research reuses
> the endpoints documented by [Catch-up TV & More](https://github.com/Catch-up-TV-and-More/plugin.video.catchuptvandmore).

## What the chain rests on

1. **The MQTT identity carries a brand token, and this unit's is `evv`.** The client id,
   the dynamic username and the password hash all embed the brand (`his` for Hisense,
   `tos` for the [Toshiba 50C350LS](../../50C350LS/V0000.09.09M.P1124/README.md)). The
   TV publishes it in its UPnP descriptor
   (`http://<tv>:18400/MediaServer/rendererdevicedesc.xml`, `modelDescription` →
   `brand=evv`). With `his`, all four credential profiles get `rc=135` and the "outdated
   app" popup — the same symptom as a wrong MAC, which is why it is easy to chase the
   wrong cause. `server/pair.py` now reads the brand from the descriptor (or
   `VIDAA_BRAND`).
2. **The MAC in the identity is `macWifi`** (the unit is wireless; the descriptor's
   `mac=` is the Ethernet NIC), colon-formatted, as on the
   [55E7QTUK](../../55E7QTUK/V0000.09.09D.P1001/README.md).
3. **`launchapp` with a custom URL is not ignored on this build.** The lane-1 page opens
   as a custom web app (`storeType: custom`, `urlType: 1`); the
   [43A5LE](../../43A5LE/V0000.09.60A.Q0707/README.md) note that custom app ids are
   silently ignored does not hold here.
4. **An installed HTML5 store app can be launched with a modified URL on its own host,
   and keeps reading its own address.** That is all a deep link needs: the french
   apps' VIDAA builds parse `location.search` / `location.pathname` at start-up. The
   bridge only accepts a URL whose host is the app's registered host.
5. **`hiservice_cmd/<client>/actions/screenshot`** answers with the raw 1920×1080 JPEG on
   `/remoteapp/mobile/<client>/hiservice/data/screenshot` (documented for Vidda
   projectors by [sergvax/Vidda_remote_cn_node](https://github.com/sergvax/Vidda_remote_cn_node);
   rate-limited after ~8–10 quick shots). Exposed as `GET /api/screenshot`.

## What was measured

| Claim | Evidence | Source |
| --- | --- | --- |
| Pairing fails with `rc=135` on all four profiles with `brand=his`, with either MAC | **verified** | `pair.py` runs, 2026-11-16 |
| Pairing succeeds with `brand=evv` + colon-formatted `macWifi`, profile `modern`; PIN → `{"result":1}` → `tokenissuance` (access 2 days, refresh 30 days) | **verified** | same session |
| The 2024 `VidaaAppAndroidV01` client certificate is accepted (TLS completes; the rejection is at CONNECT) | **verified** | `rc=135`, not a TLS error |
| Lane-1 page opens via `/api/open` (custom web app) and stays connected over `/ws` | **verified** | bridge log: page, `/ws` 101, icon fetches |
| france.tv deep link opens the programme page | **verified** (owner, on screen) | see table below |
| TF1+ deep link opens the programme page | **verified** (owner, on screen) | see table below |
| M6+ deep link opens the programme page | **verified** (owner, on screen) | see table below |
| M6+ `/video-tv/<code>-p_<id>` opens the app on its home page, not the programme | **verified** | first M6+ attempt |
| ARTE deep link | **hypothesis** | its bundle handles `deeplink` / `arte://`; never launched |
| CANAL+ deep link | **untested** | its app URL answers 403 off the TV; bundle not read |
| Screenshot action returns a JPEG | **verified** if the screenshots below are present, otherwise **untested** | `GET /api/screenshot` |
| SoC, browser UA, VIDAA version from the system menu | **untested** | not read |

### Deep links (VIDAA builds of the french apps)

The app URLs come from the TV's own registry (`ui_service/applist`, exposed read-only as
`GET /api/applist`). The formats were read from each app's bundle; nothing public
documents them.

| App | Deep link | Where it is in the bundle | Label |
| --- | --- | --- | --- |
| france.tv | `https://hisense-smart-tv.yatta.francetv.fr/?deeplink=page/program/<program_path>` (also `page/unit/<video id>`, `page/channel/…`, `page/category/…`) | `DeeplinkHelper`, `hisense` case: reads `deeplink=` from `location.search` | **verified** (program) |
| TF1+ | `https://smart-tv-vidaa.prod.p.tf1.fr/?source=atf&deeplinkTarget=SHOWPAGE&deeplink=<program UUID>` (`VIDEO`, `LIVE` targets exist) | non-webOS/Tizen branch of the linking config → `Showpage` → `programById` | **verified** (SHOWPAGE) |
| M6+ | `https://hisense--m6plus.6cloud.fr/core/main/program/<6play program id>` | `app-renderer` chunk: start-up `changeLocation` to `window.location`, routes `/core/main/<entityType>/<entityId>` | **verified** |
| ARTE | `deeplink` parameter / `arte://` pages | main bundle | **hypothesis** |

Program ids: france.tv `program_path` from `api-mobile.yatta.francetv.fr/generic/homepage?platform=apps_tv`;
TF1+ program `id` from the `tf1.fr/graphql/web` persisted query `483ce0f`; M6+ program
`id` from `android.middleware.6play.fr/6play/v2/platforms/m6group_androidmob/services/6play/folders/<id>/programs`.
All three are public, account-free endpoints (as used by Catch-up TV & More).

## Screenshots

Taken from the projector with `GET /api/screenshot` (the Free My TV lane-1 home, see
[FREE-MY-TV-LANE1.md](../../../launcher/FREE-MY-TV-LANE1.md)).

<!-- screenshots -->

## What this guide includes and leaves out

| Included | Left out |
| --- | --- |
| the descriptor constants (`brand`, `transport_protocol`) and the pairing failure mode | the client certificate and key (extract them from the official app yourself, as the root README explains) |
| the deep-link formats and where each was found | access/refresh tokens, the TMDB key |
| the bridge and home-screen code (this branch) | MAC addresses, serial, LAN addresses |
| the public catalogue endpoints used | the apps' bundles themselves |

Nothing here touches the TV beyond the documented MQTT actions; the line is the
repository's usual one: findings and code, no key material.

## Teardown

Nothing is installed on the projector. Stop the bridge and press Home: the stock VIDAA
home returns. If the home watcher is enabled, it runs on the bridge host and stops with
it. The paired client stays in the TV's list until removed there.

## Open items

- ARTE deep link (format known from the bundle, never launched).
- CANAL+: deep link into a title or a live channel (bundle not readable off the TV).
- SoC, browser UA and VIDAA version from the system menu.
- Whether other `evv` devices share the descriptor port 18400 and the same app builds.

## Cross-reference

- Toshiba OEM brand case: [50C350LS](../../50C350LS/V0000.09.09M.P1124/README.md)
- Wireless `macWifi` pairing: [55E7QTUK](../../55E7QTUK/V0000.09.09D.P1001/README.md)
- Launcher lane on another 09.6x build: [43A5LE](../../43A5LE/V0000.09.60A.Q0707/README.md)
- Free My TV lane-1 port: [docs/launcher/FREE-MY-TV-LANE1.md](../../../launcher/FREE-MY-TV-LANE1.md)
- Publication policy: [DISCLOSURE.md](../../../DISCLOSURE.md)
