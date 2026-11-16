/*
 * Free My TV on a VIDAA TV/projector, through the alvidaa bridge (server/vidaa_server.py on the Pi).
 * Replaces web/tv.js: same interface, but the apps, inputs and launches go over the bridge's WebSocket (/ws),
 * which talks to the TV over its local MQTT API. The page is served by the same bridge, so icons are same-origin.
 * Plain ES5 for the TV's browser engine.
 */
var TV = (function () {
  'use strict';

  var ws = null, online = false, hello = null, retry = 0;
  var waitingHello = [];   // apps()/inputs() callers waiting for the first snapshot
  var waitingReply = [];   // launch callers waiting for {ok: ...}

  function connect() {
    try { ws = new WebSocket('ws://' + location.host + '/ws'); } catch (e) { later(); return; }
    ws.onopen = function () { online = true; retry = 0; };
    ws.onmessage = function (ev) {
      var m = null;
      try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.t === 'hello') {
        // The bridge answered after apps()/inputs() gave up (it was starting): start over with the real lists.
        if (gaveUp && !hello) { location.reload(); return; }
        hello = m;
        var w = waitingHello; waitingHello = [];
        for (var i = 0; i < w.length; i++) w[i]();
      } else if (m.t === 'reload') {
        location.reload();   // GET /api/reload on the bridge: picks up a new build without touching the TV
      } else if (m.t === 'apps' && hello) {
        hello.apps = m.apps || hello.apps;
      } else if (m.t === 'sources' && hello) {
        hello.sources = m.sources || hello.sources;
      } else if (typeof m.ok === 'boolean' && waitingReply.length) {
        waitingReply.shift()(m.ok);
      }
    };
    ws.onclose = function () {
      online = false;
      while (waitingReply.length) waitingReply.shift()(false);
      later();
    };
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  }
  function later() { setTimeout(connect, Math.min(8000, 1000 * Math.pow(2, retry++))); }

  var gaveUp = false;

  /** fn() once the bridge has sent its snapshot (or after 8 s without it: the page shows, and reloads when it comes). */
  function whenReady(fn) {
    if (hello) { fn(); return; }
    var done = false;
    function once() { if (!done) { done = true; fn(); } }
    waitingHello.push(once);
    setTimeout(function () { if (!done) { gaveUp = true; once(); } }, 8000);
  }

  function send(obj, done) {
    if (!online || !ws || ws.readyState !== 1) { if (done) done(false); return; }
    var answered = false;
    function reply(ok) { if (!answered) { answered = true; if (done) done(ok); } }
    waitingReply.push(reply);
    setTimeout(function () {
      var i = waitingReply.indexOf(reply);
      if (i >= 0) waitingReply.splice(i, 1);
      reply(true);   // the bridge answers late on some launches; the TV usually opens the app anyway
    }, 5000);
    try { ws.send(JSON.stringify(obj)); } catch (e) { reply(false); }
  }

  connect();

  // VIDAA's names for its inputs: the antenna ("TV Channels", id 284) and HDMI ports.
  function inputOf(s) {
    var id = String(s.id), name = s.name || id;
    if (id === '284' || /^tv\b|channel/i.test(name)) {
      return {id: 'source:' + id, key: 'live', label: null, symbol: 'live_tv', connected: true};
    }
    var hdmi = /^hdmi\s*(\d)/i.exec(name) || /^hdmi\s*(\d)/i.exec(id);
    if (hdmi) {
      return {id: 'source:' + id, key: 'hdmi' + hdmi[1], label: 'HDMI ' + hdmi[1], symbol: 'hdmi',
        connected: s.signal !== false};
    }
    return {id: 'source:' + id, key: 'src' + id, label: name.replace(/▶/g, '').trim(), symbol: 'cast',
      connected: s.signal !== false};
  }

  return {
    name: 'vidaa',

    /** Installed apps, as the bridge lists them: [{id, title, icon, color}]. The id is the app's name. */
    apps: function (done) {
      whenReady(function () {
        var list = (hello && hello.apps) || [];
        done(list.map(function (a) {
          return {id: a.name, title: a.name, icon: a.icon || '', color: ''};
        }).filter(function (a) { return a.id && !/tv channels|live tv/i.test(a.id); }));
      });
    },

    /** Opens an app (by name) or an input ("source:<id>"); done(ok). */
    launch: function (id, params, done) {
      if (id.indexOf('source:') === 0) send({t: 'source', id: id.slice(7)}, done);
      else send(params && params.url ? {t: 'launch', name: id, url: params.url} : {t: 'launch', name: id}, done);
    },

    /** The antenna, HDMI and other inputs the TV reports. */
    inputs: function (done) {
      whenReady(function () {
        var list = ((hello && hello.sources) || []).map(inputOf);
        list.sort(function (a, b) { return a.key === 'live' ? -1 : b.key === 'live' ? 1 : 0; });
        done(list);
      });
    },

    /** VIDAA's own settings menu (the remote's Menu key, sent by the bridge). */
    settings: function (done) { send({t: 'key', key: 'KEY_MENU'}, done); },

    /** Nothing to hold: VIDAA has no screensaver request API. */
    holdScreenSaver: function () {},

    /** Back on the first screen: this is the home screen, nothing behind it. */
    back: function () {},

    zone: function () {
      try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) { return ''; }
    },

    /** Key codes: arrows, OK, and VIDAA's Back (8, as Backspace). */
    keys: {left: 37, up: 38, right: 39, down: 40, ok: 13, back: 8}
  };
})();
