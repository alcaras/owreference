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
    slug: 'nations', icon: '👑', label: 'Nations', section: 'Nations & Families',
    status: 'built', sourceSheet: '👑 Nations',
    summary: 'Bonuses, shrines, unique units, families, leaders',
  },
  {
    slug: 'families', icon: '👪', label: 'Families', section: 'Nations & Families',
    status: 'built', sourceSheet: '👪 Families',
    summary: 'Class bonuses, opinion modifiers, signature traits',
    willContain: [
      'Family class (Champions, Hunters, Riders, …) × ability matrix',
      'Family seat bonus and unlock requirements',
      'Per-family opinion modifiers',
    ],
  },
  {
    slug: 'archetypes', icon: '🎓', label: 'Archetypes', section: 'Characters',
    status: 'built', sourceSheet: '🎓 Archetypes',
    summary: 'Character archetypes, ratings, and traits',
    willContain: [
      '10 archetypes × four ratings (Wisdom/Charisma/Courage/Discipline)',
      'Signature trait per archetype',
      'Archetype crest art',
    ],
  },
  {
    slug: 'archetype-tendencies', icon: '🎲', label: 'Archetype Tendencies', section: 'Nations & Families',
    status: 'built', sourceSheet: '👑👪🎓 Nations, Families, and Archetype Tendencies',
    summary: 'Which families of each nation roll which archetypes (×10/×5 weights)',
  },
  {
    slug: 'cognomens', icon: '👑', label: 'Cognomens', section: 'Characters',
    status: 'built', sourceSheet: '👑Cognomens',
    summary: 'Title/cognomen unlock conditions',
    willContain: ['All cognomens with unlock triggers and bonuses'],
  },
  {
    slug: 'cognomens-tracker', icon: '🧮', label: 'Cognomens Tracker', section: 'Characters',
    status: 'built', sourceSheet: '👑Cognomens (Tracker)',
    summary: 'Interactive calculator: which title your leader earns',
    willContain: [
      'Per-stat inputs replaying the exact in-game award routine',
      'Ruler-number and game-speed threshold scaling (from game source)',
      'Per-track progress to the next title',
    ],
  },

  {
    slug: 'tribes', icon: '🏕️', label: 'Tribes', section: 'Nations & Families',
    status: 'built', sourceSheet: '',
    summary: 'Barbarian tribes — levels, units, sites, diplomacy',
  },

  // ── Characters ─────────────────────────────────────────────────
  {
    slug: 'jobs', icon: '💼', label: 'Jobs', section: 'Court & Missions',
    status: 'built', sourceSheet: '💼 Jobs',
    summary: 'Court/governor/general assignments and effects',
    willContain: ['Each job slot, requirements, and ability output formula'],
  },
  {
    slug: 'council', icon: '🏛️', label: 'Council & Courtiers', section: 'Court & Missions',
    status: 'built', sourceSheet: '',
    summary: 'Council seats (triangular rating yields) and the four courtier types',
  },
  {
    slug: 'opinion', icon: '❤️', label: 'Opinion', section: 'Characters',
    status: 'built', sourceSheet: '❤️ Opinion',
    summary: 'How character opinion is calculated',
    willContain: ['Opinion modifier table (gifts, marriage, war, etc.)'],
  },
  {
    slug: 'traits', icon: '🎭', label: 'Traits', section: 'Characters',
    status: 'built', sourceSheet: '',
    summary: 'Full trait catalog — ratings, effects, opinions, restrictions',
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
    slug: 'rural-improvements', icon: '⛏️', label: 'Rural Improvements', section: 'Cities',
    status: 'built', sourceSheet: '⛏️ Rural Improvements',
    summary: 'Tile improvements, yields, and adjacency',
    willContain: ['Yield, cost, prerequisites, and adjacency bonuses'],
  },
  {
    slug: 'urban-improvements', icon: '🏡', label: 'Urban Improvements', section: 'Cities',
    status: 'built', sourceSheet: '🏡 Urban Buildings',
    summary: 'City buildings — art, specialist slots, and effects',
    willContain: ['Cost, slots, yield, and required terrain/tech'],
  },
  {
    slug: 'shrines', icon: '🔱', label: 'Shrines', section: 'Religion',
    status: 'built', sourceSheet: '🔱 Shrines',
    summary: 'Shrine pool, yields per tier',
    willContain: ['All shrine outcomes, which nations roll which'],
  },
  {
    slug: 'world-religion-buildings', icon: '🕍', label: 'World Religion Buildings', section: 'Religion',
    status: 'built', sourceSheet: '🕍 World Religion Buildings',
    summary: 'Religion-specific worship buildings',
    willContain: ['Building × religion grid with yields'],
  },
  {
    slug: 'theologies', icon: '🙏', label: 'Theologies', section: 'Religion',
    status: 'built', sourceSheet: '🙏 Theologies',
    summary: 'Religion picks and effects',
    willContain: ['Each theology tier with options and impact'],
  },
  {
    slug: 'wonders', icon: '🏛️', label: 'Wonders', section: 'Cities',
    status: 'built', sourceSheet: '🏛️ Wonders',
    summary: 'Cost, prerequisites, and yields',
    willContain: ['Wonder grid: tech req, civic req, cost, build bonus, ongoing bonus'],
  },
  {
    slug: 'projects', icon: '🏗️', label: 'Projects', section: 'Cities',
    status: 'built', sourceSheet: '',
    summary: 'City projects — cost, prerequisites, and effects',
  },
  {
    slug: 'ambitions', icon: '🏆', label: 'Ambitions', section: 'Empire',
    status: 'built', sourceSheet: '',
    summary: 'All 400+ ambition goals by tier and class, plus victory types',
  },
  {
    slug: 'turn-order', icon: '🔄', label: 'Turn Order', section: 'Empire',
    status: 'built', sourceSheet: '',
    summary: 'Exact order of operations at turn start — rollover and per-player, from the game code',
  },
  {
    slug: 'laws', icon: '⚖️', label: 'Laws', section: 'Empire',
    status: 'built', sourceSheet: '⚖️ Laws',
    summary: 'Law pairs and their effects',
    willContain: ['All law pairs grouped by civic tier'],
  },
  {
    slug: 'harvest-events', icon: '🌾', label: 'Harvest Events', section: 'Events',
    status: 'built', sourceSheet: '🌾 Harvest Events',
    summary: 'Harvest events grouped by resource, with option rewards',
    willContain: ['Each harvest event and its option rewards'],
  },
  {
    // Split into Urban Specialists + Rural Specialists. Slug kept as a
    // redirect; not surfaced in nav/index.
    slug: 'specialists', icon: '👨‍🌾', label: 'Specialists', section: 'Cities',
    status: 'skipped', sourceSheet: '👨‍🌾 Specialists',
    summary: 'Tile/building specialists and yields',
    willContain: ['Specialist type × yield per slot'],
  },
  {
    slug: 'urban-specialists', icon: '🏺', label: 'Urban Specialists', section: 'Cities',
    status: 'built', sourceSheet: '👨‍🌾 Specialists',
    summary: 'Tiered urban specialists (I/II/III), art, yields, slots',
    willContain: ['Each urban specialist class × tier yields and which buildings it slots into'],
  },
  {
    slug: 'rural-specialists', icon: '🌾', label: 'Rural Specialists', section: 'Cities',
    status: 'built', sourceSheet: '👨‍🌾 Specialists',
    summary: 'Rural specialists, art, yields, and slots',
    willContain: ['Each rural specialist class, yields, and which improvements it slots into'],
  },
  {
    slug: 'culture', icon: '🎭', label: 'Culture & Development', section: 'Cities',
    status: 'built', sourceSheet: '',
    summary: 'City culture levels — thresholds, VP, consumption, and unlocks',
  },
  {
    slug: 'hurrying', icon: '⏩', label: 'Hurrying Production', section: 'Cities',
    status: 'built', sourceSheet: '⏩ Hurrying Production',
    summary: 'Hurry costs and yield equivalents',
    willContain: ['Hurry conversion math per resource'],
  },

  // ── Technology ────────────────────────────────────────────────
  {
    slug: 'technologies', icon: '🔮', label: 'Technologies', section: 'Empire',
    status: 'built', sourceSheet: '🔮Technologies',
    summary: 'Tech tree with prerequisites and unlocks',
    willContain: ['Each tech: era, cost, prerequisites, unlocks'],
  },

  // ── Military ──────────────────────────────────────────────────
  {
    slug: 'units', icon: '🛡️', label: 'Units', section: 'Units',
    status: 'built', sourceSheet: '🛡️ Units',
    summary: 'Standard buildable units: stats, cost, upkeep, counters',
    willContain: ['Each unit: class, strength, move, range, cost, tech, counters'],
  },
  {
    slug: 'military-units', icon: '⚔️', label: 'Military Units', section: 'Units',
    status: 'built', sourceSheet: '🛡️ Units',
    summary: 'Combat units only: stats, cost, upkeep, counters',
    willContain: ['Each combat unit: class, strength, move, range, cost, tech, counters'],
  },
  {
    slug: 'civilian-units', icon: '⚒️', label: 'Civilian Units', section: 'Units',
    status: 'built', sourceSheet: '🛡️ Units',
    summary: 'Non-combat units only: workers, settlers, scouts',
    willContain: ['Each civilian unit: move, range, cost, tech, abilities'],
  },
  {
    slug: 'unique-units', icon: '⭐', label: 'Unique Units', section: 'Units',
    status: 'built', sourceSheet: '⭐ Unique Units',
    summary: 'Nation-unique units by civilization and Culture tier',
    willContain: ['Each unique unit: nation, tier, class, stats, counters'],
  },
  {
    slug: 'promotions', icon: '🎖️', label: 'Promotions', section: 'Combat',
    status: 'built', sourceSheet: '🎖️ Promotions',
    summary: 'Promotion tree, prerequisites, effects',
    willContain: ['Each promotion: stat changes, prereq promotions'],
  },
  {
    slug: 'combat-damage', icon: '⚔️', label: 'Combat Damage Formula', section: 'Combat',
    status: 'built', sourceSheet: '⚔️ Combat Damage Formula',
    summary: 'How combat math works',
    willContain: ['Damage formula, modifiers, worked examples'],
  },
  {
    slug: 'unit-counters', icon: '⚔️', label: 'Unit Counters at-a-glance', section: 'Combat',
    status: 'built', sourceSheet: '⚔️ Unit Counters at-a-glance',
    summary: 'Quick rock-paper-scissors chart',
    willContain: ['Unit type counter matrix'],
  },
  {
    slug: 'unit-damage', icon: '⚔️', label: 'Unit Damage & Counters', section: 'Combat',
    status: 'built', sourceSheet: '⚔️ Unit Damage & Counters',
    summary: 'Full unit × unit damage table',
    willContain: ['Expected damage by attacker/defender pair'],
  },
  {
    slug: 'city-capture-mechanics', icon: '🏰', label: 'City Capture Mechanics', section: 'Combat',
    status: 'built', sourceSheet: '',
    summary: 'How long a city takes to flip after you occupy it',
    willContain: [
      'Capture-turns counter: +1/turn occupying, −1/turn when not',
      'Threshold = base 2 + enemy culture level + original-founder bonus',
      'Turns-to-flip table; 50% HP on capture; raze conditions',
    ],
  },

  // ── World ─────────────────────────────────────────────────────
  {
    slug: 'terrain', icon: '⛰️', label: 'Terrain', section: 'World',
    status: 'built', sourceSheet: '',
    summary: 'Terrain, vegetation, height — movement, chop yields, valid builds',
  },
  {
    slug: 'resources', icon: '💎', label: 'Resources', section: 'World',
    status: 'built', sourceSheet: '',
    summary: 'Map resources — yields, harvests, luxuries, and spawn rules',
  },
  {
    slug: 'map-scripts', icon: '🗺️', label: 'Map Scripts', section: 'World',
    status: 'built', sourceSheet: '',
    summary: 'Map generation scripts and their option chips',
  },

  // ── Mechanics ─────────────────────────────────────────────────
  {
    slug: 'events', icon: '📜', label: 'Story Events', section: 'Events',
    status: 'built', sourceSheet: '',
    summary: 'Every narrative event — browsable by class, trigger, and chain',
  },
  {
    slug: 'events/chains', icon: '⛓', label: 'Event Chains', section: 'Events',
    status: 'built', sourceSheet: '',
    summary: 'Multi-event chains as flow diagrams — branches, merges, follow-ups',
  },
  {
    slug: 'diplomacy', icon: '🕊️', label: 'Diplomacy', section: 'Empire',
    status: 'built', sourceSheet: '',
    summary: 'States, war score, truces, alliances, tribute',
  },
  {
    slug: 'occurrences', icon: '🌋', label: 'Occurrences', section: 'Events',
    status: 'built', sourceSheet: '',
    summary: 'Calamities, world transformations, and era/crisis occurrences',
  },
  {
    slug: 'subjects', icon: '🤝', label: 'Subjects', section: 'Events',
    status: 'built', sourceSheet: '',
    summary: 'Event-system casting roles — 2,062 subject templates and their filters',
  },
  {
    slug: 'concepts', icon: '📖', label: 'Concepts', section: 'Concepts',
    status: 'built', sourceSheet: '',
    summary: 'Game-mechanics glossary — every in-game encyclopedia entry, auto-linked',
  },
  {
    slug: 'difficulty', icon: '🎚️', label: 'Difficulty & Advantages', section: 'Empire',
    status: 'built', sourceSheet: '',
    summary: 'What each difficulty preset changes — prosperity, AI bonuses, tribes',
  },
  {
    slug: 'missions', icon: '🎯', label: 'Missions', section: 'Court & Missions',
    status: 'built', sourceSheet: '',
    summary: 'Character missions — costs, requirements, outcomes',
  },
  {
    slug: 'ruin-events', icon: '🏚️', label: 'Ruin Events', section: 'Events',
    status: 'built', sourceSheet: '',
    summary: 'Ruins-tile events — triggers, odds, options, rewards',
    willContain: [
      'Ruins-tile events with eligibility conditions and weighted odds',
      'Each option’s requirements and outcome rewards',
    ],
  },
  {
    slug: 'expedition-events', icon: '🧭', label: 'Expedition Events', section: 'Events',
    status: 'built', sourceSheet: '',
    summary: 'Explore-distant-lands expedition chains, incl. follow-ups',
    willContain: [
      'Expedition (explore distant lands) chains, incl. follow-ups',
      'Each option’s requirements and outcome rewards',
    ],
  },
  {
    slug: 'rally', icon: '📯', label: 'Rally Troops', section: 'Court & Missions',
    status: 'built', sourceSheet: '📈 Rally  Hold Court  Steal Res',
    summary: 'Leader mission: Training yields, dice outcomes',
  },
  {
    slug: 'hold-court', icon: '⚖️', label: 'Hold Court', section: 'Court & Missions',
    status: 'built', sourceSheet: '📈 Rally  Hold Court  Steal Res',
    summary: 'Judge mission: Civics, courtier chance, event chance',
  },
  {
    slug: 'steal-research', icon: '🕵', label: 'Steal Research', section: 'Court & Missions',
    status: 'built', sourceSheet: '📈 Rally  Hold Court  Steal Res',
    summary: 'Spymaster mission: Science from rival, with exposure risk',
  },
  {
    slug: 'religious-conversion', icon: '🙏', label: 'Religious Conversion', section: 'Religion',
    status: 'built', sourceSheet: '🙏 Religious Conversion Mechani',
    summary: 'How religion spreads between cities',
    willContain: ['Spread formula, modifiers, examples'],
  },

  // ── Character Skills ─────────────────────────────────────────
  {
    slug: 'stat-scaling', icon: '📈', label: 'Stat Scaling', section: 'Ratings',
    status: 'built', sourceSheet: '🟣 Wisdom Base / CM (+ Charisma, Courage, Discipline)',
    summary: 'Per-rating yield/combat scaling by role, Non-competitive vs Competitive',
    willContain: ['All 4 stats, rating −3..+15, Leader/Governor/Agent/General, both modes'],
  },

  // ── Meta ─────────────────────────────────────────────────────
  {
    slug: 'patch-notes', icon: '🛠', label: 'Patch notes', section: 'Meta',
    status: 'built', sourceSheet: '',
    summary: "Mohawk's official build notes per release, plus the XML changes we detected",
  },
];

export const SECTIONS = [
  'Nations & Families',
  'Characters',
  'Court & Missions',
  'Ratings',
  'Cities',
  'Empire',
  'Units',
  'Combat',
  'Religion',
  'Events',
  'World',
  'Concepts',
  'Meta',
] as const;
