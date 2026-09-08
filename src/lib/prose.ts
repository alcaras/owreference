// Page prose from src/data/<page>-prose.md: "## key" sections, minimal inline
// markdown, {placeholders} filled from the page's data at build time.
//
// Used by zone-of-control.astro and border-expansion.astro; the in-place
// editor (src/lib/prose-editor.js + scripts/prose_editor.mjs) writes the same
// files back, so the markdown here and the serialiser there must agree:
//   **bold** *emphasis* `code` [text](url)   paragraphs = blank line
//   "- " bullets → <ul>, "1. " items → <ol>   {name} → a locked .prose-var chip
//
// A placeholder value is either a string (inline markdown allowed) or
// { html } to insert prepared markup verbatim (entity links, chips).

export type ProseVar = string | { html: string };

export interface ProseOptions {
  raw: string;                       // the ?raw import of the prose file
  vars?: Record<string, ProseVar>;
  listClass?: string;                // class for <ul>/<ol> rendered by blocks()
  name?: string;                     // prefix for missing-key warnings
}

export function parseProse(raw: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of raw.split(/\n---\n/)[0].split(/^## /m).slice(1)) {
    const nl = part.indexOf('\n');
    out[part.slice(0, nl).trim()] = part.slice(nl + 1).trim();
  }
  return out;
}

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function md(text: string): string {
  return esc(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, text, href) =>
      `<a href="${href}"${/^https?:/.test(href) ? ' rel="noopener"' : ''}>${text}</a>`)
    .replace(/\s*\n\s*/g, ' ');
}

export function createProse({ raw, vars = {}, listClass = '', name = 'prose' }: ProseOptions) {
  const PROSE = parseProse(raw);
  const warn = (key: string) => console.warn(`[${name}] missing key: ${key}`);

  // Markdown first (placeholders are inert to it), then each {placeholder}
  // becomes a locked chip whose own value may carry inline markdown.
  const render = (text: string) =>
    md(text).replace(/\{([a-zA-Z][a-zA-Z0-9]*)\}/g, (m, k) => {
      const v = vars[k];
      if (v === undefined) return m;
      return `<span class="prose-var" data-var="${k}">${typeof v === 'string' ? md(v) : v.html}</span>`;
    });

  function inline(key: string): string {
    const text = PROSE[key];
    if (text === undefined) {
      if (!key.endsWith('.note')) warn(key);   // notes are optional
      return '';
    }
    return render(text);
  }

  // Paragraphs plus "- " bullet and "1. " numbered lists, in source order.
  function blocks(key: string): string {
    const text = PROSE[key];
    if (text === undefined) { warn(key); return ''; }
    const cls = listClass ? ` class="${listClass}"` : '';
    const out: string[] = [];
    for (const block of text.split(/\n\s*\n/)) {
      const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
      if (!lines.length) continue;
      if (lines.every(l => l.startsWith('- '))) {
        out.push(`<ul${cls}>${lines.map(l => `<li>${render(l.slice(2))}</li>`).join('')}</ul>`);
      } else if (lines.every(l => /^\d+\. /.test(l))) {
        out.push(`<ol${cls}>${lines.map(l => `<li>${render(l.replace(/^\d+\. /, ''))}</li>`).join('')}</ol>`);
      } else {
        out.push(`<p>${render(lines.join(' '))}</p>`);
      }
    }
    return out.join('');
  }

  const has = (key: string) => !!PROSE[key];
  return { inline, blocks, has, PROSE };
}
