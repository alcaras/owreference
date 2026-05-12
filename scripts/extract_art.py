#!/usr/bin/env python3
"""
Extract Old World game art from Unity asset bundles (pinacotheca-style).

Reads Sprite objects from the game's `resources.assets` and friends, routes
them to public/img/{crests,archetypes,families,tribes,portraits,...} by
naming convention. Handles dupes by keeping the largest image per name.

Output paths are stable so the site references like /img/crests/persia.png
don't depend on which bundle the sprite came from in a given patch.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import UnityPy
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "public" / "img"
DEFAULT_INSTALL = Path.home() / "Library/Application Support/Steam/steamapps/common/Old World"

# Routing table: (regex on sprite name) → (output dir, slug-from-match)
# Regexes match against the Sprite m_Name as-found in the bundle.
ROUTES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^CREST_NATION_([A-Z_]+?)(_SEAT)?$"), "crests"),
    (re.compile(r"^CREST_FAMILY_([A-Z_]+?)(_SEAT)?$"), "families"),
    (re.compile(r"^CREST_TRIBE_([A-Z_]+?)(_SEAT)?$"), "tribes"),
    (re.compile(r"^CREST_ARCHETYPE_([A-Z_]+?)(_SEAT)?$"), "archetypes"),
    (re.compile(r"^YIELD_([A-Z_]+?)()$"), "icons/yields"),
    (re.compile(r"^RESOURCE_([A-Z_]+?)()$"), "icons/resources"),
    (re.compile(r"^SPECIALIST_([A-Z_]+?)()$"), "icons/specialists"),
    (re.compile(r"^TECH_([A-Z_]+?)()$"), "icons/techs"),
    (re.compile(r"^IMPROVEMENT_SHRINE_([A-Z_]+?)()$"), "icons/shrines"),
    # General improvement icons (excludes _SHRINE_ matched above, ruins/temp
    # placeholders, and per-religion sub-icons we don't need here).
    (re.compile(r"^IMPROVEMENT_(?!SHRINE_|RUINS|PILLAGED|FINISHED|LIBRARY_TEMP|DEAD_|.*_RUINS|SETTLEMENT_|HOVEL_|BASTION_|OUTPOST_|ANCIENT_|ENCAMPMENT_|CITY_SITE)([A-Z0-9_]+?)()$"), "icons/improvements"),
]


def route(name: str) -> tuple[str, str, bool] | None:
    """Return (output_dir, slug, is_seat) or None."""
    for pat, out_dir in ROUTES:
        m = pat.match(name)
        if m:
            slug = m.group(1).lower()
            is_seat = bool(m.group(2))
            return out_dir, slug, is_seat
    return None


def asset_files(install: Path) -> list[Path]:
    data = install / "OldWorld.app" / "Contents" / "Resources" / "Data"
    if not data.is_dir():
        sys.exit(f"✗ Game data dir not found: {data}")
    files: list[Path] = []
    for p in data.iterdir():
        n = p.name
        if n == "resources.assets":
            files.append(p)
        elif n.startswith("sharedassets") and not n.endswith(".resS"):
            files.append(p)
        elif n.startswith("level") and "." not in n:
            files.append(p)
    return files


def extract(install: Path, verbose: bool = False) -> dict[str, int]:
    # Track best (largest area) PIL image we've seen per (out_dir, slug, seat)
    best: dict[tuple[str, str, bool], Image.Image] = {}

    files = asset_files(install)
    print(f"→ scanning {len(files)} asset files")

    for ap in files:
        try:
            env = UnityPy.load(str(ap))
        except Exception as e:
            if verbose:
                print(f"  ! skip {ap.name}: {e}")
            continue

        for obj in env.objects:
            if obj.type.name != "Sprite":
                continue
            try:
                data = obj.read()
            except Exception:
                continue
            name = getattr(data, "m_Name", "") or ""
            r = route(name)
            if not r:
                continue
            out_dir, slug, is_seat = r
            try:
                img = data.image
            except Exception:
                continue
            if img is None:
                continue
            key = (out_dir, slug, is_seat)
            area = img.size[0] * img.size[1]
            cur = best.get(key)
            if cur is None or (cur.size[0] * cur.size[1]) < area:
                best[key] = img

    # Save best images
    counts: dict[str, int] = {}
    for (out_dir, slug, is_seat), img in best.items():
        d = IMG / out_dir
        d.mkdir(parents=True, exist_ok=True)
        suffix = "-seat" if is_seat else ""
        out_path = d / f"{slug}{suffix}.png"
        img.save(out_path)
        counts[out_dir] = counts.get(out_dir, 0) + 1
        if verbose:
            print(f"  ✓ {out_path.relative_to(ROOT)}  ({img.size[0]}×{img.size[1]})")

    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", type=Path, default=DEFAULT_INSTALL)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    counts = extract(args.install, verbose=args.verbose)
    print("\n→ extracted:")
    for k, v in sorted(counts.items()):
        print(f"   {k:12s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
