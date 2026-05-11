# Handoff: Old World Reference — Nations Table Design Pass

## Overview

This bundle is a design pass on the **Nations table** for [Old World Reference](https://github.com/alcaras/owreference), the dark-mode reference site for the game *Old World*. The flagship Nations page lays out all 13 playable nations as columns and their bonuses/shrines/unique units/techs/families/royal-family as rows, with cells color-coded by **what yield the bonus gives** (not by nation).

The goal of this pass was to **refine — not reinvent** — the existing Astro implementation at `src/pages/nations.astro`: tighten density, settle a clean type/color rhythm, and add a couple of small chrome improvements (footer patch indicator, top search) without breaking the design rules documented in `HANDOFF.md`.

## About the Design Files

The files in this bundle are **design references created in HTML/React** — a clickable prototype showing the intended look and behavior, not production code to copy as-is. The actual site is **Astro + plain CSS**; the prototype uses inline React only so the design could be iterated quickly with state and Tweaks.

The implementation task is to **port the visual decisions back into the Astro codebase** at `src/pages/nations.astro` and `src/styles/theme.css`. Most of the work is CSS — the React shape mirrors the existing `.astro` row spec one-to-one.

## Fidelity

**High-fidelity.** All colors, spacing, type sizes, and hover states are final. The CSS in `styles.css` can be lifted straight into `src/styles/theme.css` with minimal renaming.

## Design Rules (preserved from `HANDOFF.md`)

These were *not* touched in this pass — keep them:

1. **Dark mode only.** Base `#0e0f12`, gold accent `#c9a04a`.
2. **Cells get full background fill.** Match spreadsheet scannability. 25–32% black scrim keeps them readable on dark.
3. **Cells colored by yield given**, not by nation. Nation color is the column-header strip only (left-edge tint is **off** in this pass — see below).
4. **In-game colors only** — nation hex from `color.xml`, yield colors from spreadsheet Intro tab.
5. **Everything links, PKM-style.** Continue wrapping free text in `<LinkedText>`.
6. **Cinzel for headings, Inter for body.** Both Google Fonts.

## What Changed in This Pass

### 1. Density: **micro** is the default

The table runs noticeably tighter than the current production. Three density modes ship as Tweaks (`comfy` / `tight` / `micro`) but **micro is the new default**. Cell padding `0.28rem 0.45rem`, font-size `0.72rem`, line-height `1.25`.

### 2. **No more all-caps**

Drop `text-transform: uppercase` from:
- `.nations-grid th.rowlabel`
- `.nation-header .name`
- Section row headers (`.section-row th`)
- `.shrine-type` (and rebuild — see below)

Nation names render in Cinzel mixed-case (`Aksum`, `Babylonia`) — keeps the dignified feel without shouting.

### 3. **No left-edge nation tint by default**

The current `box-shadow: inset 3px 0 0 var(--nation-bg)` on every cell adds visual noise once you've already got a tinted column header. **Off by default.** Still available as a Tweak.

### 4. **No crosshair hover by default**

Skip the column/row highlight — cells are already tinted enough that scanning works without it. Available as a Tweak.

### 5. **No yield glyph in cell corners**

Yield color *is* the indicator. Adding `◇⚛§♪¤` glyphs in the corner is redundant. Off by default.

### 6. **Shrine cells: type is the headline, deity name is flavor**

Critical readability fix. Old layout:
```
[WAR pill] Mahrem
+2 Training, +10 XP / Unit
```
New layout:
```
War                          ← Cinzel 0.92rem, primary
Mahrem                       ← Inter italic 0.7rem, dim
+2 Training, +10 XP / Unit
```

The shrine **type** (War, Fire, Water, Love, Kingship, Sun, etc.) is the scannable category — that's what a user is hunting for. The deity name is local flavor. Same logic for **families**: class (Champions, Traders, Clerics) is the headline; family name (Agaw, Agazi) is italic flavor below.

### 7. **No more per-column meta line**

Removed the `"X families · X shrines"` strap line under each nation name in the column header. Crest + name is enough.

### 8. **No page-sub description / "How to read this table"**

Removed. The legend chip strip at the bottom does this job better.

### 9. **Patch indicator → footer, not header**

Moved out of the top bar and into a quiet footer row at the bottom of the page:
```
Patch  1.0.79431  ·  released May 02, 2026  ·  data auto-synced from game files       Changelog · Source · Old World
```

Footer is `border-top: 1px solid var(--border)`, `font-size: 0.72rem`, `color: var(--text-dim)`. Tabular-nums for the patch version.

### 10. **Global search in the header**

New search input in the top-right of the site header. ⌘K focuses it. Filters columns live (hides non-matching nations). Matching is fuzzy across the full JSON of each nation, not just the name.

## Layout / Components

### Header (`.hdr`)

Sticky top, `linear-gradient(180deg, #14161b, #0e0f12)`, `backdrop-filter: saturate(140%) blur(8px)`, `border-bottom: 1px solid var(--border)`.

3-column grid: `auto 1fr auto`, gap `1.5rem`, max-width `1700px`, padding `0.7rem 1.1rem`.

- **Brand** (left): `⚜ Old World Reference`. Mark in `--accent` (`#c9a04a`). Title in Cinzel 1.05rem, sub in Inter 0.95rem `--text-dim`.
- **Nav** (center): `Index Nations Yields Techs Units Families Laws Shrines`. Active state: `inset 0 -2px 0 var(--accent)` underline + `--bg-elev` background.
- **Search** (right): `min-width: 280px`, `background: var(--bg-elev)`, `border: 1px solid var(--border)`, radius `8px`. Focus ring `0 0 0 2px color-mix(in srgb, var(--accent) 22%, transparent)`. `⌘K` kbd badge inside on the right.

### Page meta strip

H1 "Nations" in Cinzel 1.7rem with `👑` mark — that's it. No tagline. Right side: three `.stat` pills showing `13 nations`, `total families`, `total shrines`.

### Nations table (`.ntbl`)

`border-collapse: separate`, `border-spacing: 0`, `font-size: 0.82rem` (then density modifiers).

**Row labels** (sticky-left column): `var(--bg-elev)`, Cinzel 600, `font-size: 0.78rem`, `letter-spacing: 0.02em` (no all-caps). Border-right `var(--border)`. Min-width `8.5rem` (`7rem` in micro).

**Section rows** ("Bonuses", "Shrines", "Unique Unit", etc.): `var(--accent)` Cinzel, `font-size: 0.85rem`, `letter-spacing: 0.04em`. Padding-top `1.1rem`. Underline: `1px solid color-mix(in srgb, var(--accent) 35%, var(--border) 65%)`. Small `▸` chevron in front.

**Nation column headers** (sticky-top): `var(--nation-bg)` fill, `linear-gradient(180deg, rgba(255,255,255,0.08), rgba(0,0,0,0.18))` overlay for a subtle dome. Border-bottom `2px solid color-mix(in srgb, var(--nation-bg) 50%, #000 50%)`. Crest 32px in micro, then name in Cinzel 600 0.98rem with `text-shadow: 0 1px 0 rgba(0,0,0,0.18)`.

**Data cells** (`.cell`):
- Background: `var(--yield-bg)` + `linear-gradient(rgba(0,0,0,0.28), rgba(0,0,0,0.28))` scrim. In Refined variant the scrim has subtle vertical falloff: `linear-gradient(180deg, rgba(255,255,255,0.04), rgba(0,0,0,0.20) 60%, rgba(0,0,0,0.32))`.
- Border: `1px solid color-mix(in srgb, var(--yield-bg) 50%, #000 50%)` right + bottom only (no full border — keeps the cell-quilt feel).
- Empty cells: `var(--bg-elev)` background, no scrim, `var(--text-faint)` em-dash.
- Hover: subtle `filter: brightness(1.18) saturate(1.08)` if crosshair is on; otherwise nothing.

**Shrine cell internals** (`.shrine`):
- `display: flex; flex-direction: column;` (was a horizontal pill+name strip).
- `.shrine__type`: Cinzel 600, 0.92rem (0.84rem in micro), `letter-spacing: 0.03em`. No pill background, no border, no padding. Just the type word with a small glyph (`♥ ⚔ ≋ 🜂 ♔ ☀`) prefix.
- `.shrine__name`: Inter italic 0.7rem (0.64rem in micro), opacity 0.72. Sits directly below.
- Effect text wraps via `<LinkedText>` underneath.

**Family cell internals** (`.fam`):
- Class on top: Cinzel 600, 0.9rem (0.82rem in micro), `letter-spacing: 0.02em`. *This is what you scan for.*
- Family name below: Inter italic 0.7rem (0.64rem in micro), opacity 0.72.

### Footer (`.foot`)

`margin-top: 2rem`, `padding-top: 0.9rem`, `border-top: 1px solid var(--border)`, `font-size: 0.72rem`, `color: var(--text-dim)`. Flex space-between. Left side carries patch info; right side carries Changelog · Source · Old World links. `.foot__label` is mono uppercase `0.62rem` `--text-faint`.

## Design Tokens

### Colors

```css
--bg:            #0e0f12;   /* base */
--bg-elev:       #16181d;   /* row-label background, header bg */
--bg-elev-2:     #1d2027;   /* section row bg, hover row-label */
--bg-elev-3:     #23262f;
--border:        #2a2e37;
--border-strong: #3a3f4b;
--text:          #e8e9ec;
--text-dim:      #a8acb6;
--text-faint:    #6c707a;
--accent:        #c9a04a;   /* parchment gold */
--accent-2:      #6ea7d4;   /* link blue */
```

### Yield palette (preserved from current `theme.css`)

```css
.yield-science     { --yield-bg:#6b5ea6; --yield-fg:#fff; }
.yield-civics      { --yield-bg:#c98b46; --yield-fg:#fff; }
.yield-training    { --yield-bg:#c25555; --yield-fg:#fff; }
.yield-money       { --yield-bg:#d9b13a; --yield-fg:#1a1408; }
.yield-food        { --yield-bg:#5e8c43; --yield-fg:#fff; }
.yield-iron        { --yield-bg:#8a8a8e; --yield-fg:#14161b; }
.yield-stone       { --yield-bg:#b3b3b8; --yield-fg:#14161b; }
.yield-wood        { --yield-bg:#8a4a08; --yield-fg:#fff; }
.yield-culture     { --yield-bg:#4e84b8; --yield-fg:#fff; }
.yield-growth      { --yield-bg:#6ba368; --yield-fg:#fff; }
.yield-orders      { --yield-bg:#b8b8c0; --yield-fg:#14161b; }
.yield-discontent  { --yield-bg:#7a6ea3; --yield-fg:#fff; }
.yield-happiness   { --yield-bg:#d9b13a; --yield-fg:#1a1408; }
.yield-influence   { --yield-bg:#c8c9d3; --yield-fg:#14161b; }
.yield-legitimacy  { --yield-bg:#c9a04a; --yield-fg:#1a1408; }
```

### Nation tokens

Untouched. Continue auto-generating `src/styles/nation-tokens.css` from `color.xml` via `scripts/build_data.py`.

### Typography

```css
--font-ui:      "Inter", ui-sans-serif, system-ui, sans-serif;
--font-display: "Cinzel", "Trajan Pro", Georgia, serif;
--font-mono:    "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
```

Add `JetBrains Mono` to the Google Fonts import in `src/layouts/Base.astro` — used for footer label, search kbd badge, corner cell.

### Type scale (micro density — the new default)

```
Page H1            Cinzel  600  1.7rem
Section row        Cinzel  600  0.85rem  letter-spacing 0.04em
Row label          Cinzel  600  0.68rem  letter-spacing 0.02em
Nation header name Cinzel  600  0.82rem  letter-spacing 0.02em
Shrine type        Cinzel  600  0.84rem  letter-spacing 0.03em
Family class       Cinzel  600  0.82rem  letter-spacing 0.02em
Cell body          Inter   400  0.72rem  line-height 1.25
Shrine/family name Inter   400i 0.64rem  opacity 0.72
Footer label       Mono    400  0.62rem  letter-spacing 0.08em uppercase
```

### Spacing / shape

```
--radius:    6px;
--radius-sm: 4px;
--radius-lg: 10px;

Cell padding (micro):     0.28rem 0.45rem
Row label padding (micro):0.3rem  0.55rem
Nation header padding:    0.4rem  0.4rem
```

## Interactions & Behavior

- **Search bar** (top right): typing filters columns live. `⌘K` (or `Ctrl+K`) focuses it. When some columns are hidden, show a small `"Showing X of Y nations matching '...'"` note under the table.
- **Hover**: cells brighten subtly only if crosshair Tweak is on (off by default).
- **Sticky scroll**: row-label column stays pinned-left; nation-header row stays pinned-top; both via `position: sticky`. Corner cell (`Nation → / Attribute ↓`) sits at `top:0; left:0; z-index:5`.
- **Linkified text**: every nation name, yield, resource, family class, and known game term inside cell text is wrapped in an `<a>` linking to the entity page. Underline only on hover (using `text-decoration-color: color-mix(in srgb, currentColor 35%, transparent)` so links read as same-color text until hovered).
- **Empty cells**: render an em-dash, faint.

## State Management

Trivially small. The only client state is the search query string. Everything else is static data from `src/data/nations.json` rendered server-side by Astro.

For the Astro port:
- `nations.astro` already builds the row spec server-side. Add a small client island (e.g. a `<NationsSearch client:load>` React or Solid component) that only owns the input + a `display: none` toggle on `<col>` elements by index. Don't pull the whole table into the island.

## Files in this Bundle

| File | Purpose |
|---|---|
| `Nations.html` | Entry point — loads React, the data, and the app |
| `app.jsx` | React app: header, table, footer, tweaks panel. Mirrors the row spec from `src/pages/nations.astro` |
| `styles.css` | Full stylesheet — this is the file to port back |
| `nations.data.js` | Slimmed snapshot of `src/data/nations.json` for the prototype |
| `tweaks-panel.jsx` | Floating Tweaks panel (only used during design iteration; **drop on port**) |
| `src/styles/nation-tokens.css` | Generated nation color tokens — copy unchanged |
| `public/img/crests/*.png` | 13 nation crest PNGs |

## Porting Steps (Suggested)

1. **`src/layouts/Base.astro`** — add `JetBrains Mono` to the Google Fonts import. Add the new `.foot` and `.hdr__search` markup; remove the existing patch-tag if any.
2. **`src/styles/theme.css`** — replace the existing `.nations-grid`, row-label, section-row, nation-header, and `.cell` blocks with the new ones from `styles.css`. The yield-token block at the bottom is unchanged.
3. **`src/pages/nations.astro`** — update the JSX:
   - Strip the `.meta-row` patch tag, the page-sub paragraph, and the `.nhdr__meta` line under each crest.
   - Rebuild `.shrine` to render type-then-name vertically (not pill + name horizontally).
   - Rebuild family cells the same way (class big, name italic below).
4. **Search island** — add a small client component (10-20 lines) that owns the search input and toggles `<col>` visibility by index.
5. **Footer** — new `<footer class="foot">` block rendered inside `Base.astro` slot.
6. **Drop**: `tweaks-panel.jsx` and all `app--*` / `grid--*` variant classes. Production only ships the `refined` variant in `micro` density with all reading-aid Tweaks off.

## Tweaks (Design Iteration Only — Not for Production)

The prototype exposes a Tweaks panel with three direction variants (Refined / Columnar / Engraved), three densities (Comfy / Tight / Micro), and three reading-aid toggles (crosshair hover, left-edge nation tint, corner yield glyph). **Only Refined + Micro + all reading aids OFF is the chosen production setting.** The other variants and toggles exist in the CSS for future experimentation but should not ship as user-facing controls.

## Assets

All 13 nation crest PNGs come straight from the existing `public/img/crests/` folder — already extracted by the project's `make art` pipeline from Unity bundles. No new asset work required.

## What's Not Covered

This pass focused on the **Nations table only**. The same design system (type scale, color tokens, footer, header search) should propagate to:
- `src/pages/index.astro` — tab grid
- `src/pages/yields/[slug].astro` — yield detail + backlinks
- `src/pages/[slug].astro` — generic placeholder

A second pass can address those. The Nations work establishes the vocabulary.
