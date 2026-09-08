// Dev-only in-page prose editor for Border Expansion (loaded from the page
// only when import.meta.env.DEV). Pairs with scripts/prose-dev.mjs, which
// stamps data-prose="<id>" on every prose block and serves /__prose/*.
//
// Click the pencil, edit any outlined block in place, Save. Edits are turned
// back into source text: blocks made only of plain text and simple tags
// (<strong>, <em>, <code>, <a href="#…">) are written as typed; a block that
// also holds {data slots} or components gets its changed span spliced into
// the source by matching the unchanged text around it. If that fails, the
// block is reported for a manual edit instead of being guessed.

type Block = { id: string; kind: string; file: string; text: string };

const SIMPLE = new Set(['STRONG', 'EM', 'CODE', 'KBD']);
const norm = (s: string) => s.replace(/\s+/g, ' ').trim();

let blocks: Record<string, Block> = {};
let original: Record<string, string> = {};
let editing = false;

function serialize(el: Element): string {
  let out = '';
  el.childNodes.forEach(n => {
    if (n.nodeType === Node.TEXT_NODE) { out += n.textContent; return; }
    if (n.nodeType !== Node.ELEMENT_NODE) return;
    const e = n as Element;
    const tag = e.tagName;
    if (SIMPLE.has(tag)) out += `<${tag.toLowerCase()}>${serialize(e)}</${tag.toLowerCase()}>`;
    else if (tag === 'A' && (e.getAttribute('href') || '').startsWith('#')) out += `<a href="${e.getAttribute('href')}">${serialize(e)}</a>`;
    else out += `⦃${e.getAttribute('data-prose-tok') ?? '?'}⦄`; // opaque: a component or data-driven markup
  });
  return norm(out);
}

// Splice a single changed span from the rendered text into the source text.
function splice(src: string, oldR: string, newR: string): string | null {
  let pre = 0;
  while (pre < oldR.length && pre < newR.length && oldR[pre] === newR[pre]) pre++;
  let suf = 0;
  while (suf < oldR.length - pre && suf < newR.length - pre && oldR[oldR.length - 1 - suf] === newR[newR.length - 1 - suf]) suf++;
  const oldMid = oldR.slice(pre, oldR.length - suf);
  const newMid = newR.slice(pre, newR.length - suf);
  if (/[⦃⦄]/.test(oldMid + newMid)) return null;
  const before = oldR.slice(0, pre).split(/[⦃⦄]/).pop()!;
  const after = oldR.slice(oldR.length - suf).split(/[⦃⦄]/)[0];
  for (const len of [48, 32, 24, 16, 12, 8, 5]) {
    const b = before.slice(Math.max(0, before.length - len));
    const a = after.slice(0, len);
    const needle = b + oldMid + a;
    const i = src.indexOf(needle);
    if (i < 0 || src.indexOf(needle, i + 1) >= 0) continue;
    return src.slice(0, i) + b + newMid + a + src.slice(i + needle.length);
  }
  return null;
}

