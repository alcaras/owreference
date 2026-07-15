// Combat damage math, mirrored from the game source (verified against
// reference/Source/Base/Game/GameCore/Unit.cs and InfoHelpers.cs):
//
//   attackUnitStrength / defendUnitStrength — base strength × (100 + Σ
//   modifiers)/100. The anti-trait modifiers we model are the unit-vs-trait
//   ones (aiUnitTraitModifier both ways, aiUnitTraitModifierAttack on
//   attack, aiUnitTraitModifierMelee when the MELEE side applies);
//   situational ones (terrain, flanking, promotions, generals, damage
//   state) are deliberately excluded — same baseline as the legacy
//   spreadsheet's matrix.
//
//   InfoHelpers.getAttackDamage: damage = BASE_DAMAGE * StrAtt / StrDef,
//   +(StrDef-1) before the divide when StrAtt > StrDef (i.e. round UP in
//   the stronger attacker's favor, floor otherwise), minimum 1.
//
// BASE_DAMAGE = 6 (globalsInt.xml). Strengths in units.json are ×10
// internal units (Cataphract 100 = display 10).

export const BASE_DAMAGE = 6;

export interface CombatCounter {
  kind: string;       // 'vs' | 'melee vs' | 'attack vs' | 'attack' (pattern, ignored)
  target: string;     // trait label, e.g. 'Mounted'
  value: number;      // percent
}

export interface CombatUnit {
  id: string;
  name: string;
  slug: string;
  iconSlug: string;
  strength: number;   // ×10 internal scale
  traits: string[];
  isMelee: boolean;
  isCombat: boolean;
  isWater: boolean;
  isTribal: boolean;
  primaryLabel: string;
  nationLabel?: string | null;
  counters: CombatCounter[];
}

/** Σ of this unit's anti-trait bonuses applicable against `otherTraits`. */
export function counterBonus(
  u: CombatUnit,
  otherTraits: string[],
  attacking: boolean,
  attackerIsMelee: boolean,
): number {
  let b = 0;
  for (const c of u.counters) {
    if (!otherTraits.includes(c.target)) continue;
    if (c.kind === 'vs') b += c.value;
    else if (c.kind === 'melee vs' && (attacking ? u.isMelee : attackerIsMelee)) b += c.value;
    else if (c.kind === 'attack vs' && attacking) b += c.value;
    else if (c.kind === 'defense vs' && !attacking) b += c.value;
  }
  return b;
}

/** Damage per attack, att → def, full HP, open terrain, no promotions. */
export function attackDamage(att: CombatUnit, def: CombatUnit): number {
  const effA = Math.floor(att.strength * (100 + counterBonus(att, def.traits, true, att.isMelee)) / 100);
  const effD = Math.floor(def.strength * (100 + counterBonus(def, att.traits, false, att.isMelee)) / 100);
  if (effA <= 0 || effD <= 0) return 0;
  let d = BASE_DAMAGE * effA;
  if (effA > effD) d += effD - 1;
  return Math.max(1, Math.floor(d / effD));
}

/** Raw strength-only damage (the Combat Damage Formula lookup table). */
export function rawDamage(strAtt: number, strDef: number): number {
  if (strAtt <= 0 || strDef <= 0) return 0;
  let d = BASE_DAMAGE * strAtt;
  if (strAtt > strDef) d += strDef - 1;
  return Math.max(1, Math.floor(d / strDef));
}

/** Heatmap tone for a damage value, matching the legacy sheet's red-hot /
 *  gold-mid / blue-cold read, adapted to the dark theme. Returns a CSS
 *  background-color string. Scale anchors: 6 = even fight. */
export function damageTone(d: number): string {
  if (d >= 12) return 'color-mix(in srgb, #c25555 52%, var(--bg-elev))';
  if (d >= 9)  return 'color-mix(in srgb, #c25555 34%, var(--bg-elev))';
  if (d >= 7)  return 'color-mix(in srgb, #c98b46 30%, var(--bg-elev))';
  if (d === 6) return 'color-mix(in srgb, #c9a04a 18%, var(--bg-elev))';
  if (d >= 4)  return 'color-mix(in srgb, #4e84b8 16%, var(--bg-elev))';
  return 'color-mix(in srgb, #4e84b8 30%, var(--bg-elev))';
}
