#!/usr/bin/env node
// Optional relay for the streamer overlay (from PR #1 by machinefolly).
//
// Only needed when the control panel runs in a DIFFERENT browser than the OBS
// browser source — the recommended setup (OBS Custom Browser Dock) shares a
// profile with the source and needs no server at all. Run manually:
//
//   make overlay-server         (or: node scripts/overlay_state_server.cjs)
//
// then add `?server` to the /obs Browser Source URL. Holds one string.
const http = require('http');

const PORT = 43210;
// {id, ts, ttl} — ts stamps each push so the overlay can restart its
// auto-hide countdown even when the same card is shown twice.
let state = { id: '', ts: 0, ttl: 0 };

http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (req.method === 'GET' && url.pathname === '/get') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(state));
    return;
  }
  if (req.method === 'POST' && url.pathname === '/set') {
    state = {
      id: url.searchParams.get('id') || '',
      ts: Date.now(),
      ttl: Math.max(0, parseInt(url.searchParams.get('ttl') || '0', 10) || 0),
    };
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', ...state }));
    return;
  }
  res.writeHead(404);
  res.end();
}).listen(PORT, '127.0.0.1', () => {
  console.log(`[overlay] state relay on http://127.0.0.1:${PORT} — Ctrl-C to stop`);
});
