#!/usr/bin/env python3
"""
Extract Old World game art from Unity asset bundles (pinacotheca-style).

Reads Sprite objects from the game's `resources.assets` and friends, routes
them to public/img/{crests,archetypes,families,tribes,portraits,...} by
naming convention. Handles dupes by keeping the largest image per name.

Also extracts the lush 2048×1024 event-popup backgrounds (Texture2D, named
by `<zBackgroundName>` in eventStory/cityEvent/scenario XML) to
public/img/events/<slug>.png.

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
XML_INFOS = ROOT / "reference" / "XML" / "Infos"
DEFAULT_INSTALL = Path.home() / "Library/Application Support/Steam/steamapps/common/Old World"

# Routing table: (regex on sprite name) → (output dir, slug-from-match)
# Regexes match against the Sprite m_Name as-found in the bundle.
ROUTES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^CREST_NATION_([A-Z_]+?)(_SEAT)?$"), "crests"),
    (re.compile(r"^CREST_FAMILY_([A-Z_]+?)(_SEAT)?$"), "families"),
    (re.compile(r"^CREST_TRIBE_([A-Z_]+?)(_SEAT)?$"), "tribes"),
    (re.compile(r"^CREST_ARCHETYPE_([A-Z_]+?)(_SEAT)?$"), "archetypes"),
    (re.compile(r"^CULTURE_(WEAK|DEVELOPING|STRONG|LEGENDARY)()$"), "icons/culture"),
    (re.compile(r"^YIELD_([A-Z_]+?)()$"), "icons/yields"),
    # Character rating glyphs (Wisdom/Charisma/Courage/Discipline) — the game
    # shows these as icons next to the +N value on archetype / cognomen screens.
    (re.compile(r"^RATING_([A-Z_]+?)()$"), "icons/ratings"),
    (re.compile(r"^RESOURCE_([A-Z_]+?)()$"), "icons/resources"),
    (re.compile(r"^SPECIALIST_([A-Z_]+?)()$"), "icons/specialists"),
    (re.compile(r"^TECH_([A-Z_]+?)()$"), "icons/techs"),
    (re.compile(r"^IMPROVEMENT_SHRINE_([A-Z_]+?)()$"), "icons/shrines"),
    # NB: char class includes `'` so apostrophe assets like
    # IMPROVEMENT_SANCHI'S_STUPPA (the Great Stupa) actually match;
    # route() then sanitizes the slug to sanchi_s_stuppa.
    (re.compile(r"^IMPROVEMENT_(?!SHRINE_|RUINS|PILLAGED|FINISHED|LIBRARY_TEMP|DEAD_|.*_RUINS|SETTLEMENT_|HOVEL_|BASTION_|OUTPOST_|ANCIENT_|ENCAMPMENT_|CITY_SITE)([A-Z0-9_']+?)()$"), "icons/improvements"),
    (re.compile(r"^PROJECT_([A-Z_0-9]+?)()$"), "icons/projects"),
    (re.compile(r"^EFFECTUNIT_([A-Z_0-9]+?)()$"), "icons/effects"),
    # Historical-person portraits (dynasty founders + named characters)
    (re.compile(r"^HISTORICAL_PERSON_([A-Z_0-9]+?)()$"), "portraits/historical"),
    # Default-leader portraits used in the New Game character-select UI.
    # Often the dynasty's signature character (Ashurbanipal, Cyrus, Dido, …).
    (re.compile(r"^CHARACTER_SELECT_([A-Z_0-9]+?)()$"), "portraits/character_select"),
    # Unit-trait glyphs (the white silhouettes inside each unit's shape on
    # the map — bow for ranged, hammer for siege, etc.)
    (re.compile(r"^UNITTRAIT_([A-Z_0-9]+?)()$"), "icons/unit_traits"),
    # Character-archetype trait glyphs (Judge, Scholar, Diplomat, Schemer,
    # …) — used to show which leader archetype a mission requires.
    (re.compile(r"^TRAIT_([A-Z_0-9]+?)()$"), "icons/traits"),
    # Religion symbols — clergy missions are gated by faith.
    (re.compile(r"^RELIGION_([A-Z_0-9]+?)()$"), "icons/religions"),
    # Unit sprites for the unique-unit cards. The game has lots; we extract
    # everything starting with UNIT_ (excluding action/UI sprites).
    (re.compile(r"^UNIT_(?!ACTION_|TARGET_|TARGETING_|MOVE_|ATTACK_)([A-Z_0-9]+?)()$"), "icons/units"),
]

# Some sprite names ship TWICE at different sizes: a large illustrated portrait
# and a small white silhouette glyph (the one drawn inside the unit's map
# marker — a sling for Slinger, a bow for Archer). Keeping only the largest
# per name silently threw the glyph away, so these routes are extracted by
# SMALLEST instead, into a parallel directory.
SMALLEST_ROUTES = [
    (re.compile(r"^UNIT_(?!ACTION_|TARGET_|TARGETING_|MOVE_|ATTACK_)([A-Z_0-9]+?)()$"), "icons/unit_glyphs"),
]


def route(name: str, table=None) -> tuple[str, str, bool] | None:
    """Return (output_dir, slug, is_seat) or None."""
    for pat, out_dir in (table if table is not None else ROUTES):
        m = pat.match(name)
        if m:
            # Sanitize: lower-case, any non [a-z0-9_] → _ (collapse runs).
            # No-op for the usual ALL_CAPS_UNDERSCORE names; only rewrites
            # oddballs like SANCHI'S_STUPPA → sanchi_s_stuppa so the file
            # is shell/URL-safe and matches build_wonders' slug resolver.
            slug = re.sub(r"[^a-z0-9_]+", "_", m.group(1).lower()).strip("_")
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
    smallest: dict[tuple[str, str, bool], Image.Image] = {}

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

            # same sprite, opposite selection rule → the silhouette glyph
            rs = route(name, SMALLEST_ROUTES)
            if rs:
                gkey = (rs[0], rs[1], rs[2])
                gcur = smallest.get(gkey)
                if gcur is None or (gcur.size[0] * gcur.size[1]) > area:
                    smallest[gkey] = img

    # Save best images
    counts: dict[str, int] = {}
    for (out_dir, slug, is_seat), img in list(best.items()) + list(smallest.items()):
        d = IMG / out_dir
        d.mkdir(parents=True, exist_ok=True)
        suffix = "-seat" if is_seat else ""
        out_path = d / f"{slug}{suffix}.png"
        img.save(out_path)
        counts[out_dir] = counts.get(out_dir, 0) + 1
        if verbose:
            print(f"  ✓ {out_path.relative_to(ROOT)}  ({img.size[0]}×{img.size[1]})")

    return counts


_BG_RE = re.compile(r"<zBackgroundName>([^<]+)</zBackgroundName>")


def load_background_names(xml_dir: Path) -> set[str]:
    """Read every `<zBackgroundName>` value from XML/Infos/*.xml.

    Values come from eventStory*.xml, cityEvent.xml, scenario.xml, unit.xml.
    Some references include the `Sprites/Events/` prefix — strip it.
    """
    names: set[str] = set()
    if not xml_dir.is_dir():
        return names
    for f in xml_dir.glob("*.xml"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in _BG_RE.finditer(text):
            n = m.group(1).strip()
            if not n or n.upper() == "DEFAULT":
                continue
            if "/" in n:
                n = n.rsplit("/", 1)[-1]
            names.add(n)
    return names


def _bg_slug(name: str) -> str:
    """File-safe slug for a background name. Lowercase, [a-z0-9_]+, hyphens→_."""
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")


def extract_event_backgrounds(install: Path, verbose: bool = False) -> int:
    """Extract event-popup backgrounds as Texture2D → public/img/events/<slug>.png.

    Match Texture2D `m_Name` (case-insensitive) against `<zBackgroundName>`
    values harvested from the game XML. Keep the largest image per slug to
    handle dupes between bundles or capitalization-variants.
    """
    wanted = load_background_names(XML_INFOS)
    if not wanted:
        print("→ no background names found in reference/XML/Infos — skipping")
        return 0
    # case-folded → canonical name
    wanted_lc = {n.lower(): n for n in wanted}

    files = asset_files(install)
    print(f"→ event-bg pass: {len(wanted)} names, scanning {len(files)} asset files")

    # slug → (area, PIL.Image)
    best: dict[str, tuple[int, Image.Image]] = {}
    for ap in files:
        try:
            env = UnityPy.load(str(ap))
        except Exception:
            continue
        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue
            try:
                data = obj.read()
            except Exception:
                continue
            nm = getattr(data, "m_Name", "") or ""
            if not nm:
                continue
            canonical = wanted_lc.get(nm.lower())
            if canonical is None:
                continue
            try:
                img = data.image
            except Exception:
                continue
            if img is None:
                continue
            # Many event backgrounds in the bundle are stored upside-down (Unity
            # texture coords); the in-game UI flips them. Detect by aspect:
            # legitimate event splashes are landscape 2:1, but we can't infer
            # orientation from name alone, so leave the raw image. PIL's tobytes
            # already comes top-left origin from UnityPy.
            slug = _bg_slug(canonical)
            area = img.size[0] * img.size[1]
            prev = best.get(slug)
            if prev is None or prev[0] < area:
                best[slug] = (area, img)

    out_dir = IMG / "events"
    out_dir.mkdir(parents=True, exist_ok=True)
    for slug, (_, img) in best.items():
        out_path = out_dir / f"{slug}.png"
        img.save(out_path)
        if verbose:
            print(f"  ✓ {out_path.relative_to(ROOT)}  ({img.size[0]}×{img.size[1]})")

    missing = sorted(wanted - {n for n in wanted if _bg_slug(n) in best})
    if missing:
        print(f"  ! {len(missing)} background name(s) had no matching Texture2D:")
        for m in missing:
            print(f"      {m}")
    return len(best)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", type=Path, default=DEFAULT_INSTALL)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument(
        "--only",
        choices=("sprites", "events", "all"),
        default="all",
        help="which pass to run (default: all)",
    )
    args = ap.parse_args()

    if args.only in ("sprites", "all"):
        counts = extract(args.install, verbose=args.verbose)
        print("\n→ extracted sprites:")
        for k, v in sorted(counts.items()):
            print(f"   {k:12s} {v}")
    if args.only in ("events", "all"):
        n = extract_event_backgrounds(args.install, verbose=args.verbose)
        print(f"\n→ extracted event backgrounds: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
