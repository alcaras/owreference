// Catalog of every reference page. Drives the index, nav, and the dynamic
// placeholder route. When a tab gets its own dedicated page (like nations),
// keep its entry here so it shows up in nav — Astro's static `nations.astro`
// will win over the dynamic `[slug].astro` route.

export type TabStatus = 'built' | 'placeholder' | 'skipped';

export interface Tab {
  slug: string;
  label: string;           // Display name (no emoji)
  icon: string;            // The emoji from the original sheet
  section: string;         // Group on the index
  status: TabStatus;
  sourceSheet: string;     // Original xlsx sheet name (for traceability)
  summary: string;         // 1-line description for the index card
  // What this page will contain once built — feeds the placeholder body so the
  // design pass and future implementers have context without opening the xlsx.
  willContain?: string[];
}

export const TABS: Tab[] = [
  // ── Civilizations ──────────────────────────────────────────────
  {
    slug: 'nations', icon: '👑', label: 'Nations', section: 'Civilizations',
    status: 'built', sourceSheet: '👑 Nations',
    summary: 'Bonuses, shrines, unique units, families, leaders',
  },
  {
    slug: 'families', icon: '👪', label: 'Families', section: 'Civilizations',
    status: 'built', sourceSheet: '👪 Families',
    summary: 'Class bonuses, opinion modifiers, signature traits',
    willContain: [
      'Family class (Champions, Hunters, Riders, …) × ability matrix',
      'Family seat bonus and unlock requirements',
      'Per-family opinion modifiers',
    ],
  },
  {
    slug: 'archetypes', icon: '🎓', label: 'Archetypes', section: 'Civilizations',
    status: 'placeholder', sourceSheet: '🎓 Archetypes',
    summary: 'Character archetypes, ratings, and traits',
    willContain: [
      '10 archetypes × four ratings (Wisdom/Charisma/Courage/Discipline)',
      'Signature trait per archetype',
      'Archetype crest art',
    ],
  },
  {
    slug: 'cognomens', icon: '👑', label: 'Cognomens', section: 'Civilizations',
    status: 'placeholder', sourceSheet: '👑Cognomens',
    summary: 'Title/cognomen unlock conditions',
    willContain: ['All cognomens with unlock triggers and bonuses'],
  },

  // ── Characters ─────────────────────────────────────────────────
  {
    slug: 'jobs', icon: '💼', label: 'Jobs', section: 'Characters',
    status: 'placeholder', sourceSheet: '💼 Jobs',
    summary: 'Court/governor/general assignments and effects',
    willContain: ['Each job slot, requirements, and ability output formula'],
  },
  {
    slug: 'opinion', icon: '❤️', label: 'Opinion', section: 'Characters',
    status: 'placeholder', sourceSheet: '❤️ Opinion',
    summary: 'How character opinion is calculated',
    willContain: ['Opinion modifier table (gifts, marriage, war, etc.)'],
  },
  {
    slug: 'trait-inheritance', icon: '🧬', label: 'Trait Inheritance', section: 'Characters',
    status: 'placeholder', sourceSheet: '🧬 Trait Inheritance',
    summary: 'How traits pass to children',
    willContain: ['Inheritance odds matrix per trait family'],
  },
  {
    slug: 'study-events', icon: '🎓', label: 'Study Events', section: 'Characters',
    status: 'placeholder', sourceSheet: '🎓 Study Events',
    summary: 'Tutor study event outcomes',
    willContain: ['Each study event, prerequisites, and possible traits gained'],
  },

  // ── Empire ────────────────────────────────────────────────────
  {
    slug: 'rural-improvements', icon: '⛏️', label: 'Rural Improvements', section: 'Empire',
    status: 'placeholder', sourceSheet: '⛏️ Rural Improvements',
    summary: 'Tile improvements, yields, and adjacency',
    willContain: ['Yield, cost, prerequisites, and adjacency bonuses'],
  },
  {
    slug: 'urban-buildings', icon: '🏡', label: 'Urban Buildings', section: 'Empire',
    status: 'placeholder', sourceSheet: '🏡 Urban Buildings',
    summary: 'Buildings, specialist slots, and effects',
    willContain: ['Cost, slots, yield, and required terrain/tech'],
  },
  {
    slug: 'shrines', icon: '🔱', label: 'Shrines', section: 'Empire',
    status: 'placeholder', sourceSheet: '🔱 Shrines',
    summary: 'Shrine pool, yields per tier',
    willContain: ['All shrine outcomes, which nations roll which'],
  },
  {
    slug: 'world-religion-buildings', icon: '🕍', label: 'World Religion Buildings', section: 'Empire',
    status: 'placeholder', sourceSheet: '🕍 World Religion Buildings',
    summary: 'Religion-specific worship buildings',
    willContain: ['Building × religion grid with yields'],
  },
  {
    slug: 'theologies', icon: '🙏', label: 'Theologies', section: 'Empire',
    status: 'placeholder', sourceSheet: '🙏 Theologies',
    summary: 'Religion picks and effects',
    willContain: ['Each theology tier with options and impact'],
  },
  {
    slug: 'wonders', icon: '🏛️', label: 'Wonders', section: 'Empire',
    status: 'placeholder', sourceSheet: '🏛️ Wonders',
    summary: 'Cost, prerequisites, and yields',
    willContain: ['Wonder grid: tech req, civic req, cost, build bonus, ongoing bonus'],
  },
  {
    slug: 'laws', icon: '⚖️', label: 'Laws', section: 'Empire',
    status: 'placeholder', sourceSheet: '⚖️ Laws',
    summary: 'Law pairs and their effects',
    willContain: ['All law pairs grouped by civic tier'],
  },
  {
    slug: 'harvest-events', icon: '🌾', label: 'Harvest Events', section: 'Empire',
    status: 'placeholder', sourceSheet: '🌾 Harvest Events',
    summary: 'Random harvest outcomes',
    willContain: ['Each harvest event and odds'],
  },
  {
    slug: 'specialists', icon: '👨‍🌾', label: 'Specialists', section: 'Empire',
    status: 'placeholder', sourceSheet: '👨‍🌾 Specialists',
    summary: 'Tile/building specialists and yields',
    willContain: ['Specialist type × yield per slot'],
  },
  {
    slug: 'hurrying', icon: '⏩', label: 'Hurrying Production', section: 'Empire',
    status: 'placeholder', sourceSheet: '⏩ Hurrying Production',
    summary: 'Hurry costs and yield equivalents',
    willContain: ['Hurry conversion math per resource'],
  },

  // ── Technology ────────────────────────────────────────────────
  {
    slug: 'technologies', icon: '🔮', label: 'Technologies', section: 'Technology',
    status: 'placeholder', sourceSheet: '🔮Technologies',
    summary: 'Tech tree with prerequisites and unlocks',
    willContain: ['Each tech: era, cost, prerequisites, unlocks'],
  },

  // ── Military ──────────────────────────────────────────────────
  {
    slug: 'promotions', icon: '🎖️', label: 'Promotions', section: 'Military',
    status: 'placeholder', sourceSheet: '🎖️ Promotions',
    summary: 'Promotion tree, prerequisites, effects',
    willContain: ['Each promotion: stat changes, prereq promotions'],
  },
  {
    slug: 'combat-damage', icon: '⚔️', label: 'Combat Damage Formula', section: 'Military',
    status: 'placeholder', sourceSheet: '⚔️ Combat Damage Formula',
    summary: 'How combat math works',
    willContain: ['Damage formula, modifiers, worked examples'],
  },
  {
    slug: 'unit-counters', icon: '⚔️', label: 'Unit Counters at-a-glance', section: 'Military',
    status: 'placeholder', sourceSheet: '⚔️ Unit Counters at-a-glance',
    summary: 'Quick rock-paper-scissors chart',
    willContain: ['Unit type counter matrix'],
  },
  {
    slug: 'unit-damage', icon: '⚔️', label: 'Unit Damage & Counters', section: 'Military',
    status: 'placeholder', sourceSheet: '⚔️ Unit Damage & Counters',
    summary: 'Full unit × unit damage table',
    willContain: ['Expected damage by attacker/defender pair'],
  },

  // ── Mechanics ─────────────────────────────────────────────────
  {
    slug: 'rally-court-steal', icon: '📈', label: 'Rally / Hold Court / Steal Resources', section: 'Mechanics',
    status: 'placeholder', sourceSheet: '📈 Rally  Hold Court  Steal Res',
    summary: 'Mission outcome math',
    willContain: ['Probability tables for each mission type'],
  },
  {
    slug: 'religious-conversion', icon: '🙏', label: 'Religious Conversion', section: 'Mechanics',
    status: 'placeholder', sourceSheet: '🙏 Religious Conversion Mechani',
    summary: 'How religion spreads between cities',
    willContain: ['Spread formula, modifiers, examples'],
  },

  // ── Character Skills ─────────────────────────────────────────
  {
    slug: 'wisdom', icon: '🟣', label: 'Wisdom', section: 'Character Skills',
    status: 'placeholder', sourceSheet: '🟣 Wisdom Base',
    summary: 'Base bonuses + commander effects',
    willContain: ['Wisdom Base sheet + Wisdom CM (commander) sheet'],
  },
  {
    slug: 'charisma', icon: '🧡', label: 'Charisma', section: 'Character Skills',
    status: 'placeholder', sourceSheet: '🧡 Charisma Base',
    summary: 'Base bonuses + commander effects',
    willContain: ['Charisma Base sheet + Charisma CM (commander) sheet'],
  },
  {
    slug: 'courage', icon: '🔺', label: 'Courage', section: 'Character Skills',
    status: 'placeholder', sourceSheet: '🔺 Courage Base',
    summary: 'Base bonuses + commander effects',
    willContain: ['Courage Base sheet + Courage CM (commander) sheet'],
  },
  {
    slug: 'discipline', icon: '⚡', label: 'Discipline', section: 'Character Skills',
    status: 'placeholder', sourceSheet: '⚡ Discipline Base',
    summary: 'Base bonuses + commander effects',
    willContain: ['Discipline Base sheet + Discipline CM (commander) sheet'],
  },
];

export const SECTIONS = [
  'Civilizations',
  'Characters',
  'Empire',
  'Technology',
  'Military',
  'Mechanics',
  'Character Skills',
] as const;
