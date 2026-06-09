// The curated, hand-maintained navigation set: pages that have been
// polished to the Nations standard and are "ready". This is the single
// source of truth for BOTH the header nav (Base.astro) and the home-page
// catalog (index.astro) — the home page must not link tabs that aren't
// in here, even if tabs.ts marks them 'built'.
//
// Scope is intentionally narrow. Add an entry only once its page is
// polished and surfaced on purpose.
export interface NavItem {
  href: string;   // slug, also the tabs.ts slug for metadata lookup
  label: string;  // display name
}

export const NAV: NavItem[] = [
  { href: 'nations', label: 'Nations' },
  { href: 'tribes', label: 'Tribes' },
  { href: 'families', label: 'Families' },
  { href: 'archetypes', label: 'Archetypes' },
  { href: 'missions', label: 'Missions' },
  { href: 'map-scripts', label: 'Map Scripts' },
  { href: 'urban-improvements', label: 'Urban Improvements' },
  { href: 'rural-improvements', label: 'Rural Improvements' },
  { href: 'wonders', label: 'Wonders' },
  { href: 'urban-specialists', label: 'Urban Specialists' },
  { href: 'rural-specialists', label: 'Rural Specialists' },
  { href: 'units', label: 'Units' },
  { href: 'unique-units', label: 'Unique Units' },
  { href: 'city-capture-mechanics', label: 'City Capture Mechanics' },
  { href: 'stat-scaling', label: 'Stat Scaling' },
  { href: 'rally', label: 'Rally Troops' },
  { href: 'hold-court', label: 'Hold Court' },
  { href: 'steal-research', label: 'Steal Research' },
  { href: 'ruin-events', label: 'Ruin Events' },
  { href: 'expedition-events', label: 'Expedition Events' },
  { href: 'cognomens', label: 'Cognomens' },
  { href: 'cognomens-tracker', label: 'Cognomens Tracker' },
];
