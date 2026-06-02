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
    status: 'built', sourceSheet: '🎓 Archetypes',
    summary: 'Character archetypes, ratings, and traits',
    willContain: [
      '10 archetypes × four ratings (Wisdom/Charisma/Courage/Discipline)',
      'Signature trait per archetype',
      'Archetype crest art',
    ],
  },
  {
    slug: 'cognomens', icon: '👑', label: 'Cognomens', section: 'Civilizations',
    status: 'built', sourceSheet: '👑Cognomens',
    summary: 'Title/cognomen unlock conditions',
    willContain: ['All cognomens with unlock triggers and bonuses'],
  },
  {
    slug: 'cognomens-tracker', icon: '🧮', label: 'Cognomens Tracker', section: 'Civilizations',
    status: 'built', sourceSheet: '👑Cognomens (Tracker)',
    summary: 'Interactive calculator: which title your leader earns',
    willContain: [
      'Per-stat inputs replaying the exact in-game award routine',
      'Ruler-number and game-speed threshold scaling (from game source)',
      'Per-track progress to the next title',
    ],
  },

  // ── Characters ─────────────────────────────────────────────────
  {
    slug: 'jobs', icon: '💼', label: 'Jobs', section: 'Characters',
    status: 'built', sourceSheet: '💼 Jobs',
    summary: 'Court/governor/general assignments and effects',
    willContain: ['Each job slot, requirements, and ability output formula'],
  },
  {
    slug: 'opinion', icon: '❤️', label: 'Opinion', section: 'Characters',
    status: 'built', sourceSheet: '❤️ Opinion',
    summary: 'How character opinion is calculated',
    willContain: ['Opinion modifier table (gifts, marriage, war, etc.)'],
  },
  {
    slug: 'trait-inheritance', icon: '🧬', label: 'Trait Inheritance', section: 'Characters',
    status: 'built', sourceSheet: '🧬 Trait Inheritance',
    summary: 'How traits pass to children',
    willContain: ['Inheritance odds matrix per trait family'],
  },
  {
    slug: 'study-events', icon: '🎓', label: 'Study Events', section: 'Characters',
    status: 'built', sourceSheet: '🎓 Study Events',
    summary: 'Tutor study event outcomes',
    willContain: ['Each study event, prerequisites, and possible traits gained'],
  },
  {
    slug: 'tutor-events', icon: '📚', label: 'Tutor Events', section: 'Characters',
    status: 'built', sourceSheet: '🎓 Study Events',
    summary: 'Study events grouped by course of study',
  },

  // ── Empire ────────────────────────────────────────────────────
  {
    slug: 'rural-improvements', icon: '⛏️', label: 'Rural Improvements', section: 'Empire',
    status: 'built', sourceSheet: '⛏️ Rural Improvements',
    summary: 'Tile improvements, yields, and adjacency',
    willContain: ['Yield, cost, prerequisites, and adjacency bonuses'],
  },
  {
    slug: 'urban-improvements', icon: '🏡', label: 'Urban Improvements', section: 'Empire',
    status: 'built', sourceSheet: '🏡 Urban Buildings',
    summary: 'City buildings — art, specialist slots, and effects',
    willContain: ['Cost, slots, yield, and required terrain/tech'],
  },
  {
    slug: 'shrines', icon: '🔱', label: 'Shrines', section: 'Empire',
    status: 'built', sourceSheet: '🔱 Shrines',
    summary: 'Shrine pool, yields per tier',
    willContain: ['All shrine outcomes, which nations roll which'],
  },
  {
    slug: 'world-religion-buildings', icon: '🕍', label: 'World Religion Buildings', section: 'Empire',
    status: 'built', sourceSheet: '🕍 World Religion Buildings',
    summary: 'Religion-specific worship buildings',
    willContain: ['Building × religion grid with yields'],
  },
  {
    slug: 'theologies', icon: '🙏', label: 'Theologies', section: 'Empire',
    status: 'built', sourceSheet: '🙏 Theologies',
    summary: 'Religion picks and effects',
    willContain: ['Each theology tier with options and impact'],
  },
  {
    slug: 'wonders', icon: '🏛️', label: 'Wonders', section: 'Empire',
    status: 'built', sourceSheet: '🏛️ Wonders',
    summary: 'Cost, prerequisites, and yields',
    willContain: ['Wonder grid: tech req, civic req, cost, build bonus, ongoing bonus'],
  },
  {
    slug: 'laws', icon: '⚖️', label: 'Laws', section: 'Empire',
    status: 'built', sourceSheet: '⚖️ Laws',
    summary: 'Law pairs and their effects',
    willContain: ['All law pairs grouped by civic tier'],
  },
  {
    slug: 'harvest-events', icon: '🌾', label: 'Harvest Events', section: 'Empire',
    status: 'built', sourceSheet: '🌾 Harvest Events',
    summary: 'Harvest events grouped by resource, with option rewards',
    willContain: ['Each harvest event and its option rewards'],
  },
  {
    // Split into Urban Specialists + Rural Specialists. Slug kept as a
    // redirect; not surfaced in nav/index.
    slug: 'specialists', icon: '👨‍🌾', label: 'Specialists', section: 'Empire',
    status: 'skipped', sourceSheet: '👨‍🌾 Specialists',
    summary: 'Tile/building specialists and yields',
    willContain: ['Specialist type × yield per slot'],
  },
  {
    slug: 'urban-specialists', icon: '🏺', label: 'Urban Specialists', section: 'Empire',
    status: 'built', sourceSheet: '👨‍🌾 Specialists',
    summary: 'Tiered urban specialists (I/II/III), art, yields, slots',
    willContain: ['Each urban specialist class × tier yields and which buildings it slots into'],
  },
  {
    slug: 'rural-specialists', icon: '🌾', label: 'Rural Specialists', section: 'Empire',
    status: 'built', sourceSheet: '👨‍🌾 Specialists',
    summary: 'Rural specialists, art, yields, and slots',
    willContain: ['Each rural specialist class, yields, and which improvements it slots into'],
  },
  {
    slug: 'hurrying', icon: '⏩', label: 'Hurrying Production', section: 'Empire',
    status: 'built', sourceSheet: '⏩ Hurrying Production',
    summary: 'Hurry costs and yield equivalents',
    willContain: ['Hurry conversion math per resource'],
  },

  // ── Technology ────────────────────────────────────────────────
  {
    slug: 'technologies', icon: '🔮', label: 'Technologies', section: 'Technology',
    status: 'built', sourceSheet: '🔮Technologies',
    summary: 'Tech tree with prerequisites and unlocks',
    willContain: ['Each tech: era, cost, prerequisites, unlocks'],
  },

  // ── Military ──────────────────────────────────────────────────
  {
    slug: 'units', icon: '🛡️', label: 'Units', section: 'Military',
    status: 'built', sourceSheet: '🛡️ Units',
    summary: 'Standard buildable units: stats, cost, upkeep, counters',
    willContain: ['Each unit: class, strength, move, range, cost, tech, counters'],
  },
  {
    slug: 'unique-units', icon: '⭐', label: 'Unique Units', section: 'Military',
    status: 'built', sourceSheet: '⭐ Unique Units',
    summary: 'Nation-unique units by civilization and Culture tier',
    willContain: ['Each unique unit: nation, tier, class, stats, counters'],
  },
  {
    slug: 'promotions', icon: '🎖️', label: 'Promotions', section: 'Military',
    status: 'built', sourceSheet: '🎖️ Promotions',
    summary: 'Promotion tree, prerequisites, effects',
    willContain: ['Each promotion: stat changes, prereq promotions'],
  },
  {
    slug: 'combat-damage', icon: '⚔️', label: 'Combat Damage Formula', section: 'Military',
    status: 'built', sourceSheet: '⚔️ Combat Damage Formula',
    summary: 'How combat math works',
    willContain: ['Damage formula, modifiers, worked examples'],
  },
  {
    slug: 'unit-counters', icon: '⚔️', label: 'Unit Counters at-a-glance', section: 'Military',
    status: 'built', sourceSheet: '⚔️ Unit Counters at-a-glance',
    summary: 'Quick rock-paper-scissors chart',
    willContain: ['Unit type counter matrix'],
  },
  {
    slug: 'unit-damage', icon: '⚔️', label: 'Unit Damage & Counters', section: 'Military',
    status: 'built', sourceSheet: '⚔️ Unit Damage & Counters',
    summary: 'Full unit × unit damage table',
    willContain: ['Expected damage by attacker/defender pair'],
  },

  // ── Mechanics ─────────────────────────────────────────────────
  {
    slug: 'events', icon: '🧭', label: 'Exploration Events', section: 'Mechanics',
    status: 'built', sourceSheet: '',
    summary: 'Ruins & expedition events — triggers, odds, options, rewards',
    willContain: [
      'Ruins-tile events with eligibility conditions and weighted odds',
      'Expedition (explore distant lands) chains, incl. follow-ups',
      'Each option’s requirements and outcome rewards',
    ],
  },
  {
    slug: 'rally', icon: '📯', label: 'Rally Troops', section: 'Mechanics',
    status: 'built', sourceSheet: '📈 Rally  Hold Court  Steal Res',
    summary: 'Leader mission: Training yields, dice outcomes',
  },
  {
    slug: 'hold-court', icon: '⚖️', label: 'Hold Court', section: 'Mechanics',
    status: 'built', sourceSheet: '📈 Rally  Hold Court  Steal Res',
    summary: 'Judge mission: Civics, courtier chance, event chance',
  },
  {
    slug: 'steal-research', icon: '🕵', label: 'Steal Research', section: 'Mechanics',
    status: 'built', sourceSheet: '📈 Rally  Hold Court  Steal Res',
    summary: 'Spymaster mission: Science from rival, with exposure risk',
  },
  {
    slug: 'religious-conversion', icon: '🙏', label: 'Religious Conversion', section: 'Mechanics',
    status: 'built', sourceSheet: '🙏 Religious Conversion Mechani',
    summary: 'How religion spreads between cities',
    willContain: ['Spread formula, modifiers, examples'],
  },

  // ── Character Skills ─────────────────────────────────────────
  {
    slug: 'stat-scaling', icon: '📈', label: 'Stat Scaling', section: 'Character Skills',
    status: 'built', sourceSheet: '🟣 Wisdom Base / CM (+ Charisma, Courage, Discipline)',
    summary: 'Per-rating yield/combat scaling by role, Non-competitive vs Competitive',
    willContain: ['All 4 stats, rating −3..+15, Leader/Governor/Agent/General, both modes'],
  },
  {
    slug: 'wisdom', icon: '🟣', label: 'Wisdom', section: 'Character Skills',
    status: 'built', sourceSheet: '🟣 Wisdom Base',
    summary: 'Base bonuses + commander effects',
    willContain: ['Wisdom Base sheet + Wisdom CM (commander) sheet'],
  },
  {
    slug: 'charisma', icon: '🧡', label: 'Charisma', section: 'Character Skills',
    status: 'built', sourceSheet: '🧡 Charisma Base',
    summary: 'Base bonuses + commander effects',
    willContain: ['Charisma Base sheet + Charisma CM (commander) sheet'],
  },
  {
    slug: 'courage', icon: '🔺', label: 'Courage', section: 'Character Skills',
    status: 'built', sourceSheet: '🔺 Courage Base',
    summary: 'Base bonuses + commander effects',
    willContain: ['Courage Base sheet + Courage CM (commander) sheet'],
  },
  {
    slug: 'discipline', icon: '⚡', label: 'Discipline', section: 'Character Skills',
    status: 'built', sourceSheet: '⚡ Discipline Base',
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
