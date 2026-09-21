#!/usr/bin/env node
// Text-contrast audit of the BUILT site (WCAG 2.x AA: 4.5:1 for text, 3:1 for
// large text). Headless Chrome renders each page from dist/, a script walks
// every visible text node, composites its real background (backgrounds up the
// tree, gradient scrims, group opacity) and measures the ratio. Failures are
// grouped by (colour, element, background) so one bad token shows once.
//
//   make contrast            # sampled: every top-level page + 2 per dynamic route
//   node scripts/audit_contrast.mjs --all
//   node scripts/audit_contrast.mjs --only '^(shrines|hurrying)$'
//
// Exits 1 on any failure. Decorative glyphs (separators, empty-cell dashes
// marked aria-hidden) and disabled controls are skipped, as the guideline
// allows. Design tokens this guards: theme.css --text-* ramp, the per-yield
// --yield-fill / --yield-fg / --yield-ink / --yield-tint set, nation --nation-fg.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const args = process.argv.slice(2);
const flag = (n) => args.includes(n);
const opt = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : null; };
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const DIST = path.resolve(opt('--dist') || path.join(ROOT, 'dist'));
const BASE = '/owreference/';
const CHROME = process.env.CHROME || [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
].find((p) => fs.existsSync(p));
if (!CHROME) { console.error('audit_contrast: no Chrome found (set CHROME=/path)'); process.exit(2); }
if (!fs.existsSync(DIST)) { console.error(`audit_contrast: ${DIST} missing — run make build first`); process.exit(2); }

