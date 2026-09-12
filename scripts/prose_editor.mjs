#!/usr/bin/env node
// In-place prose editing for pages whose text lives in src/data/<page>-prose.md
// (zone-of-control, border-expansion, family-envy; see src/lib/prose.ts). Usage:
//
//   npm run edit                             # save server on :4399 + `astro dev` on :4321
//   node scripts/prose_editor.mjs --no-dev   # save server only (you run astro dev yourself)
//
// then open  http://localhost:4321/owreference/<page>/?edit
//
// The page (only under `astro dev`) loads src/lib/prose-editor.js, which makes
// every data-prose="<key>" slot contenteditable and POSTs changed slots here:
//
//   POST http://localhost:4399/save   { file: "src/data/zoc-prose.md", slots: { key: markdown } }
//
// Only the named "## key" sections are replaced; header, order, untouched
// sections and the trailer after "---" survive. Vite sees the file change (the
// page imports it with ?raw) and reloads. Deliberately not an Astro/Vite
// plugin: it must not touch astro.config.mjs or the production build.
import { createServer } from 'node:http';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, relative, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const FILE_RE = /^src\/data\/[a-z0-9-]+-prose\.md$/;
const args = process.argv.slice(2);
const PORT = Number((args.find(a => a.startsWith('--port=')) || '--port=4399').split('=')[1]);
const DEV_PORT = Number((args.find(a => a.startsWith('--dev-port=')) || '--dev-port=4321').split('=')[1]);

export function mergeProse(raw, slots) {
  const [body, ...trailerParts] = raw.split(/\n---\n/);
  const trailer = trailerParts.length ? trailerParts.join('\n---\n') : '';
  const parts = body.split(/^## /m);
  const header = parts[0];
  const sections = parts.slice(1).map(p => {
    const nl = p.indexOf('\n');
    return { key: p.slice(0, nl).trim(), text: p.slice(nl + 1).trim() };
  });
  const seen = new Set();
  for (const s of sections) {
    if (s.key in slots) { s.text = String(slots[s.key]).trim(); seen.add(s.key); }
  }
  for (const key of Object.keys(slots)) {
    if (!seen.has(key)) sections.push({ key, text: String(slots[key]).trim() });
  }
  return header.replace(/\s*$/, '\n\n') +
    sections.map(s => `## ${s.key}\n\n${s.text}\n`).join('\n') +
    (trailer ? `\n---\n${trailer.replace(/^\n+/, '')}` : '');
}

function cors(res) {
  res.setHeader('access-control-allow-origin', '*');
  res.setHeader('access-control-allow-headers', 'content-type');
  res.setHeader('access-control-allow-methods', 'POST, OPTIONS');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const server = createServer((req, res) => {
    cors(res);
    if (req.method === 'OPTIONS') { res.statusCode = 204; return res.end(); }
    if (req.url !== '/save' || req.method !== 'POST') { res.statusCode = 404; return res.end('POST /save only'); }
    let data = '';
    req.on('data', c => { data += c; });
    req.on('end', () => {
      res.setHeader('content-type', 'application/json');
      try {
        const { file, slots } = JSON.parse(data);
        if (!FILE_RE.test(file || '')) throw new Error(`refusing to write ${file}`);
        const abs = resolve(ROOT, file);
        if (relative(ROOT, abs).startsWith('..') || !existsSync(abs)) throw new Error(`no such prose file: ${file}`);
        writeFileSync(abs, mergeProse(readFileSync(abs, 'utf8'), slots || {}));
        const keys = Object.keys(slots || {});
        console.log(`[prose-editor] wrote ${file}: ${keys.join(', ')}`);
        res.end(JSON.stringify({ ok: true, file, keys }));
      } catch (e) {
        res.statusCode = 400;
        res.end(JSON.stringify({ ok: false, error: String(e.message || e) }));
      }
    });
  });
  server.listen(PORT, '127.0.0.1', () => {
    console.log(`[prose-editor] save server on http://127.0.0.1:${PORT}/save`);
    if (!args.includes('--no-dev')) {
      const dev = spawn('npx', ['astro', 'dev', '--port', String(DEV_PORT)], { cwd: ROOT, stdio: 'inherit' });
      dev.on('exit', code => process.exit(code ?? 0));
      process.on('SIGINT', () => { dev.kill('SIGINT'); process.exit(0); });
    }
    for (const page of ['zone-of-control', 'border-expansion', 'family-envy']) console.log(`[prose-editor] edit at http://localhost:${DEV_PORT}/owreference/${page}/?edit`);
  });
}
