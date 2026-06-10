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
make data       scripts/build_*.py (40+, see Makefile data: target) → src/data/*.json
                scripts/build_entities.py → registry of entities + alias index → src/data/entities.json
                scripts/build_backlinks.py→ src/data/backlinks.json
make audit      scripts/audit_coverage.py → HARD GATE: any XML effect field the game
                                            renders but we drop fails the pipeline
                scripts/verify_source_constants.py → warns when watched game-source
                                            functions changed (hand-curated constants)
make changelog  scripts/changelog.py      → diffs EVERY src/data/*.json vs snapshot → CHANGELOG.md
make build      npx astro build           → dist/
make check      scripts/check_links.py    → no broken internal links / unresolved <Term>s
```

Per-patch flow: `make patch` (= sync art data audit changelog build check) → review CHANGELOG → `git push` → GH Actions deploys. New `build_*.py` outputs join the changelog automatically; new XML fields trip the audit until handled.

---

## File layout

```
reference/XML/Infos/*.xml            # synced from Steam install, DO NOT hand-edit
scripts/
  humanize.py                        # XML effect tree → human strings (curated phrasing)
  effects.py                         # registry-driven completeness backstop (see below)
  data/helptext_registry.json        # extracted from game source HelpText.*.cs:
                                     #   every field the game renders + its TEXT template
  audit_coverage.py                  # patch tripwire: populated vs renderable vs handled
  verify_source_constants.py         # hashes watched game-source functions (drift alarm)
  check_links.py                     # post-build link + unresolved-<Term> check
  build_data.py                      # XML+humanizer → src/data/nations.json
  build_*.py                         # one per dataset/tab (40+, registered in Makefile)
  build_entities.py                  # entity registry + alias index
  build_backlinks.py                 # backlinks PKM-graph
  extract_art.py                     # UnityPy Sprite extraction
  sync_patch.sh                      # rsync from Steam install
  changelog.py                       # diffs ALL generated JSON vs last snapshot
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

## Effect rendering: curated phrasing + registry backstop

Two layers, one output:

1. **humanize.py** renders the fields it covers with curated, spreadsheet-validated
   phrasing. Its coverage is declared in `humanize.HANDLED_FIELDS` (per section:
   effectCity / effectPlayer / effectUnit / bonus).
2. **effects.py** renders *every other populated field* generically, grounded in
   `scripts/data/helptext_registry.json` — a machine extraction of the game's own
   HelpText builders (which field → which TEXT template, arg semantics, ÷10 scaling).
   humanize's renderers call `effects.extra_lines(entry, section, exclude=HANDLED, …)`
   at the end, so a brand-new patch field renders (honest generic phrasing) instead
   of silently vanishing.

`audit_coverage.py` ties it together: populated ∧ game-renderable ∧ ¬(curated ∪
backstop ∪ conscious-skip) ⇒ pipeline failure. To improve phrasing for a field,
move it from backstop to curated: render it in humanize.py AND add it to
`HANDLED_FIELDS` there. To consciously hide a field, add it to `effects.SKIP_FIELDS`
with a reason comment. Never delete registry entries to silence the audit; re-extract
the registry instead when Mohawk ships new HelpText code (the extraction recipe is in
the git history of `scripts/data/helptext_registry.json`).

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
- **Value scaling is per-field, never blanket ÷10.** Rates (`aiYieldRate` etc.) are 10× display, but: `aiYieldStockpile` grants are ×10 in code so XML = display (`Player.cs:15843`); `aiYieldHarvest`/`aiYieldReveal` display raw; goal/subject yield thresholds are display units (`PlayerGoal.cs` divides before comparing); vegetation chop yields raw. The helptext registry records `valueScale` per field — trust it.
- **`MOVEMENT_MULTIPLER` = 9** (typo is the game's): 9 = 1 MP. Occurrence terrain-change chances are per-10,000.
- **`difficulty.xml` is the Prosperity dial, not difficulty levels** — the picker presets ("The Able"…) live in `difficultyMode.xml`. AI always plays at Prosperity "Thriving" (`globalsType.xml AI_DIFFICULTY`).
- **`development.xml` is the advanced-start setup option** (AI starting cities/techs/no-wonder turns), not city development.
- **`subject.xml` is the event-system casting layer** (role templates events bind), not vassals. No SaP "Sons of Adad" — `-sap` = The Sacred and the Profane.
- **`diplomacy.xml` holds only the 4 states**; diplomatic *actions* are missions in `mission.xml`; war-score deltas are source-only (`City.cs`/`Unit.cs`).
- **Council seat rating yields scale triangularly** — base × R(R+1)/2 (`InfoHelpers.getRatingYieldRateCouncil → triangleOffset`), not linearly. Grand Vizier's seat lives in `council-btt.xml`.
- **Bonus-card tech zTypes lie about prereqs** (`TECH_FORESTRY_BONUS_SCIENTIST` requires Metaphysics) — always read `abTechPrereq`, never parse the zType.
- **`resource.xml` has no category field** — luxury = union of `effectCity aeLuxuryResources`; strategic = unit `EffectCityPrereq` chains. Worked-resource yields live on `improvementClass.xml`, not `improvement.xml`. `zIconName` redirects shared art (Marble→stone.png, Ore→iron.png).
- **Terrains have no base yields in XML** — tile yields come from improvements/resources; `aiDefendEffectUnit` is an *attack penalty into* the tile; `TerrainValid` targets are OR'd; `iRemoveCost` is Orders, not worker-turns.
- **Culture gates**: `RequiresCulture` = exactly that level; `MinimumCulture` = at least. Past Legendary, each culture step costs 5,000×(step+1) and is +1 VP.
- **Ambition "tier" = which ambition slot (1st–10th)** it can be offered as; goals have no per-goal reward fields (Legitimacy/VP flow indirectly).
- **DLC event text lives in oddly named files**: Wonders & Dynasties → `text-wonders-dynasties-events.xml`, Wrath of Gods → `text-calamities-events.xml` (there is no `text-eventStory-wd/-wog.xml`). ~16 eventStory entries legitimately have no `Name` (hidden setup events); ~372 have no class/trigger (engine-invoked).
- **Occurrences aren't all WoG** — badge by `GameContentRequired`, not by file. `occurrenceEffect.xml` is cosmetic only.
- **Mods folder (`reference/XML/Mods/`) is excluded from the repo** to keep size down. The pipeline only reads from `reference/XML/Infos/`.
- **`reference/Graphics/` and `reference/Source/`** are excluded too (binary game assets, Unity controllers).
- **Cognomen tracker OCR — the OCR is reliable; don't blame Tesseract.** On a real F5 capture Tesseract.js read **every digit correctly** (17/17 scoring stats, zero number errors). What looks "garbled" is *gutter noise*, not bad text: bullet glyphs (●) become `e`/`eo`/`®`/`¢`, the left UI rail bleeds in as `J{`/`U`/`|` prefixes, and right-edge game-world text appends junk like `54 C`, `5 in`, `1 Is`. The fix was always in the **parser**, never the image. Don't add OpenCV.js / heavier preprocessing on a hunch — diagnose against a real screenshot first.
- **F5 panel ≠ all cognomen stats.** The panel lists ~50 lifetime stats but only **47 feed cognomen scoring** (`calculator.inputStats`). `Worker Turns`, `Children Had`, `Trees Removed` etc. are real panel rows that score nothing — the parser's `ignored` bucket counting them is **correct behaviour, not a miss**. Verify against `inputStats` before "fixing" an ignored stat.

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

## Cognomen tracker — screenshot OCR import

`src/pages/cognomens-tracker.astro` lets users fill the tracker from the in-game
**F5 leader panel** two ways, both converging on **one parser** (`parseAndFill`):

1. **Paste/type the Stat(s) text** — original flow.
2. **Paste / drag-drop / pick a screenshot** — OCR'd client-side, fed into the
   same `parseAndFill`. A single `document` `paste` listener auto-detects:
   `clipboardData.items` with an `image/*` file → OCR; otherwise text flow.

Pipeline (all in the page's `is:inline` script — no build step, no server):

- **Tesseract.js** is **lazy-loaded from jsDelivr CDN** (`@5.1.1`) only the first
  time an image is supplied (`loadTesseract()`), so the page stays light and the
  static/offline build is uncompromised. Offline → it tells the user to paste text.
- **`preprocess(img)`**: canvas upscale (~1600px max), grayscale, **Otsu**
  threshold with **auto-polarity** (majority class = background → forced white),
  returns a data URL. This is enough; resist adding more.
- **`parseAndFill(raw)`** is OCR-tolerant by design:
  - **Value** = first integer *after* the first `:`/`=` (`rest.match(/(\d[\d,]*)/)`),
    so trailing edge-bleed (`54 C`, `5 in`) is ignored.
  - **Label** = text before that colon, `normLabel`'d, then matched against
    `calculator.statAliases` by exact key **or suffix** (`norm.endsWith(' '+key)`,
    longest wins), so bullet/UI-rail gutter junk (`J{ e Worker Turns`) is stripped.
  - The `Cognomen:` line is skipped from stat-fill and used as a cross-check
    (`expected` → compared to the computed `best.title`).
- `statAliases` comes from `scripts/build_cognomens.py` (`_norm_label` — keep the
  JS `normLabel` in sync with it). 99 alias keys → 47 scoring stat tokens.

When changing the parser, **test against a real OCR dump**, not synthetic text —
the gutter-noise shapes (`eo`, `|J{ e`, `Jie`, trailing ` of`/` Is`) are the
whole point. A node one-liner loading `calculator.statAliases` + the real paste
is the fastest regression check (see git history of commit `5c37ecd`).

---

## Common pitfalls

- **Don't import `Bonus 1/2/3`-style rows for new pages without reason.** The spreadsheet's row structure was a workaround for fixed-column tables. With Astro we can render lists naturally.
- **Don't hardcode lists of nations or family classes** — they come from XML. The DLC may add more (e.g., Maurya, Tamil, Yuezhi are DLC).
- **Don't add yield aliases for mechanic words** ("Pillage", "Ranged", "Mercs") — those are unit/combat mechanics, not yields. They were tried and produced wrong colors. See `YIELD_ALIASES` in `build_entities.py`.
- **Don't override the cell color via row defaults** unless the row is truly about that yield (e.g., a "Cost" row in iron). Honest "misc" slate is better than wrong color.
- **Don't write new CSS classes when existing ones work.** Reuse `.cell`, `.rowlabel`, `.nhdr`, `.shrine__*`, `.fam__*`, `.effect`, `.chip` first.

---

## Open work (as of 2026-06-09)

- **Field-coverage is audited, not aspirational** — `make audit` fails on any populated
  field the game renders that neither humanize.py nor effects.py covers. To raise
  phrasing quality, promote fields from the generic backstop into curated humanize.py
  rendering (see "Effect rendering" section).
- **Backstop phrasing polish** — generic lines like "+10% Vegetation From Modifier / Trees"
  are honest but clunky; promote the common ones to curated phrasing as they're noticed.
- **Header nav (`nav.ts`) is still the narrow curated set** — the home page now lists
  every built tab by section; decide which of the new pages earn header slots.
- **Registry re-extraction** — when a patch changes `reference/Source` HelpText code,
  re-extract `scripts/data/helptext_registry.json` (recipe in its git history).

If you're an agent building a new tab, this doc plus `src/pages/nations.astro` and
`scripts/build_data.py` are your reference.
