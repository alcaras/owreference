#!/usr/bin/env python3
"""
Effect-field coverage audit — the patch-proofing tripwire.

Three sets per effect file (effectCity / effectPlayer / effectUnit / bonus):

  populated  — fields that actually occur (non-empty) in the current XML
  renderable — fields the GAME's own help system renders, per
               scripts/data/helptext_registry.json (extracted from
               reference/Source HelpText.*.cs)
  handled    — fields our renderers cover (scripts/effects.py HANDLED_FIELDS,
               plus scripts/humanize.py's legacy coverage list if present)

Report:
  • populated ∧ renderable ∧ ¬handled  → we silently DROP player-facing data (the bug)
  • populated ∧ ¬renderable            → game hides it too (informational)
  • handled ∧ ¬populated               → dead coverage (informational)

Run as part of `make patch` (after sync, before build). Exit code 1 when
the DROP set is non-empty for any file, so new patch fields can't slip by.
Pass --warn-only to report without failing (used while coverage is being
built out).
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
REGISTRY = ROOT / "scripts" / "data" / "helptext_registry.json"

FILES = {
    "effectCity": ["effectCity.xml"],
    "effectPlayer": ["effectPlayer.xml"],
    "effectUnit": ["effectUnit.xml"],
    "bonus": ["bonus.xml"] + sorted(p.name for p in XML_DIR.glob("bonus-event-*.xml")),
}

# Bookkeeping fields that aren't effects at all.
IGNORE = {
    "zType", "Name", "zIconName", "zPortraitName", "zAudioOnStart",
    "GameContent", "zHelpOverride",
}


def populated_fields(filenames: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for entry in ET.parse(p).getroot().findall("Entry"):
            for child in entry:
                tag = child.tag
                if tag in IGNORE:
                    continue
                # Populated = has text content or sub-elements
                has_value = bool((child.text or "").strip()) or len(child) > 0
                if has_value:
                    counts[tag] = counts.get(tag, 0) + 1
    return counts


def handled_fields() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {k: set() for k in FILES}
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import effects  # type: ignore
        for k, v in getattr(effects, "HANDLED_FIELDS", {}).items():
            out.setdefault(k, set()).update(v)
        # Conscious exclusions (display flags, plumbing) count as covered —
        # the rationale lives next to SKIP_FIELDS in effects.py.
        for k, v in getattr(effects, "SKIP_FIELDS", {}).items():
            out.setdefault(k, set()).update(v)
    except ImportError:
        pass
    try:
        import humanize  # type: ignore
        for k, v in getattr(humanize, "HANDLED_FIELDS", {}).items():
            out.setdefault(k, set()).update(v)
    except ImportError:
        pass
    return out


def main() -> int:
    warn_only = "--warn-only" in sys.argv
    registry = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
    handled = handled_fields()

    failures = 0
    for section, filenames in FILES.items():
        pop = populated_fields(filenames)
        reg = registry.get(section, {})
        renderable = {v.get("xmlField") or k for k, v in reg.items()} if reg else set()
        have = handled.get(section, set())

        drops = sorted(
            f for f in pop
            if f in renderable and f not in have
        ) if renderable else sorted(f for f in pop if f not in have)
        hidden = sorted(f for f in pop if renderable and f not in renderable and f not in have)
        dead = sorted(f for f in have if f not in pop)

        print(f"── {section}: {len(pop)} populated fields, "
              f"{len(renderable)} game-renderable, {len(have)} handled")
        if drops:
            failures += len(drops)
            print(f"  ✗ DROPPED (game shows these, we don't): ")
            for f in drops:
                print(f"    {f}  ({pop[f]} entr{'y' if pop[f]==1 else 'ies'})")
        if hidden:
            print(f"  · not rendered by game either: {', '.join(hidden)}")
        if dead:
            print(f"  · handled but unused in current XML: {', '.join(dead)}")

    if not REGISTRY.exists():
        print("⚠ scripts/data/helptext_registry.json missing — ran in degraded mode "
              "(every populated-but-unhandled field counts as a drop)")

    if failures:
        print(f"\n{'⚠' if warn_only else '✗'} {failures} dropped field(s)")
        return 0 if warn_only else 1
    print("\n✓ coverage audit clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
