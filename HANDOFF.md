# Handoff to Claude Design

This is a reference site for [Old World](https://mohawkgames.com/oldworld/), replacing the legacy spreadsheet at `./Old World Reference Spreadsheet.xlsx`. The scaffolding is done — Astro pages, data pipeline, art extraction, entity registry, backlinks. **Your job is visual polish, not architecture.**

## What to upload to Claude Design

Upload the **entire repo**. Specifically, the design pass should focus on these files:

| Priority | Path | Why |
|---|---|---|
| ⭐⭐⭐ | `src/pages/nations.astro` | Flagship page. Embodies all design rules — full-bg cells, yield-coloring, linkified terms, shrine cards, sticky col/row. |
| ⭐⭐⭐ | `src/styles/theme.css` | Global tokens — dark palette, yield colors, table styles. Edit fearlessly. |
| ⭐⭐⭐ | `src/layouts/Base.astro` | Site shell — header, fonts, nav. |
| ⭐⭐ | `src/components/Term.astro` | Linked entity reference (icon + name). |
| ⭐⭐ | `src/components/LinkedText.astro` | Auto-linker for free text. |
| ⭐⭐ | `src/pages/index.astro` | Tab index — section grouping, status badges. |
| ⭐⭐ | `src/pages/yields/[slug].astro` | Backlinks page template. |
| ⭐ | `src/pages/[slug].astro` | Generic placeholder. |
| ⭐ | `src/styles/nation-tokens.css` | **Generated** — don't hand-edit. Re-run `make data` if you change nation colors in XML. |

**Don't touch:**
- `scripts/*` — the data pipeline
- `reference/` — synced from Steam install
- `src/data/*.json` — generated artifacts
- `public/img/` — extracted game art

## Design rules (load-bearing decisions)

These are user-confirmed, not provisional:

1. **Dark mode only.** No light mode requested. Base `#0e0f12`, gold accent `#c9a04a`.
2. **Cells get full background fill, not just accents.** Match the spreadsheet's bright-tile scannability. The 25% black scrim keeps them readable on dark.
3. **Cells colored by what they GIVE (yield), not by nation.** Use `.yield-{key}` classes. Nation color is reserved for the column header strip + a subtle left-edge tint on cells.
4. **In-game colors only** — nation hex from `color.xml`, yield colors from the spreadsheet Intro tab. Don't pick from generic dark-theme templates.
5. **Yield palette mirrors the legacy spreadsheet Intro tab** (pastels, adapted for dark mode). See `theme.css` `.yield-*` classes.
6. **Everything is a link, PKM-style.** "Egypt", "Wood", "Orders" all link to their detail page. Wrap free text in `<LinkedText text={...}>`.
7. **Backlinks shown on every entity page.** "Referenced by:" section — already wired for yields.
8. **Shrine cells show type tag + deity name + effect.** Auto-derived from XML.
9. **Display font is Cinzel** (Trajan-adjacent) for headings; **Inter** for body. Both via Google Fonts.

## What's already working

- 13 nations with crests, families, techs, dynasties, leaders, unique units, shrines
- 30 tab placeholders grouped into 7 sections on the index
- 19 yield detail pages with backlinks (1 per yield/concept)
- Auto-link any of 367 known terms (nations, yields, techs, units, families, laws, resources)
- 198 extracted game-art assets (crests, yield icons, resource icons, tech icons, specialists)
- Per-patch auto-update pipeline (`make patch`)
- GH Actions deploy to GitHub Pages

## Suggested visual improvements

The design pass is welcome to:

- Hover effects, transitions, polish on the Nations table
- Better empty states for placeholder pages
- A search/filter bar on the index (would need a React island)
- Better mobile layout for the Nations grid (currently relies on horizontal scroll)
- A "Compare" view: pick 2-3 nations side by side
- Better backlink rendering — clustering, counts, search
- Filter chips above the Nations table (by family, by yield, by tech)
- A patch indicator in the header (read `data/patch.json`)

## How to run locally

```sh
make install    # one-time: npm + pip deps
make patch      # full pipeline: sync from Steam → extract art → build data → diff → build
make dev        # astro dev at http://localhost:4321/owreference/
make build      # static output to ./dist/
```

## Open questions for the user

Things still TBD that affect design choices:

1. **GitHub username** — `astro.config.mjs` has placeholder `USERNAME`; fix before deploy.
2. **Patch version source** — currently uses `.app` mtime; could read Unity `PlayerSettings` for real version.
3. **Hand off design first or fill remaining tabs first?** Most tabs are placeholders. Designing on Nations alone is fine but you'll iterate as the other pages come online.
