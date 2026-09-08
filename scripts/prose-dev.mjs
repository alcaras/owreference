// Dev-only Vite plugin: in-page prose editing for Border Expansion.
//
// While `astro dev` serves the page, every prose block that
// scripts/border_prose.py knows about gets a data-prose="<id>" attribute
// (paragraphs, list items, headings; HexBoard notes via a noteId prop), and
// two endpoints appear:
//   GET  /__prose/blocks  → the blocks JSON (id, kind, normalised source text)
//   POST /__prose/apply   → body is the markdown `border_prose.py apply` reads;
//                           runs it (and build_borders.py if a caption changed)
// Nothing here runs for `astro build`; the production HTML is untouched.
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { readFileSync } from 'node:fs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PAGE = path.join(ROOT, 'src/pages/border-expansion.astro');
const PY = ['python3', path.join(ROOT, 'scripts/border_prose.py')];

function blocks() {
  return JSON.parse(execFileSync(PY[0], [PY[1], 'blocks'], { cwd: ROOT, encoding: 'utf8' }));
}

export default function proseDev() {
  return {
    name: 'owreference-prose-dev',
    apply: 'serve',
    enforce: 'pre',
    // Astro compiles .astro files in its own (earlier) transform hook, so the
    // stamping has to happen in load, which Astro leaves to Vite for the plain
    // page id; the ?astro&type=style sub-requests re-load through here too.
    load(id) {
      if (id !== PAGE) return null;
      const code = readFileSync(PAGE, 'utf8');
      const page = blocks().filter(b => b.file === 'src/pages/border-expansion.astro');
      // border_prose.py reports code-point offsets; JS strings index UTF-16
      // units and the page holds a non-BMP emoji, so work on code points.
      const cp = Array.from(code);
      for (const b of page.sort((a, c) => c.start - a.start)) {
        if (b.kind === 'note') {
          let at = b.start;
          while (at > 0 && cp.slice(at, at + 5).join('') !== 'note=') at--;
          cp.splice(at, 0, `noteId="${b.id}" `);
        } else {
          // group 1 starts right after the opening tag's '>'
          const gt = b.start - 1;
          if (cp[gt] !== '>') continue;
          cp.splice(gt, 0, ` data-prose="${b.id}"`);
        }
      }
      const out = cp.join('');
      return { code: out, map: null };
    },
    configureServer(server) {
      server.middlewares.use('/__prose/blocks', (req, res) => {
        res.setHeader('content-type', 'application/json');
        res.end(JSON.stringify(blocks()));
      });
      server.middlewares.use('/__prose/apply', (req, res) => {
        if (req.method !== 'POST') { res.statusCode = 405; return res.end(); }
        let body = '';
        req.on('data', c => (body += c));
        req.on('end', () => {
          const r = spawnSync(PY[0], [PY[1], 'apply', '-'], { cwd: ROOT, input: body, encoding: 'utf8' });
          let log = (r.stdout || '') + (r.stderr || '');
          let ok = r.status === 0;
          if (ok && log.includes('BOARDS_CHANGED')) {
            const b = spawnSync('python3', [path.join(ROOT, 'scripts/build_borders.py')], { cwd: ROOT, encoding: 'utf8' });
            log += (b.stdout || '') + (b.stderr || '');
            ok = b.status === 0;
          }
          res.setHeader('content-type', 'application/json');
          res.end(JSON.stringify({ ok, log }));
        });
      });
    },
  };
}
