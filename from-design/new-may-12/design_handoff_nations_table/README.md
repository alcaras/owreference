# Handoff: Nations Table — Editorial Redesign

## Overview

A design pass on the **Nations** page of [owreference](https://github.com/alcaras/owreference) — the side-by-side comparison table covering bonuses, shrines, unique units, families, starting techs, and royal lineup for all 13 Old World nations.

The original implementation filled every data cell with a saturated yield color, drowning the actual text in chartjunk. This redesign applies two principles in combination:

1. **Tufte data-ink discipline** — color encodes categorical info (which yield, whose nation) at the minimum intensity needed. Type carries the hierarchy.
2. **Editorial / manuscript aesthetic** — borrowed from the sibling [Old World Tech Tree](https://alcaras.github.io/owtt/) project. Warm dark-slate palette in `oklch`, Cormorant Garamond serif for proper names, Inter sans for UI chrome, gold-leaf restraint, eyebrow labels, subtle parchment grid overlay.

The two principles work together: data ink stays minimal (3 px yield bar, 2 px nation rule) while the typography and palette give the table a crafted, of-a-piece feel with the rest of the owtt/owreference family.

## About the Design Files

The files in this bundle are **design references created in HTML** — a React + Babel prototype showing intended look and behavior. They are **not** production code to drop into the repo. The task is to recreate this design in the existing **Astro** codebase at `src/pages/nations.astro`, using the project's established patterns:

- `LinkedText.astro` for term linkification
- `classifyYield` / `yieldColors` from `src/lib/entities.ts`
- `nations.json` as the data source
- Update / extend the existing `theme.css` to add the new design tokens

The prototype includes a "Tweaks" panel exposing four directions; **Tufte** is the default + decision. The other variants (Refined / Columnar / Engraved) were design exploration and are not for production.

## Fidelity

**High-fidelity.** Exact colors (oklch values), type sizes, spacing, and interaction states are specified.

## Visual DNA

### Core moves

| Aspect | Before | After |
|---|---|---|
| Cell yield color | Solid full-bg fill | **3 px left-edge bar**; cell bg transparent |
| Nation column color | Full-color band header | **2 px rule** under the nation name |
| Background | Flat near-black `#0e0f12` | `oklch(0.18 0.012 80)` warm slate + two radial gradients + 60 px parchment grid overlay |
| Title / nation names | Cinzel display caps | **Cormorant Garamond** serif, normal case |
| Section headers | Gold Cinzel with chevron | **Gold-soft uppercase eyebrow** (10px, letter-spacing 0.2em) with `--gold-deep` underline rule |
| Page title | "Nations" only | Eyebrow "ALL 13 · SIDE BY SIDE" above large serif "Nations" |
| Brand mark | Single `⚜` glyph | **36 px shield SVG** in a recessed dark-radial tile with `--gold-deep` border, paired with eyebrow + serif title |
| Linkifier | Underline on every term | Underline on **hover only** (toggleable) |
| Shrine deity art | Removed (was bg imagery) | **16 px game icon** beside the serif type label |

## Design Tokens

### Color (all `oklch`, hue 80 = bone/amber)

```css
--bg:           oklch(0.18 0.012 80);
--bg-elev:      oklch(0.22 0.012 78);
--bg-elev-2:    oklch(0.25 0.013 78);
--border:       oklch(0.32 0.012 80);
--border-strong:oklch(0.40 0.014 80);
--border-faint: oklch(0.28 0.010 80);

--text:         oklch(0.94 0.008 80);
--text-soft:    oklch(0.82 0.010 80);
--text-dim:     oklch(0.62 0.012 80);
--text-faint:   oklch(0.48 0.012 80);

--gold:         oklch(0.82 0.13 82);
--gold-soft:    oklch(0.70 0.10 82);
--gold-deep:    oklch(0.55 0.08 80);
--gold-glow:    oklch(0.82 0.13 82 / 0.18);
```

### Body background

```css
background:
  radial-gradient(1200px 600px at 20% -10%, oklch(0.26 0.02 70 / .55), transparent 60%),
  radial-gradient(900px 500px at 110% 10%, oklch(0.24 0.02 250 / .25), transparent 60%),
  var(--bg);
```

### Parchment grid overlay (on `body::before`)

```css
background-image:
  linear-gradient(to right, oklch(1 0 0 / .013) 1px, transparent 1px),
  linear-gradient(to bottom, oklch(1 0 0 / .013) 1px, transparent 1px);
background-size: 60px 60px;
```

### Type

| Use | Family | Weight | Size | Letter-spacing |
|---|---|---|---|---|
| Page title | Cormorant Garamond | 600 | 2rem | 0.01em |
| Page eyebrow | Inter | 500 | 10px | 0.22em / uppercase |
| Brand title "Reference" | Cormorant Garamond | 600 | 1.35rem | 0.005em |
| Brand eyebrow "OLD WORLD" | Inter | 500 | 9.5px | 0.18em / uppercase |
| Nation name (header) | Cormorant Garamond | 600 | 1rem | 0.01em |
| Row label (Bonus 1, etc.) | Cormorant Garamond | 600 | 0.88rem | 0.01em |
| Section eyebrow (BONUSES) | Inter | 600 | 0.66rem | 0.22em / uppercase |
| Corner cell label | Inter | 500 | 9.5px | 0.18em / uppercase |
| Shrine type (War, Fire) | Cormorant Garamond | 600 | 1rem | 0.005em |
| Deity name (italic) | Cormorant Garamond italic | 400 | 0.74rem | 0.01em |
| Family class | Cormorant Garamond | 600 | 0.96rem | 0.005em |
| Family name (italic) | Cormorant Garamond italic | 400 | 0.74rem | 0.01em |
| Cell body text | Inter | 400 | 0.8rem (`tight`) | — |
| Numbers | tabular-nums everywhere | | | |

Google Fonts import (single line):

```html
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

### Yields (per-cell `--yield-bg`)

Unchanged from existing `theme.css`. **In the Tufte direction these are used only as the 3 px left bar, not as cell fills.**

| Yield | hex |
|---|---|
| science | `#6b5ea6` |
| civics | `#c98b46` |
| training | `#c25555` |
| money | `#d9b13a` |
| food | `#5e8c43` |
| iron | `#8a8a8e` |
| stone | `#b3b3b8` |
| wood | `#8a4a08` |
| culture | `#4e84b8` |
| growth | `#6ba368` |
| orders | `#b8b8c0` |

Consider re-deriving these in `oklch` for consistency with the new palette (optional, lower priority).

### Nations (per-column `--nation-bg`)

Pull from `src/styles/nation-tokens.css` (already in repo, included unchanged).

## Screens / Views

### Single screen: `/nations`

Header → page meta → table → legends → footer.

#### Header

- `<header>` is sticky, top, 50 z-index. Background `linear-gradient(to bottom, oklch(0.16 0.012 80 / .92), oklch(0.16 0.012 80 / .82))` with `backdrop-filter: blur(10px) saturate(140%)` and `1px` `var(--border)` bottom.
- Three-column grid: `auto 1fr auto`, gap `1.5rem`, padding `0.8rem 1.4rem`.
- **Brand**: 36 × 36 px shield-SVG tile (gold icon on a `radial-gradient(circle at 30% 30%, oklch(0.32 0.05 80), oklch(0.20 0.02 80))` with `var(--gold-deep)` border, inset-highlight box-shadow), paired with a stacked label: eyebrow "OLD WORLD" + serif title "Reference".
- **Nav**: tab pills with `inset 0 -2px 0 var(--gold)` underline on the active item.
- **Search**: 280 px min-width, `var(--bg-elev)` background, `var(--border)` border, focus → `var(--gold-deep)` border + `var(--gold-glow)` 2 px ring.

#### Page meta

- Eyebrow "ALL 13 · SIDE BY SIDE" (gold-soft, 10px, letter-spacing 0.22em, uppercase)
- `<h1>` "Nations" — Cormorant Garamond 600, 2rem
- Visibility stat pill on the right: clicking opens a checkbox dropdown to filter columns (Select all / Clear / Done). Tabular-nums in mono for the count.

#### Table

**Sticky elements:**
- Row labels column (sticky left, `min-width: 7rem` at `--micro`, `8.5rem` default)
- Nation header row (sticky top)
- Corner cell stays in top-left

**Corner cell:**
- Two stacked eyebrow lines: "NATION →" (text-dim) and "ATTRIBUTE ↓" (gold-soft), both 9.5 px Inter 500 uppercase letter-spacing 0.18em.

**Column header (`.nhdr`):**
- Background: transparent (lets body gradient show through)
- Crest: 26 × 26 px, drop-shadow `0 1px 1px rgba(0,0,0,0.4)`
- Name: **Cormorant Garamond 600, 1rem**, color `var(--text)`
- **Underline rule**: 2 px tall, `var(--nation-bg)` at opacity 0.9, full width minus 0.5 rem right inset
- Hover: rule grows to 3 px and shifts to `var(--gold)`; name color shifts to `var(--gold)`

**Row labels (`.rowlabel`):**
- Background: transparent
- **Cormorant Garamond 600, 0.88rem**, color `var(--text-soft)`
- Right-aligned, padding `0.4rem 0.8rem 0.4rem 0`
- Right border: 1 px `var(--border)`
- Hover: color → `var(--gold)`

**Section row (`.srow__th`):**
- `colspan` over all columns
- Inter 600, **0.66 rem, letter-spacing 0.22em, uppercase**, color `var(--gold-soft)`
- Padding `1.75rem 0 0.45rem 0`
- Bottom border: 1 px `var(--gold-deep)`
- **No chevron**, no fill

**Data cell (`.cell`):**
- Background: transparent
- Padding: `0.5rem 0.7rem 0.5rem 0.85rem`
- Color: `var(--text)`
- Border-bottom: 1 px `var(--border-faint)` between non-section rows
- **Left bar (`::before`)**: 3 px wide, `var(--yield-bg)`, inset 0.4 rem top/bottom, left at 0.15 rem, border-radius 1 px
- **Right hairline (`::after`, toggleable)**: 2 px wide, `var(--nation-bg)` opacity 0.4
- Empty cell: text `var(--text-faint)`, dash at 0.25 opacity, no bars
- Crosshair hover: bg → `oklch(0.22 0.012 78 / 0.6)`, left bar widens to 4 px

**Shrine cell internals:**
- `.shrine__type`: Cormorant Garamond 600, 1 rem, normal case
- `.shrine__art`: 16 × 16 px PNG from `public/img/icons/shrines/<TYPE>.png` to the left of the type label
- `.shrine__name` (deity, e.g. "Mahrem"): **italic** Cormorant Garamond, 0.74 rem, `var(--text-faint)`
- Effect text below, `Linkified` with quiet underlines (hover-only, gold)

**Family cell internals:**
- `.fam__class`: Cormorant Garamond 600, 0.96 rem, normal case
- `.fam__name`: italic Cormorant Garamond, 0.74 rem, `var(--text-faint)`

## Interactions & Behavior

1. **Nation picker** — clicking the "X of 13 visible" pill opens a dropdown of checkboxes (crest + name), with Select all / Clear / Done. Closes on outside click, Escape, or Done.

2. **Search filter** — typing in the global search hides any nation whose JSON blob doesn't contain the query. AND-combines with the picker.

3. **Crosshair hover** (toggleable, default off) — mousing over a cell highlights its row label and nation header.

4. **Linkifier**:
   - Game terms wrapped in `<a class="lnk lnk--quiet">` (default)
   - No decoration; **underline on hover only**, color `var(--gold)`, offset 2 px
   - Always-on mode (toggle): permanent thin underline at 35% currentColor

5. **Cmd/Ctrl-K** focuses the search input.

## State Management

- `picked: Set<string>` — slugs of currently-visible nations (default: all)
- `search: string` — query string
- `hoverCol`, `hoverRow` for crosshair (transient)

## Spacing scale used

- Cell padding: `0.5rem 0.7rem 0.5rem 0.85rem`
- Section header top gap: `1.75rem`
- Left bar inset top/bottom: `0.4rem`; left inset: `0.15rem`
- Nation header padding: `1rem 0.6rem 0.6rem`
- Header underline inset from right: `0.5rem`

## Densities

The prototype supports three (`comfy` / `tight` / `micro`); ship **`tight`** by default.

## Assets

Copied into `public/img/` (already in the repo, just confirming the set needed):

- `crests/<slug>.png` — 13 nation crests (used at 26 px in header, 18 px in picker)
- `icons/shrines/<type>.png` — 11 shrine deity icons (used at 16 px beside shrine type label)
- `icons/yields/<yield>.png` — yield icons (not used in Tufte cells directly; kept for legend chips)

## Legend

Below the table:

- **Yields chip strip** — one chip per yield. Transparent background, no border; just the colored yield glyph followed by the yield name in `var(--text-soft)`, Inter 500, 0.72 rem, letter-spacing 0.02em.
- **Caption line** — `"Left edge = yield given. Right edge = nation tint."` in `var(--gold-soft)`, 0.62 rem Inter uppercase letter-spacing 0.2em.

## Files in this bundle

- `Nations.html` — entry HTML, loads React + Babel and the three scripts below
- `app.jsx` — React prototype (table, picker, tweaks, all variants)
- `styles.css` — all CSS. Tufte block is under `/* Variant 0 — TUFTE (editorial: warm slate + gold leaf) */`
- `tweaks-panel.jsx` — helper component (not shipped in production)
- `nations.data.js` — flattened nations.json used by the prototype (use the real `src/data/nations.json` in production)
- `src/styles/nation-tokens.css` — per-nation color tokens (already in repo)
- `public/img/crests/`, `public/img/icons/shrines/`, `public/img/icons/yields/` — assets

## Inspiration

The editorial layer is borrowed from [Old World Tech Tree](https://alcaras.github.io/owtt/) (same author) — specifically its dark-slate-and-gold-leaf treatment, Cormorant Garamond serif headings, eyebrow labels, brand-mark tile, and warm radial-gradient backdrop. Implementing this design pulls the Nations table into visual continuity with that sibling project.

## Not in scope

The Refined / Columnar / Engraved variants in `styles.css` are reference only — do not implement.