function collect() {
  const changed: string[] = [];
  const manual: string[] = [];
  document.querySelectorAll<HTMLElement>('[data-prose]').forEach(el => {
    const id = el.dataset.prose!;
    const b = blocks[id];
    if (!b) return;
    const now = serialize(el);
    if (now === original[id]) return;
    let text: string | null;
    if (!/[{⦃]/.test(original[id]) && !/\{/.test(b.text)) text = now;
    else text = splice(b.text, original[id], now);
    if (text === null) manual.push(`### manual.${id}\n\nWAS: ${original[id]}\n\nNOW: ${now}\n`);
    else changed.push(`### ${id}\n\n${text}\n`);
  });
  return { changed, manual };
}

function ui() {
  const bar = document.createElement('div');
  bar.id = 'prose-bar';
  bar.innerHTML = `<button data-act="toggle" title="Edit the page's prose in place (dev only)">✎ Edit prose</button>
    <button data-act="save" hidden>Save to source</button>
    <button data-act="copy" hidden>Copy markdown</button>
    <span data-role="status"></span>`;
  document.body.appendChild(bar);
  const style = document.createElement('style');
  style.textContent = `
    #prose-bar { position: fixed; right: 1rem; bottom: 1rem; z-index: 9999; display: flex; gap: .5rem; align-items: center;
      font: 12px/1.3 var(--font-mono, monospace); background: #0e0f12; border: 1px solid #c9a04a; border-radius: 6px; padding: .45rem .6rem; color: #e8e2d3; box-shadow: 0 4px 18px #0009; max-width: 60vw; }
    #prose-bar button { font: inherit; background: #1a1c22; color: inherit; border: 1px solid #c9a04a88; border-radius: 4px; padding: .3rem .6rem; cursor: pointer; }
    #prose-bar button:hover { border-color: #c9a04a; }
    #prose-bar [data-role=status] { white-space: pre-wrap; max-height: 30vh; overflow: auto; color: #b8b2a3; }
    body.prose-editing [data-prose] { outline: 1px dashed #c9a04a66; outline-offset: 3px; border-radius: 2px; cursor: text; }
    body.prose-editing [data-prose]:hover { outline-color: #c9a04a; }
    body.prose-editing [data-prose]:focus { outline: 2px solid #c9a04a; background: #c9a04a14; }
    body.prose-editing [data-prose].prose-dirty { outline-color: #4696eb; }
    body.prose-editing [data-prose] a { pointer-events: none; }`;
  document.head.appendChild(style);
  const status = bar.querySelector<HTMLElement>('[data-role=status]')!;
  const say = (s: string) => { status.textContent = s; };
  const save = bar.querySelector<HTMLButtonElement>('[data-act=save]')!;
  const copy = bar.querySelector<HTMLButtonElement>('[data-act=copy]')!;

  bar.querySelector('[data-act=toggle]')!.addEventListener('click', () => {
    editing = !editing;
    document.body.classList.toggle('prose-editing', editing);
    document.querySelectorAll<HTMLElement>('[data-prose]').forEach(el => {
      el.contentEditable = editing ? 'true' : 'false';
      el.spellcheck = editing;
    });
    save.hidden = copy.hidden = !editing;
    say(editing ? `${Object.keys(original).length} blocks editable. Click any outlined text.` : '');
  });
  document.addEventListener('input', e => {
    const el = (e.target as HTMLElement).closest<HTMLElement>('[data-prose]');
    if (el) el.classList.toggle('prose-dirty', serialize(el) !== original[el.dataset.prose!]);
  });
  const md = () => {
    const { changed, manual } = collect();
    return { text: [...changed, ...manual].join('\n'), n: changed.length, m: manual.length };
  };
  copy.addEventListener('click', async () => {
    const r = md();
    await navigator.clipboard.writeText(r.text);
    say(r.text ? `copied ${r.n} changed block(s)${r.m ? `, ${r.m} for manual edit` : ''}:\n${r.text}` : 'nothing changed');
  });
  save.addEventListener('click', async () => {
    const r = md();
    if (!r.text) return say('nothing changed');
    say('saving…');
    const res = await fetch('/__prose/apply', { method: 'POST', body: r.text });
    const j = await res.json();
    say((j.ok ? '' : 'FAILED\n') + j.log + (r.m ? `\n${r.m} block(s) need a manual edit:\n${collect().manual.join('\n')}` : ''));
    if (j.ok) {
      // the dev server reloads the page when the source files change; keep the
      // log visible in the meantime by re-arming the bar after reload
      sessionStorage.setItem('prose-log', status.textContent || '');
    }
  });
  const prior = sessionStorage.getItem('prose-log');
  if (prior) { say(prior); sessionStorage.removeItem('prose-log'); }
}

async function init() {
  const list: Block[] = await (await fetch('/__prose/blocks')).json();
  blocks = Object.fromEntries(list.map(b => [b.id, b]));
  let tok = 0;
  document.querySelectorAll<HTMLElement>('[data-prose]').forEach(el => {
    el.querySelectorAll('*').forEach(e => {
      if (!SIMPLE.has(e.tagName) && !(e.tagName === 'A' && (e.getAttribute('href') || '').startsWith('#'))) e.setAttribute('data-prose-tok', String(tok++));
    });
    original[el.dataset.prose!] = serialize(el);
  });
  ui();
}

init();
