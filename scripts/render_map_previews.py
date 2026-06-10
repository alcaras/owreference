#!/usr/bin/env python3
"""
render_map_previews.py — generate preview images for every map script.

For each script in src/data/mapscripts.json, headlessly generates maps
with the sibling owmapgen harness (cc/owmapgen — mono CLI around the
game's own map-generation code) and renders them with owmapgen-lab's
render_pretty (the owtournamentatlas "tactical map" renderer: terrain
hexes, rivers, resource icons, city sites, capital stars, dark bg).

Settings (deterministic — same inputs → byte-stable maps):
  * Default scripts:  --size medium --players 6   ("6-player Medium")
  * Duel scripts (DOTA — the script is built around two diagonally
    opposed bases): --size smallest --players 2 --mirror
    --point-symmetry  ("1v1 Duel"; DOTA locks point-symmetry in-game)
  * Seeds: 11, 22, 33 (one image per seed). If a seed fails to
    generate, seed+1000 is tried once as a documented fallback.

Output: public/img/mapscripts/{slug}-{n}.png  (n = 1..3, ordinal per
seed), downscaled to 800px wide and quantized to a 256-colour palette
to keep the committed weight low (~130 KB each).

Requires the LOCAL-ONLY sibling repos (never pushed):
  cc/owmapgen       — the mono harness (owmapgen wrapper script)
  cc/owmapgen-lab   — render_pretty/render_map (PIL renderer)
and mono on PATH (/opt/homebrew/bin). If either is missing this script
fails loudly rather than producing fake art.

Usage: scripts/render_map_previews.py [--force] [SLUG ...]
  --force    re-render even if the output PNG already exists
  SLUG ...   limit to specific slugs (default: all 22)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CC = ROOT.parent                       # …/cc — the sibling-repo dir
OWMAPGEN = CC / "owmapgen" / "owmapgen"
LAB_SCRIPTS = CC / "owmapgen-lab" / "scripts"
OUTDIR = ROOT / "public" / "img" / "mapscripts"
MAPSCRIPTS = ROOT / "src" / "data" / "mapscripts.json"

SEEDS = (11, 22, 33)        # deterministic; ordinal n in {slug}-{n}.png
SEED_FALLBACK_OFFSET = 1000  # tried once if a seed fails to generate
WIDTH = 800                  # final image width (px)
HEX = 12                     # render_pretty hex size before downscale
DUEL_IDS = {"DOTA"}          # scripts whose intended layout is a 1v1

ENV = {**os.environ, "PATH": "/opt/homebrew/bin:" + os.environ.get("PATH", "")}


def die(msg: str) -> None:
    print(f"render_map_previews: {msg}", file=sys.stderr)
    sys.exit(1)


if not OWMAPGEN.exists():
    die(f"owmapgen harness not found at {OWMAPGEN} (local-only sibling repo)")
if not (LAB_SCRIPTS / "render_pretty.py").exists():
    die(f"render_pretty.py not found under {LAB_SCRIPTS}")

sys.path.insert(0, str(LAB_SCRIPTS))
from render_pretty import render_pretty  # noqa: E402
from PIL import Image  # noqa: E402


def gen(td: str, script_name: str, duel: bool, seed: int) -> Path | None:
    """Run owmapgen; return the produced XML path (or None on failure)."""
    cmd = [str(OWMAPGEN), "--script", script_name, "--seed", str(seed),
           "--output", td]
    if duel:
        cmd += ["--size", "smallest", "--players", "2",
                "--mirror", "--point-symmetry"]
    else:
        cmd += ["--size", "medium", "--players", "6"]
    before = set(Path(td).glob("*.xml"))
    r = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    new = [p for p in Path(td).glob("*.xml") if p not in before]
    if not new:
        tail = (r.stdout or "")[-400:] + (r.stderr or "")[-400:]
        print(f"    FAILED ({script_name} s{seed}): {tail.strip()}",
              file=sys.stderr)
        return None
    return max(new, key=lambda p: p.stat().st_mtime)


def shrink(big_png: Path, out_png: Path) -> int:
    im = Image.open(big_png)
    if im.width > WIDTH:
        im = im.resize((WIDTH, round(im.height * WIDTH / im.width)),
                       Image.LANCZOS)
    q = im.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT,
                                   dither=Image.FLOYDSTEINBERG)
    q.save(out_png, optimize=True)
    return out_png.stat().st_size


def main() -> None:
    args = [a for a in sys.argv[1:]]
    force = "--force" in args
    only = {a for a in args if not a.startswith("--")}

    scripts = json.loads(MAPSCRIPTS.read_text())
    if only:
        scripts = [s for s in scripts if s["slug"] in only]
        missing = only - {s["slug"] for s in scripts}
        if missing:
            die(f"unknown slug(s): {', '.join(sorted(missing))}")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    total = 0
    failures: list[str] = []
    for s in scripts:
        duel = s["id"] in DUEL_IDS
        kind = "1v1 Duel (smallest)" if duel else "6-player Medium"
        print(f"{s['name']} [{s['slug']}] — {kind}", flush=True)
        for n, seed in enumerate(SEEDS, 1):
            out = OUTDIR / f"{s['slug']}-{n}.png"
            if out.exists() and not force:
                print(f"  seed {seed} → {out.name} (cached)")
                total += out.stat().st_size
                continue
            with tempfile.TemporaryDirectory() as td:
                xml = gen(td, s["name"], duel, seed)
                if xml is None:  # documented one-shot fallback seed
                    xml = gen(td, s["name"], duel,
                              seed + SEED_FALLBACK_OFFSET)
                if xml is None:
                    failures.append(f"{s['slug']} seed {seed}")
                    continue
                big = Path(td) / "render.png"
                render_pretty(xml, big, HEX)
                size = shrink(big, out)
            total += size
            print(f"  seed {seed} → {out.name} ({size // 1024} KB)",
                  flush=True)
    print(f"\ntotal committed weight: {total / 1e6:.1f} MB")
    if failures:
        print("FAILED (no image produced): " + ", ".join(failures),
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
