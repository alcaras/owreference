// Exact odds for Game.spreadReligion's target pick (see scripts/build_religious_spread.py).
//
// Each candidate gets D = distance (× connection multiplier ÷ 100, truncated, when it
// is on the Holy City's trade network) × (religions already there + 1). Its score is
// D × (a uniform draw from 1..D); the lowest score wins. The game walks every city,
// then every tribal settlement, and only replaces the leader on a strictly lower
// score, so on a tie the candidate checked first keeps it.
//
// Used at build time for the worked examples and in the browser for the calculator,
// so both show the same numbers.

export interface Candidate {
  distance: number;
  connected?: boolean;
  religions?: number;
  tribe?: boolean;
}

// Utils.modify for a non-negative value: value × (100 + modifier) ÷ 100, truncated.
export function modifyDistance(d: number, multiplier: number): number {
  if (d === 0) return 0;
  return Math.trunc((d * Math.max(0, multiplier)) / 100);
}

export function effectiveD(c: Candidate, connMultiplier: number): number {
  const d = Math.max(0, Math.trunc(c.distance));
  if (c.tribe) return d;                       // no connection test, never has a religion
  const dd = c.connected ? modifyDistance(d, connMultiplier) : d;
  return dd * (Math.max(0, Math.trunc(c.religions ?? 0)) + 1);
}

// P(score > s) and P(score >= s) for a candidate with multiplier D.
function pGreater(D: number, s: number): number {
  if (D === 0) return s < 0 ? 1 : 0;           // score is always 0
  const n = D - Math.min(D, Math.max(0, Math.floor(s / D)));
  return n / D;
}
function pAtLeast(D: number, s: number): number {
  if (D === 0) return s <= 0 ? 1 : 0;
  const kMin = Math.max(1, Math.ceil(s / D));
  return Math.max(0, D - kMin + 1) / D;
}

// Win probability of each candidate, in the order given. Tribal settlements are
// checked after every city, as in the game, whatever order they are listed in.
export function winOdds(cands: Candidate[], connMultiplier: number): number[] {
  const order = cands
    .map((c, i) => ({ c, i }))
    .sort((a, b) => Number(!!a.c.tribe) - Number(!!b.c.tribe) || a.i - b.i);
  const Ds = order.map(o => effectiveD(o.c, connMultiplier));
  const out = new Array(cands.length).fill(0);
  order.forEach((o, pos) => {
    const D = Ds[pos];
    const ks = D === 0 ? [0] : Array.from({ length: D }, (_, k) => D * (k + 1));
    let p = 0;
    for (const s of ks) {
      let q = 1 / ks.length;
      for (let j = 0; j < Ds.length && q > 0; j++) {
        if (j === pos) continue;
        q *= j < pos ? pGreater(Ds[j], s) : pAtLeast(Ds[j], s);
      }
      p += q;
    }
    out[o.i] = p;
  });
  return out;
}