// ---- the in-page measurer (runs inside Chrome) --------------------------
const INJECT = String.raw`// Injected into each built page. Walks visible text, resolves fg + composited
// bg via canvas, reports WCAG contrast per (selector-path, fg, bg) pair.
(function(){
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const cx = cv.getContext('2d', {willReadFrequently:true});
  const cache = new Map();
  function rgba(str){
    if (cache.has(str)) return cache.get(str);
    cx.clearRect(0,0,1,1); cx.fillStyle = '#000'; cx.fillStyle = str; cx.fillRect(0,0,1,1);
    const d = cx.getImageData(0,0,1,1).data; // un-premultiplied rgba
    const a = d[3]/255;
    const out = a <= 0.004 ? [0,0,0,0] : [d[0], d[1], d[2], a];
    cache.set(str, out); return out;
  }
  function over(top, bottom){ // src-over, both [r,g,b,a]
    const a = top[3] + bottom[3]*(1-top[3]);
    if (a === 0) return [0,0,0,0];
    return [0,1,2].map(i => (top[i]*top[3] + bottom[i]*bottom[3]*(1-top[3]))/a).concat([a]);
  }
  function lum([r,g,b]){ const f=c=>{c/=255; return c<=0.03928? c/12.92 : Math.pow((c+0.055)/1.055,2.4)}; return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); }
  function ratio(a,b){ const l1=lum(a), l2=lum(b); return (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05); }
  const bodyBg = rgba(getComputedStyle(document.documentElement).getPropertyValue('--bg') || '#0e0f12');
  function gradientAvg(bgImage){
    // Approximate a gradient by parsing colour stops and averaging them (weighted equally).
    const cols = []; let depth=0, cur='';
    for (const ch of bgImage){ if(ch==='(')depth++; if(ch===')')depth--; cur+=ch; if(ch===',' && depth===1){cols.push(cur.slice(0,-1)); cur='';} }
    if (cur) cols.push(cur);
    const stops = [];
    for (let c of cols.slice(1)){ c=c.trim(); const m = c.match(/^((?:rgba?|oklch|color|hsl)\([^)]*\)|#[0-9a-f]+|transparent)/i); if(m) stops.push(rgba(m[1])); }
    if (!stops.length) return null;
    const avg=[0,0,0,0]; for(const s of stops){ for(let i=0;i<3;i++) avg[i]+=s[i]*s[3]; avg[3]+=s[3]; }
    if (avg[3]===0) return [0,0,0,0];
    return [avg[0]/avg[3], avg[1]/avg[3], avg[2]/avg[3], avg[3]/stops.length];
  }
  // Paint model: a pixel starting as \`start\` (opaque text, or transparent for
  // the bare background) walks outward. Each ancestor's own background goes
  // UNDER it; an ancestor's opacity then scales the whole group so far.
  function walk(el, start, dbg){
    let px = start.slice();
    for (let e = el; e; e = e.parentElement){
      const cs = getComputedStyle(e);
      let c = rgba(cs.backgroundColor);
      const bi = cs.backgroundImage;
      if (bi && bi !== 'none' && /gradient/.test(bi)){ const g = gradientAvg(bi); if (g) c = over(g, c); }
      if (dbg && c[3]>0) dbg.push(e.tagName.toLowerCase()+'.'+[...e.classList].slice(0,2).join('.')+':'+c.map(v=>+v.toFixed(2)).join(','));
      px = over(px, c);
      const op = parseFloat(cs.opacity);
      if (op < 1) px[3] *= op;
    }
    const base = bodyBg.slice(); base[3] = 1;
    return over(px, base);
  }
  function bgOf(el, dbg){ return walk(el, [0,0,0,0], dbg); }
  function pathOf(el){
    const parts=[];
    for (let e=el, n=0; e && n<4 && e!==document.body; e=e.parentElement, n++){
      let s = e.tagName.toLowerCase();
      const cls = [...e.classList].filter(c=>!/^astro-|^n-|^is-|^hl$/.test(c)).slice(0,3);
      if (cls.length) s += '.'+cls.join('.');
      parts.unshift(s);
    }
    return parts.join(' > ');
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Map();
  let node;
  while ((node = walker.nextNode())){
    const t = node.textContent.trim(); if (!t || t.length < 1) continue;
    const el = node.parentElement; if (!el) continue;
    if (/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(el.tagName)) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility==='hidden' || cs.display==='none') continue;
    const r = el.getBoundingClientRect(); if (r.width===0 || r.height===0) continue;
    // skip content inside closed details / hidden ancestors
    let hidden=false; for (let e=el;e;e=e.parentElement){ if (e.hidden || e.disabled || e.getAttribute('aria-hidden')==='true' || getComputedStyle(e).display==='none') {hidden=true;break;} }
    if (hidden) continue;
    const dbg = [];
    const bg = bgOf(el, dbg);
    const fg = walk(el, rgba(cs.color));
    const size = parseFloat(cs.fontSize), weight = parseInt(cs.fontWeight,10)||400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3 : 4.5;
    const cr = ratio(fg, bg);
    const key = pathOf(el) + '|' + cs.color + '|' + bg.map(v=>Math.round(v)).join(',');
    const hx = c=>'#'+[0,1,2].map(i=>Math.round(c[i]).toString(16).padStart(2,'0')).join('');
    if (!seen.has(key)) seen.set(key, {path: pathOf(el), fg: hx(fg), bg: hx(bg), cssColor: cs.color, size, weight, ratio: +cr.toFixed(2), need, pass: cr >= need, count:0, sample: t.slice(0,40), layers: dbg.slice(0,4)});
    seen.get(key).count++;
  }
  const out = [...seen.values()].filter(x=>!x.pass).sort((a,b)=>a.ratio-b.ratio);
  const pre = document.createElement('pre'); pre.id='__a11y'; pre.textContent = JSON.stringify({total: seen.size, fails: out});
  document.body.appendChild(pre);
})();
`;

