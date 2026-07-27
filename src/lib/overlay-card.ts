// Shared renderer for the streamer-overlay card. Used by both /streamer (live
// preview) and /obs (the OBS browser-source overlay) so the preview IS the
// overlay — one markup builder, one stylesheet (styles/overlay-card.css).

import { attackDamage, damageTone, type CombatUnit } from './combat';

export interface OverlayEvent {
  trigger: string;
  category: string;
  dlc: string;
  chain: { title: string; size: number } | null;
  guaranteed?: string[];
  options: { text: string; rewards: string[]; reqs: string[]; leadsTo: string[] }[];
}

export interface OverlayCard {
  id: string;
  name: string;
  type: string;
  slug: string;
  page: string;
  icon: string;
  accent: string;
  aliases: string[];
  chips: string[];
  stats: Record<string, string | number>;
  cost: string[];
  lines: string[];
  event: OverlayEvent | null;
  combat?: { strength: number; traits: string[]; isMelee: boolean;
             counters: { kind: string; target: string; value: number }[] };
}

/** State-string protocol between /streamer and /obs: either a plain card id
 *  or a matchup — "MATCHUP|ATTACKER_ID|DEFENDER_ID". */
export const MATCHUP_PREFIX = 'MATCHUP|';

const esc = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// Inline yield icons, matching the main site's habit of showing the icon next
// to the yield word. Applied AFTER escaping; capitalized whole words only, so
// mechanic words and unit names stay untouched.
const YIELD_ICONS = [
  'Civics', 'Culture', 'Discontent', 'Food', 'Growth', 'Happiness', 'Iron',
  'Legitimacy', 'Maintenance', 'Money', 'Orders', 'Science', 'Stone',
  'Training', 'Wood',
];
const YIELD_RE = new RegExp(`(^|[^\\w/])(${YIELD_ICONS.join('|')})(?=$|[^\\w])`, 'g');

function iconize(escaped: string, base: string): string {
  return escaped.replace(YIELD_RE, (_m, pre, word) =>
    `${pre}<img class="ocard__yicon" src="${base}img/icons/yields/${word.toLowerCase()}.png" alt="" />${word}`);
}

// The overlay must hold a roughly constant footprint on stream — content is
// clamped here (deterministically, not by overflow) and long text lines are
// additionally line-clamped in CSS.
const MAX_LINES = 7;
const MAX_OPTIONS = 4;
const MAX_REWARDS_PER_OPTION = 2;

export interface RenderOpts {
  /** hide chain membership and per-option follow-ups — for casters who don't
   *  want to reveal why an event fired or what comes next in a series */
  noSpoilers?: boolean;
}

