// Runtime helpers around src/data/entities.json — the registry of every
// linkable thing in the site. Used by the <Term> component and the auto-
// linker that wraps known aliases in user-facing strings.

import entitiesData from '../data/entities.json';

export interface Entity {
  id: string;
  slug: string;
  type: 'yield' | 'concept' | 'nation' | 'family' | 'tech' | 'resource' | 'unit' | 'law';
  name: string;
  aliases: string[];
  page: string;
  icon?: string | null;
  color?: string;
}

export interface AliasIndexEntry {
  alias: string;
  id: string;
}

export interface EntitiesPayload {
  entities: Entity[];
  aliasIndex: AliasIndexEntry[];
  yieldColors: Record<string, string>;
}

const data = entitiesData as EntitiesPayload;
export const entities: Entity[] = data.entities;
export const yieldColors: Record<string, string> = data.yieldColors;

const byId: Record<string, Entity> = Object.fromEntries(entities.map(e => [e.id, e]));
const bySlug: Record<string, Entity> = Object.fromEntries(entities.map(e => [`${e.type}:${e.slug}`, e]));

export function getEntity(id: string): Entity | undefined {
  return byId[id];
}

export function getEntityBySlug(type: Entity['type'], slug: string): Entity | undefined {
  return bySlug[`${type}:${slug}`];
}

// Pre-compiled regex matching any known alias. Word-bounded.
// Sorted longest-first so "Heavy Cavalry" beats "Cavalry".
const aliasPattern: RegExp = (() => {
  const escaped = data.aliasIndex.map(a => a.alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  // Use boundaries that work for words like "Sci" inside "Science"
  // \b doesn't work great for non-word chars (e.g. emojis); use lookarounds.
  return new RegExp(`(?<![A-Za-z0-9])(${escaped.join('|')})(?![A-Za-z0-9])`, 'g');
})();

const aliasToEntity: Map<string, Entity> = (() => {
  const m = new Map<string, Entity>();
  for (const { alias, id } of data.aliasIndex) {
    const e = byId[id];
    if (e && !m.has(alias)) m.set(alias, e);  // first wins (already sorted longest)
  }
  return m;
})();

export interface LinkedSegment {
  text: string;
  entity?: Entity;
}

// Split `text` into segments, marking known aliases.
// Each segment is either plain text or a linked-to entity.
export function linkify(text: string): LinkedSegment[] {
  if (!text) return [];
  const segments: LinkedSegment[] = [];
  let lastIdx = 0;
  aliasPattern.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = aliasPattern.exec(text)) !== null) {
    if (match.index > lastIdx) {
      segments.push({ text: text.slice(lastIdx, match.index) });
    }
    const e = aliasToEntity.get(match[0]);
    segments.push({ text: match[0], entity: e });
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < text.length) segments.push({ text: text.slice(lastIdx) });
  return segments;
}

// Classify a free-text bonus by the first yield/concept it mentions.
// Returns the yield key (e.g. "ORDERS", "SCIENCE") or null.
export function classifyYield(text: string): string | null {
  const segs = linkify(text);
  for (const s of segs) {
    if (s.entity && (s.entity.type === 'yield' || s.entity.type === 'concept')) {
      // Pull the underlying YIELD_ key from the id (CONCEPT_ORDER → ORDERS, YIELD_ORDERS → ORDERS)
      if (s.entity.id.startsWith('YIELD_')) return s.entity.id.slice(6);
      if (s.entity.id.startsWith('CONCEPT_')) {
        // Map concept slugs to yield keys
        const conceptToYield: Record<string, string> = {
          order: 'ORDERS', training: 'TRAINING', civics: 'CIVICS', culture: 'CULTURE',
          science: 'SCIENCE', money: 'MONEY', growth: 'GROWTH', food: 'FOOD',
          wood: 'WOOD', stone: 'STONE', iron: 'IRON', happiness: 'HAPPINESS',
          discontent: 'DISCONTENT', influence: 'INFLUENCE', intrigue: 'INTRIGUE',
          legitimacy: 'LEGITIMACY',
        };
        return conceptToYield[s.entity.slug] ?? null;
      }
    }
  }
  return null;
}