// ---- page list -----------------------------------------------------------
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'owref-contrast-'));
fs.cpSync(DIST, work, { recursive: true });
const pages = [];
(function walk(d) { for (const f of fs.readdirSync(d)) { const p = path.join(d, f); if (fs.statSync(p).isDirectory()) walk(p); else if (f === 'index.html') pages.push(p); } })(work);
const only = opt('--only') ? new RegExp(opt('--only')) : null;
const perDir = new Map();
const chosen = pages.filter((p) => {
  const rel = path.relative(work, path.dirname(p)) || '/';
  if (only) return only.test(rel);
  if (flag('--all')) return true;
  const parent = path.dirname(rel);
  if (parent === '.' || parent === '/') return true;
  const n = perDir.get(parent) || 0; perDir.set(parent, n + 1);
  return n < 2;
});

// ---- run ------------------------------------------------------------------
const report = {};
let i = 0;
for (const p of chosen) {
  const rel = path.relative(work, path.dirname(p)) || '/';
  let html = fs.readFileSync(p, 'utf8');
  if (/<meta http-equiv="refresh"/i.test(html)) continue; // redirect stub, not a page
  const depth = rel === '/' ? 0 : rel.split('/').length;
  const up = depth ? '../'.repeat(depth) : './';
  html = html.replace(new RegExp(`(href|src)="${BASE}`, 'g'), `$1="${up}`);
  html = html.replace('</body>', `<script>window.addEventListener('load',()=>setTimeout(()=>{${INJECT}},300));</script></body>`);
  fs.writeFileSync(p, html);
  let dom = '';
  try {
    dom = execFileSync(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox', '--allow-file-access-from-files',
      '--window-size=1600,1200', '--virtual-time-budget=4000', '--hide-scrollbars', '--dump-dom', 'file://' + p],
      { maxBuffer: 1 << 28, timeout: 60000, stdio: ['ignore', 'pipe', 'ignore'] }).toString();
  } catch (e) { report[rel] = { error: String(e).slice(0, 200) }; continue; }
  const m = dom.match(/<pre id="__a11y">([\s\S]*?)<\/pre>/);
  if (!m) { report[rel] = { error: 'no audit output' }; continue; }
  const txt = m[1].replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
  try { report[rel] = JSON.parse(txt); } catch (e) { report[rel] = { error: 'parse ' + e.message }; }
  if (flag('--verbose')) process.stderr.write(`${++i}/${chosen.length} ${rel} fails=${report[rel].fails ? report[rel].fails.length : '?'}\n`);
}
fs.rmSync(work, { recursive: true, force: true });
if (opt('--json')) fs.writeFileSync(opt('--json'), JSON.stringify(report, null, 1));

// ---- aggregate -------------------------------------------------------------
const groups = new Map(); let nodes = 0, pagesFailing = 0; const errors = [];
for (const [page, v] of Object.entries(report)) {
  if (v.error) { errors.push(`${page}: ${v.error}`); continue; }
  if (v.fails.length) pagesFailing++;
  for (const f of v.fails) {
    nodes += f.count;
    const leaf = f.path.split(' > ').slice(-2).join(' > ');
    const key = `${f.cssColor} | ${leaf} | ${f.bg}`;
    const g = groups.get(key) || { key, ratio: f.ratio, need: f.need, size: f.size, fg: f.fg, pages: new Set(), count: 0, sample: f.sample };
    g.pages.add(page); g.count += f.count; g.ratio = Math.min(g.ratio, f.ratio); groups.set(key, g);
  }
}
console.log(`contrast: ${Object.keys(report).length} pages, ${pagesFailing} with failures, ${nodes} failing text nodes, ${groups.size} groups, ${errors.length} errors`);
for (const e of errors) console.log('  ERR', e);
const list = [...groups.values()].sort((a, b) => b.pages.size * b.count - a.pages.size * a.count);
for (const g of list) console.log(`  ${g.ratio.toFixed(2).padStart(5)}/${g.need}  ${String(g.pages.size).padStart(3)}pg ${String(g.count).padStart(5)}x ${g.size}px ${g.fg}  ${g.key}  :: ${JSON.stringify(g.sample)}`);
process.exit(nodes > 0 ? 1 : 0);