/** innerHTML for a card body; `base` is the site base URL for icon paths. */
export function cardHTML(card: OverlayCard, base: string, opts: RenderOpts = {}): string {
  const ic = (s: string) => iconize(esc(s), base);
  const parts: string[] = [];

  const accent = card.accent ? ` style="--ocard-accent:${esc(card.accent)}"` : '';
  parts.push(`<div class="ocard__inner"${accent}>`);

  parts.push('<div class="ocard__head">');
  if (card.icon) {
    parts.push(`<span class="ocard__icon"><img src="${base}${esc(card.icon)}" alt="" /></span>`);
  }
  parts.push('<span class="ocard__title">');
  parts.push(`<span class="ocard__type">${esc(card.type)}</span>`);
  parts.push(`<span class="ocard__name">${esc(card.name)}</span>`);
  parts.push('</span></div>');

  let chips = [...(card.chips || [])];
  if (card.event) {
    if (card.event.trigger) chips.push(card.event.trigger);
    if (card.event.category) chips.push(card.event.category);
    if (card.event.chain && !opts.noSpoilers) chips.push(`Chain: ${card.event.chain.title} (${card.event.chain.size})`);
    if (card.event.dlc) chips.push(card.event.dlc);
  }
  chips = [...new Set(chips)];  // trigger and category are often the same word
  if (chips.length) {
    parts.push('<div class="ocard__chips">');
    for (const ch of chips.slice(0, 4)) parts.push(`<span class="ocard__chip">${esc(ch)}</span>`);
    parts.push('</div>');
  }

  const stats = Object.entries(card.stats || {});
  if (stats.length) {
    parts.push('<div class="ocard__stats">');
    for (const [k, v] of stats) {
      parts.push(`<span class="ocard__stat"><i>${esc(k)}</i><b>${esc(String(v))}</b></span>`);
    }
    parts.push('</div>');
  }

  if (card.cost && card.cost.length) {
    parts.push('<div class="ocard__costs">');
    for (const c of card.cost) parts.push(`<span class="ocard__cost">${ic(c)}</span>`);
    parts.push('</div>');
  }

  if (card.event) {
    // Options rendered the way the event pages do: the option text is the
    // block headline, rewards sit under it, requirements in small print.
    const opts = card.event.options || [];
    parts.push('<div class="ocard__opts">');
    for (const g of (card.event.guaranteed || []).slice(0, 2)) {
      parts.push(`<div class="ocard__optreward ocard__guaranteed">${ic(g)}</div>`);
    }
    for (const [i, o] of opts.slice(0, MAX_OPTIONS).entries()) {
      parts.push('<div class="ocard__opt">');
      parts.push(`<div class="ocard__opttext"><b>${i + 1}.</b> ${esc(o.text || '—')}</div>`);
      if (o.reqs && o.reqs.length) {
        parts.push(`<div class="ocard__optreq">${esc(o.reqs.join(' · '))}</div>`);
      }
      for (const r of (o.rewards || []).slice(0, MAX_REWARDS_PER_OPTION)) {
        parts.push(`<div class="ocard__optreward">${ic(r)}</div>`);
      }
      const extraRewards = (o.rewards || []).length - MAX_REWARDS_PER_OPTION;
      if (extraRewards > 0) {
        parts.push(`<div class="ocard__optreward ocard__more">+${extraRewards} more</div>`);
      }
      // naming the chain itself adds nothing — only show distinct follow-ups
      const next = opts.noSpoilers ? []
        : (o.leadsTo || []).filter((n) => n !== card.event!.chain?.title);
      if (next.length) {
        parts.push(`<div class="ocard__optnext">continues: ${esc(next.join(', '))}</div>`);
      }
      parts.push('</div>');
    }
    if (opts.length > MAX_OPTIONS) {
      parts.push(`<div class="ocard__more">+${opts.length - MAX_OPTIONS} more option${opts.length - MAX_OPTIONS > 1 ? 's' : ''}</div>`);
    }
    parts.push('</div>');
  } else if (card.lines && card.lines.length) {
    parts.push('<ul class="ocard__lines">');
    for (const l of card.lines.slice(0, MAX_LINES)) {
      parts.push(`<li>${ic(l)}</li>`);
    }
    if (card.lines.length > MAX_LINES) {
      parts.push(`<li class="ocard__more">+${card.lines.length - MAX_LINES} more</li>`);
    }
    parts.push('</ul>');
  }

  parts.push('</div>');
  return parts.join('');
}

/** Two units head-to-head — the unit-counters math (src/lib/combat.ts, ported
 *  from Unit.cs) as one overlay: icons, strength, costs, key effects, and the
 *  expected damage each deals the other per attack. */
export function matchupHTML(a: OverlayCard, b: OverlayCard, base: string): string {
  const toCombat = (c: OverlayCard): CombatUnit => ({
    id: c.id, name: c.name, slug: c.slug, iconSlug: '',
    strength: c.combat?.strength || 0,
    traits: c.combat?.traits || [],
    isMelee: !!c.combat?.isMelee,
    isCombat: true, isWater: false, isTribal: false,
    primaryLabel: '', counters: c.combat?.counters || [],
  });
  const ca = toCombat(a), cb = toCombat(b);
  const dealAB = attackDamage(ca, cb);
  const dealBA = attackDamage(cb, ca);

  const side = (c: OverlayCard): string => {
    const abilities = (c.lines || [])
      .filter((l) => !l.startsWith('Upkeep:'))
      .map((l) => l.split(' — ')[0]);
    return `
      <div class="ocard__mside">
        ${c.icon ? `<img class="ocard__micon" src="${base}${esc(c.icon)}" alt="" />` : ''}
        <span class="ocard__mname">${esc(c.name)}</span>
        <span class="ocard__mstr"><i>Str</i><b>${esc(String(c.stats?.Strength ?? '—'))}</b></span>
        <span class="ocard__mcost">${(c.cost || []).map((x) => iconize(esc(x), base)).join('<br/>')}</span>
        <span class="ocard__mfx">${abilities.slice(0, 4).map(esc).join('<br/>')}</span>
      </div>`;
  };

  return `<div class="ocard__inner ocard__inner--matchup">
    <div class="ocard__head"><span class="ocard__title">
      <span class="ocard__type">Matchup</span>
      <span class="ocard__name ocard__name--sm">${esc(a.name)} vs ${esc(b.name)}</span>
    </span></div>
    <div class="ocard__mgrid">
      ${side(a)}
      <div class="ocard__mmid">
        <span class="ocard__mdmg" style="background:${damageTone(dealAB)}"
          title="damage per attack">${dealAB} →</span>
        <span class="ocard__mdmglbl">damage / attack</span>
        <span class="ocard__mdmg" style="background:${damageTone(dealBA)}">← ${dealBA}</span>
      </div>
      ${side(b)}
    </div>
    <div class="ocard__mfoot">per attack at full HP, open terrain — no promotions, generals or fortify</div>
  </div>`;
}
