// In-place prose editor. Included by a page ONLY under `astro dev`
// (import.meta.env.DEV) and activates only with `?edit` in the URL.
// Every element carrying data-prose="<key>" becomes contenteditable; Save
// serialises each changed slot back to the page's minimal markdown and POSTs
// it to the standalone save server (node scripts/prose_editor.mjs), which
// rewrites src/data/<page>-prose.md. Computed values render as locked
// .prose-var chips (src/lib/prose.ts) and serialise back to their {placeholder}.
// Pages: zone-of-control, border-expansion.
// The page inlines this script before its content, so wait for the DOM.
function proseEditorMain() {
  if (!/[?&]edit\b/.test(location.search)) return;
  const meta = document.querySelector('meta[name="prose-file"]');
  if (!meta) return;
  const FILE = meta.content;
  const ENDPOINT = (document.querySelector('meta[name="prose-endpoint"]') || {}).content || 'http://127.0.0.1:4399/save';

  const style = document.createElement('style');
  style.textContent = `
    [data-prose] { outline: 1px dashed rgba(201,160,74,.35); outline-offset: 3px; border-radius: 3px; min-height: 1em; }
    [data-prose]:hover { outline-color: rgba(201,160,74,.7); }
    [data-prose]:focus-within, [data-prose]:focus { outline: 2px solid #c9a04a; outline-offset: 3px; background: rgba(201,160,74,.06); }
    [data-prose].is-dirty { outline-color: #7cc4ff; }
    .prose-var { background: rgba(120,190,255,.14); border-bottom: 1px dotted rgba(120,190,255,.8); border-radius: 2px; padding: 0 .1em; cursor: not-allowed; }
    #prose-bar { position: fixed; right: 14px; bottom: 14px; z-index: 9999; display: flex; gap: .5rem; align-items: center;
      background: #1c1d22; color: #eee; border: 1px solid #c9a04a; border-radius: 8px; padding: .5rem .75rem;
      font: 13px/1.3 Inter, system-ui, sans-serif; box-shadow: 0 6px 24px rgba(0,0,0,.5); }
    #prose-bar b { color: #c9a04a; font-weight: 600; }
    #prose-bar button { font: inherit; padding: .3rem .7rem; border-radius: 6px; border: 1px solid #555; background: #2a2b31; color: #eee; cursor: pointer; }
    #prose-bar button.primary { background: #c9a04a; color: #16171c; border-color: #c9a04a; font-weight: 600; }
    #prose-bar button:disabled { opacity: .45; cursor: default; }
    #prose-bar .key { color: #9aa; font-family: ui-monospace, Menlo, monospace; font-size: 11px; max-width: 22ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  `;
  document.head.appendChild(style);

  // ---- HTML → the prose file's markdown ----
  function inlineOf(node) {
    let out = '';
    for (const n of node.childNodes) {
      if (n.nodeType === 3) { out += n.nodeValue; continue; }
      if (n.nodeType !== 1) continue;
      const tag = n.tagName;
      if (n.classList.contains('prose-var')) { out += `{${n.dataset.var}}`; continue; }
      if (tag === 'BR') { out += ' '; continue; }
      const inner = inlineOf(n);
      if (tag === 'STRONG' || tag === 'B') out += inner.trim() ? `**${inner}**` : inner;
      else if (tag === 'EM' || tag === 'I') out += inner.trim() ? `*${inner}*` : inner;
      else if (tag === 'CODE' || tag === 'KBD') out += inner.trim() ? `\`${inner}\`` : inner;
      else if (tag === 'A' && n.getAttribute('href')) out += `[${inner}](${n.getAttribute('href')})`;
      else out += inner;
    }
    return out;
  }
  const tidy = s => s.replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
  function blocksOf(root) {
    const blocks = [];
    let loose = '';
    const flushLoose = () => { if (tidy(loose)) blocks.push(tidy(loose)); loose = ''; };
    for (const n of root.childNodes) {
      if (n.nodeType === 3) { loose += n.nodeValue; continue; }
      if (n.nodeType !== 1) continue;
      if (n.tagName === 'UL' || n.tagName === 'OL') {
        flushLoose();
        const ordered = n.tagName === 'OL';
        const items = [...n.children].map((li, i) => (ordered ? `${i + 1}. ` : '- ') + tidy(inlineOf(li))).filter(l => !/^(- |\d+\. )$/.test(l));
        if (items.length) blocks.push(items.join('\n'));
      } else if (n.tagName === 'P' || n.tagName === 'DIV') {
        flushLoose();
        const t = tidy(inlineOf(n));
        if (t) blocks.push(t);
      } else if (n.tagName === 'BR') {
        flushLoose();
      } else {
        loose += inlineOf(n);
      }
    }
    flushLoose();
    return blocks.join('\n\n');
  }
  const serialise = el => (el.hasAttribute('data-prose-blocks') ? blocksOf(el) : tidy(inlineOf(el)));

  // ---- wire up ----
  const slots = [...document.querySelectorAll('[data-prose]')];
  const original = new Map();
  for (const el of slots) {
    el.setAttribute('contenteditable', 'true');
    el.setAttribute('spellcheck', 'true');
    el.title = el.dataset.prose;
    original.set(el, serialise(el));
    if (!el.hasAttribute('data-prose-blocks')) {
      el.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); el.blur(); } });
    }
    el.addEventListener('input', update);
  }
  for (const v of document.querySelectorAll('.prose-var')) v.setAttribute('contenteditable', 'false');

  const bar = document.createElement('div');
  bar.id = 'prose-bar';
  bar.innerHTML = `<span>Editing <b>${FILE.replace(/^src\/data\//, '')}</b></span><span class="key" id="prose-key"></span><span id="prose-count">0 changed</span>` +
    `<button id="prose-discard">Discard</button><button class="primary" id="prose-save">Save ⌘S</button>`;
  document.body.appendChild(bar);
  const countEl = bar.querySelector('#prose-count');
  const saveBtn = bar.querySelector('#prose-save');
  const discardBtn = bar.querySelector('#prose-discard');
  const keyEl = bar.querySelector('#prose-key');

  function dirty() {
    const out = {};
    for (const el of slots) {
      const now = serialise(el);
      const changed = now !== original.get(el);
      el.classList.toggle('is-dirty', changed);
      if (changed) out[el.dataset.prose] = now;
    }
    return out;
  }
  function update() {
    const n = Object.keys(dirty()).length;
    countEl.textContent = `${n} changed`;
    saveBtn.disabled = discardBtn.disabled = n === 0;
    const a = document.activeElement && document.activeElement.closest && document.activeElement.closest('[data-prose]');
    keyEl.textContent = a ? a.dataset.prose : '';
  }
  document.addEventListener('focusin', update);
  update();
  window.__prose = { serialise, dirty, file: FILE };   // for round-trip tests

  async function save() {
    const slotsOut = dirty();
    if (!Object.keys(slotsOut).length) return;
    saveBtn.disabled = true; saveBtn.textContent = 'Saving…';
    try {
      const r = await fetch(ENDPOINT, { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ file: FILE, slots: slotsOut }) });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || r.statusText);
      saveBtn.textContent = 'Saved ✓';
      // Vite reloads the page when the ?raw import changes; fall back if it doesn't.
      setTimeout(() => location.reload(), 1500);
    } catch (e) {
      saveBtn.disabled = false; saveBtn.textContent = 'Save ⌘S';
      alert('Save failed: ' + e.message + '\n\nIs the save server running?  node scripts/prose_editor.mjs');
    }
  }
  saveBtn.addEventListener('click', save);
  discardBtn.addEventListener('click', () => location.reload());
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); save(); }
  });
  window.addEventListener('beforeunload', e => {
    if (Object.keys(dirty()).length && saveBtn.textContent !== 'Saved ✓') { e.preventDefault(); e.returnValue = ''; }
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', proseEditorMain); else proseEditorMain();
