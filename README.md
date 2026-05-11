# Old World Reference

Successor to the [Old World Reference Spreadsheet](Old%20World%20Reference%20Spreadsheet.xlsx) — a dark-mode, in-game-styled reference site for [Old World](https://mohawkgames.com/oldworld/), auto-updated each patch from the game's own files.

## Patch workflow

```sh
make patch          # full pipeline: sync → extract art → build data → diff → site
```

Individual steps:

```sh
make sync           # rsync Steam install's Reference/ into ./reference/
make art            # extract crests + portraits from Unity bundles (pinacotheca-style)
make data           # XML + annotations → src/data/*.json
make changelog      # diff against last snapshot → append CHANGELOG.md
make dev            # astro dev server
make build          # astro build → dist/
```

## Data sources, in priority order

1. **`reference/XML/Infos/*.xml`** — canonical game data, synced from `~/Library/Application Support/Steam/steamapps/common/Old World/Reference/`. Always wins on factual conflicts.
2. **`src/data/annotations/*.yaml`** — human-curated descriptions, originally seeded from the legacy spreadsheet. We maintain this going forward.
3. **`Old World Reference Spreadsheet.xlsx`** — legacy seed only; not consulted after initial extraction.

## Layout

```
reference/         synced from Steam install — DO NOT hand-edit
scripts/           pipeline (sync, extract-art, build-data, changelog)
src/
  data/            generated JSON + hand-maintained annotations
  pages/           one .astro per sheet
  components/
  styles/
public/img/        extracted game art (committed for GH Pages)
data/snapshots/    versioned JSON for changelog diffing
```
