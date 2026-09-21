// Colour helpers for the few places that paint a yield's colour as TEXT
// (stat-scaling readouts). The CSS tokens in theme.css (--yield-ink) are the
// same rule applied ahead of time; keep the two in step.

export function luminance(hex: string): number {
  const c = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16) / 255);
  const lin = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function contrast(a: string, b: string): number {
  const la = luminance(a), lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

function mixToWhite(hex: string, t: number): string {
  const c = hex.replace('#', '');
  return '#' + [0, 2, 4]
    .map((i) => Math.round(parseInt(c.slice(i, i + 2), 16) * (1 - t) + 255 * t).toString(16).padStart(2, '0'))
    .join('');
}

/** --bg-elev-3 from theme.css, the lightest surface body text sits on. */
const ELEV_3 = '#2d2821';

/** The yield colour mixed toward white until it clears WCAG AA (4.5:1, with a
 *  little headroom) as text on the site's dark surfaces. Pale yields come back
 *  unchanged. */
export function inkFor(hex: string, target = 4.6): string {
  let out = hex;
  for (let t = 0; t <= 0.8 && contrast(out, ELEV_3) < target; t += 0.01) out = mixToWhite(hex, t);
  return out;
}
