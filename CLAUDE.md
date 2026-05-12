# CLAUDE.md — agent guide for owreference

Successor to the [Old World Reference Spreadsheet](Old%20World%20Reference%20Spreadsheet.xlsx) (alcaras's). Astro static site, dark-mode, replicating the 40 sheet tabs as XML-canonical pages that auto-update each patch.

**Live:** https://alcaras.github.io/owreference/ · **Source:** https://github.com/alcaras/owreference

---

## The core idea

The game ships its own data as XML at `~/Library/Application Support/Steam/steamapps/common/Old World/Reference/XML/Infos/`. We **sync from there each patch**, parse, and render. The site is a deterministic projection of the game's own files.

Every fact in the site should be **derivable from XML**. The legacy spreadsheet is a starting point for layout intent, not a data source. We do keep a small `src/data/annotations/*.yaml` layer for content the XML doesn't express cleanly (or until the humanizer covers it), but **prefer XML when both are available**.

---

## Pipeline

`make patch` runs the whole pipeline:

```
make sync       scripts/sync_patch.sh     → rsync Steam's Reference/ → ./reference/
make art        scripts/extract_art.py    → pinacotheca-style sprite pull → public/img/{crests,yields,resources,techs,specialists,families,tribes,archetypes}/
make data       scripts/build_data.py     → reads XML+humanizer → src/data/nations.json + src/styles/nation-tokens.css
                scripts/build_entities.py → registry of 367+ entities + alias index → src/data/entities.json
                scripts/build_backlinks.py→ src/data/backlinks.json
make changelog  scripts/changelog.py      → diff snapshots → CHANGELOG.md
make build      npx astro build           → dist/
```

Per-patch flow: `make patch` → review CHANGELOG → `git push` → GH Actions deploys.

---

## File layout

```
reference/XML/Infos/*.xml            # synced from Steam install, DO NOT hand-edit
scripts/
  humanize.py                        # XML effect tree → human strings
  build_data.py                      # XML+humanizer → src/data/nations.json
  build_entities.py                  # entity registry + alias index
  build_backlinks.py                 # backlinks PKM-graph
  extract_art.py                     # UnityPy Sprite extraction
  sync_patch.sh                      # rsync from Steam install
  changelog.py
src/
  data/
    nations.json, entities.json, backlinks.json   # generated
    annotations/nations.yaml                       # legacy curation (declining over time)
    tabs.ts                                        # catalog of all 30 tabs
  pages/
    nations.astro                    # flagship — the design reference
    index.astro                      # tab index
    [slug].astro                     # generic placeholder for unbuilt tabs
    yields/[slug].astro              # yield/concept detail page with backlinks
  components/
    Term.astro                       # linked entity reference (icon + name)
    LinkedText.astro                 # auto-link known aliases in free text
  layouts/Base.astro                 # site shell (hdr, foot, page-meta)
  lib/entities.ts                    # runtime helpers around entities.json
  styles/
    theme.css                        # tokens + table styles
    nation-tokens.css                # generated: per-nation CSS vars
public/img/                          # extracted game art, committed for GH Pages
data/
  patch.json                         # current build tag + sync timestamp
  snapshots/{version}/               # JSON snapshots for changelog diffing
from-design/                         # design-pass references (do not import)
```

---

## Design rules (LOAD-BEARING — don't drift)

These came from the user, the design pass, and iteration. Don't relitigate:

1. **Dark mode only.** Base `#0e0f12`, gold accent `#c9a04a`, parchment-tone UI. No light mode.
2. **In-game colors only.** Pull hex from `color.xml`. Don't invent palette colors.
3. **Cells colored by what they GIVE (yield).** Bonus/shrine cells get `.yield-{key}` classes via `classifyYield(text)`. The nation color shows only in the column header strip, not as cell bg.
4. **Cell layout:** full background fill, 25% black scrim for readability. Refined+micro density variant (only — drop Comfy/Tight from the design prototype).
5. **No all-caps anywhere** except mono labels in the footer. Cinzel mixed-case for headings.
6. **Everything is a link, PKM-style.** Wrap free text in `<LinkedText text={...} />`. Anchors like `Egypt`, `Wood`, `Orders` should resolve to their entity pages.
7. **Backlinks shown on every entity page** via `src/data/backlinks.json`.
8. **Shrine cells:** type-as-headline (Cinzel, with type glyph prefix) + deity name italic below + effect text.
9. **Family cells:** in-game per-family hex from `color.xml` as bg + family-class icon inline + class name (headline) + family name (italic below).
10. **Yield tokens (`theme.css`):** match the legacy spreadsheet Intro tab legend (Science purple, Civics peach, Training pink, etc.), adapted for dark mode.
11. **Nation picker popover** on the page meta lets users hide/show specific nation columns; composes with the header search.
12. **Fonts:** Cinzel for display, Inter for body, JetBrains Mono for footer labels / kbd badges.

---

## How to build a new tab page

Pattern, in order:

### 1. Identify the data source

Look at the spreadsheet tab to understand intent (column layout, row structure, what's color-coded). Then map each piece to its XML source:

| Spreadsheet says | XML source |
|---|---|
| Nation list, names, colors | `nation.xml`, `color.xml` |
| Family list, classes, in-game hex | `family.xml` (use `abNation` over `TeamColor` — YEUZHI typo!), `familyClass.xml`, `color.xml` |
| Shrine names, types, effects | `improvement.xml` (Class=IMPROVEMENTCLASS_SHRINE) |
| Tech tree | `tech.xml` (+ `text-tech.xml`) |
| Wonders, Laws, Buildings, Promotions | their respective `*.xml` |
| Bonuses (any entity's "what does it do") | walk `effectPlayer`/`effectCity`/`effectUnit`/`bonus` via `humanize.py` |
| Character ratings, archetypes | `archetype.xml`, `trait.xml` |
| Resource icons | `public/img/icons/resources/{slug}.png` (already extracted) |

The pre-extracted entities live in `src/data/entities.json` (367 of them, with aliases). Use `getEntity()` and `linkify()` from `src/lib/entities.ts`.

### 2. Build the data layer

Add a `scripts/build_<thing>.py` that:
- Reads from `reference/XML/Infos/`
- Uses `from humanize import load_xml_indexes, render_nation_effects, render_effect_city, render_bonus, ...`
- Emits `src/data/<thing>.json` with **deterministic key ordering** (`json.dumps(..., sort_keys=True)`)
- Updates `Makefile`'s `data:` target

Wire it into the index of generated data so `make data` runs it.

### 3. Render the page

`src/pages/<slug>.astro` — base off `src/pages/nations.astro`. Key beats:

- Use `<Base title="..." active="<slug>" pageMark="<emoji>" pageStats={[...]}>` from `src/layouts/Base.astro`
- For tabular data: `<table class="ntbl">` with sticky `.rowlabel` left column and sticky `.nhdr` top row. Use existing CSS classes — don't invent new ones unless the layout truly differs.
- Cells should classify yield via `classifyYield(text)` and apply `.yield-{key}` for color.
- Wrap free text in `<LinkedText text={...} />` for auto-linking.
- For entity references where you have the ID, use `<Term id="UNIT_HOPLITE" />` to get icon+name+link.
- Empty cells: `<td class="cell ... is-empty"><span class="cell__dash">—</span></td>`.

### 4. Promote in the catalog

In `src/data/tabs.ts`, change the tab's `status` from `'placeholder'` to `'built'`. The index will pick it up automatically.

### 5. Verify

```sh
make data && npx astro build
# Page should appear at /<slug>
```

---

## Humanizer reference

`scripts/humanize.py` turns the structured effect XML into one-line strings. Key entry points:

- `load_xml_indexes(xml_dir)` → preload everything; pass to renderers as `indexes`
- `render_nation_effects(effect_player_id, indexes)` → list[str] of all effects
- `render_effect_city(entry, per_city=True, indexes=indexes)` → list[str]
- `render_effect_player_scalars(entry)` → list[str] for bool/int/pct scalar fields
- `render_effect_unit(entry)` → list[str] for pillage/kill/fatigue
- `render_bonus(entry, indexes)` → list[str] for stockpile, free units, free projects
- `render_shrine_effects(improvement_entry)` → list[str] for shrine yield output + tile modifiers

Common XML fields the humanizer handles:
- `aiYieldRate` (per-turn yields) — divide value by 10 for display
- `aiYieldModifier` (percentage modifier)
- `aaiEffectCityYieldRate` (conditional per-effect yield)
- `aaiTileYieldRate*` / `aaiTileYieldModifier` (tile bonuses)
- `aiImprovementClassModifier` (e.g., +50% Shrines)
- `aaiImprovementClassYield` (e.g., +0.5 Orders/Pastures)
- `aiImprovementRiverModifier` (e.g., +40% Farm on River)
- `aiUnitCostModifier` / `aiUnitTraitCostModifier` (e.g., -25% Settler Cost)
- `aiMissionYieldCostModifier` (e.g., -50% Civics Mission)
- `aiMilitaryKillYield` (e.g., +2 Orders/Kill)
- `aeFreeEffectUnit` (e.g., Focus 1)
- `aeEffectCityEffectCity` (resource-triggered, e.g., Elephants give Ivory)
- Nested `<EffectPlayer>` pointing to a TEXT_PROJECT_* → "Unlocks X"

Add new fields to the humanizer as you encounter them. Always test against the spreadsheet to validate.

`{lowercase:link(TOKEN,N)}` markup in game-text strings is stripped to "Token Words" — see `_strip_link_templates`.

---

## Source-of-truth rules

1. **XML wins on facts.** If the XML says "+10 SCIENCE/City" and the yaml says "+1 Sci/City", the XML is what we render. The yaml is provisional.
2. **Yaml annotations are a fallback / curation layer** for things the humanizer doesn't cover. Migrate them into XML-driven rendering when possible.
3. **The xlsx is read-only history.** It seeded the yaml on day one. We don't consult it after that.
4. **Game-data quirks** (typos like `YEUZHI`, separate `family.xml` entries with mismatched references) should be papered over in our build scripts with a code comment explaining why. Don't fix the upstream — that's the user's Steam install.

---

## Quirks already discovered (don't re-debug)

- **Yuezhi families:** `family.xml` uses `TEAMCOLOR_NATION_YEUZHI` (typo — E before U) while the nation is `NATION_YUEZHI`. Always read `abNation` first, fall back to `TeamColor`. Also alias the `NATION_YEUZHI` color entries to `NATION_YUEZHI` in `build_data.py`.
- **Shrine type = signature yield:** WAR→training, KINGSHIP→civics, WISDOM→science, SUN→orders, WATER→money, LOVE→growth, UNDERWORLD/HEARTH→culture, FIRE→iron, HEALING→growth, HUNTING→food. See `SHRINE_TYPE_YIELD` in `nations.astro`.
- **Family class icons** live at `public/img/archetypes/<class>.png` (lowercase, no `_seat`). The `-seat` variants are the family-seat-flair icons; don't use for class label.
- **Game yield values are 10× display:** `YIELD_SCIENCE +10` means "+1 Science" in user-facing text. Divide by 10.
- **The "Bonuses" cell layout** is a single row, vertical stack of `.effect` mini-tiles (one per humanized effect) — not 3 separate rows. Some nations have 1 effect, some have 4.
- **Effect text falls back to yaml** when `effectsXml` is empty (only Aksum/Tamil currently — and they have partial XML coverage now too).
- **Cells that don't classify to a yield** get `.yield-misc` (slate). Don't hand-assign row defaults — let `classifyYield(text)` decide, and use `skipClassify: true` on rows where the text describes non-yield content (UU names/traits, royal family members).
- **Mods folder (`reference/XML/Mods/`) is excluded from the repo** to keep size down. The pipeline only reads from `reference/XML/Infos/`.
- **`reference/Graphics/` and `reference/Source/`** are excluded too (binary game assets, Unity controllers).

---

## Available components

- `<Base title active pageMark pageStats>` — site shell with header (nav + search), page-meta (title + stats pills), footer (patch info + repo links). Footer reads `data/patch.json`.
- `<Term id|entity label showIcon iconOnly>` — render a single linked entity reference. Icon comes from `entity.icon`; URL from `entity.page`.
- `<LinkedText text showIcons>` — scan free text for known aliases and wrap each in `<Term>`. Use this for any free-text cell content.

---

## Available helpers (TypeScript)

From `src/lib/entities.ts`:
- `entities` — list of all entities
- `getEntity(id)` — lookup by id
- `getEntityBySlug(type, slug)` — lookup by (type, slug)
- `linkify(text)` — returns `LinkedSegment[]` for rendering
- `classifyYield(text)` — returns the first yield key found (lowercased), or null
- `yieldColors` — `{YIELD_KEY: hex}` from the registry

---

## Common pitfalls

- **Don't import `Bonus 1/2/3`-style rows for new pages without reason.** The spreadsheet's row structure was a workaround for fixed-column tables. With Astro we can render lists naturally.
- **Don't hardcode lists of nations or family classes** — they come from XML. The DLC may add more (e.g., Maurya, Tamil, Yuezhi are DLC).
- **Don't add yield aliases for mechanic words** ("Pillage", "Ranged", "Mercs") — those are unit/combat mechanics, not yields. They were tried and produced wrong colors. See `YIELD_ALIASES` in `build_entities.py`.
- **Don't override the cell color via row defaults** unless the row is truly about that yield (e.g., a "Cost" row in iron). Honest "misc" slate is better than wrong color.
- **Don't write new CSS classes when existing ones work.** Reuse `.cell`, `.rowlabel`, `.nhdr`, `.shrine__*`, `.fam__*`, `.effect`, `.chip` first.

---

## Open work (as of 2026-05-11)

- **Humanizer extensions** — fields not yet handled: `aiYieldRateGlobal`, `aiYieldBonus`, `aiBuildModifier`, `iUnitBuildModifier`, `iWalls`, `iRiver`, etc. Add as you need them; always test against the spreadsheet.
- **Aksum / Tamil** — XML coverage is partial (Aksum missing Stele, Tamil missing more Bonuses). Falls back to yaml for now.
- **Remaining tabs** — see `src/data/tabs.ts`. Status `'placeholder'` means the route serves a stub; `'built'` means full content.

If you're an agent building one of those tabs, this doc plus `src/pages/nations.astro` and `scripts/build_data.py` are your reference.
