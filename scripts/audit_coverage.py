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
    # bonus-event*.xml, not bonus-event-*.xml: the plain bonus-event.xml (the
    # largest event file, home of every BONUS_OCCURRENCE_* start/end) was
    # outside the old glob.
    "bonus": ["bonus.xml"] + sorted(p.name for p in XML_DIR.glob("bonus-event*.xml")),
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


def event_bonus_checks(registry: dict) -> int:
    """Two checks for the event/mission reward path (build_missions.humanize_bonus),
    which is a separate renderer from humanize.py and once dropped every
    occurrence start/end ("Starts Era of Peace", "Ends Civil War") silently:

    1. Registry completeness: every bonus member the game's help code reads
       (HelpText.Bonus.cs, all renderers incl. the event popup's
       buildBonusHelpRolePlaying) must have a registry entry, or nothing can
       notice that we drop it. Fix: python3 scripts/extract_bonus_help_fields.py
    2. Nothing unrendered: run humanize_bonus over every bonus; a populated
       field that neither the curated code nor the registry backstop could
       turn into a line is a drop.
    """
    import re
    failures = 0
    help_cs = ROOT / "reference" / "Source" / "Base" / "Game" / "GameCore" / "HelpText" / "HelpText.Bonus.cs"
    print("── bonus (events & missions: build_missions.humanize_bonus)")
    if help_cs.exists():
        members = set(re.findall(r"bonus\(eBonus\)\.(m[a-zA-Z]+)", help_cs.read_text(errors="replace")))
        missing = sorted(members - set(registry.get("bonus", {})))
        if missing:
            failures += len(missing)
            print("  ✗ game help code reads bonus fields the registry lacks "
                  "(run scripts/extract_bonus_help_fields.py):")
            for mem in missing:
                print(f"    {mem}")
    else:
        print("  · reference/Source missing — registry completeness not checked")

    sys.path.insert(0, str(ROOT / "scripts"))
    import effects  # type: ignore
    import build_missions as bm  # type: ignore
    effects.UNRENDERED.clear()
    bonus_idx = bm.bonus_index()
    text = bm.load_text()
    for z in bonus_idx:
        bm.humanize_bonus(z, bonus_idx, text)
    unrendered = sorted(f for f in effects.UNRENDERED.get("bonus", set()) if f not in bm.HANDLED_BONUS_FIELDS)
    if unrendered:
        failures += len(unrendered)
        print("  ✗ populated bonus fields no renderer could turn into a line "
              "(curate them in scripts/event_bonus.py):")
        for f in unrendered:
            print(f"    {f}")
    if not failures:
        print(f"  ✓ {len(bonus_idx)} bonuses render; registry covers every field HelpText.Bonus.cs reads")
    return failures


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

    failures += event_bonus_checks(registry)

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
