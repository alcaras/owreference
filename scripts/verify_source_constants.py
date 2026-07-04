#!/usr/bin/env python3
"""
Tripwire for hand-maintained game-code constants.

Some site content documents logic that lives only in compiled game code
(reference/Source/), e.g. the religion-conversion scoring in
src/data/annotations/conversion.yaml. We can't auto-derive those values,
but we CAN detect when the cited source functions change — which is the
signal to re-verify the yaml by hand.

For each watched function this script:
  1. confirms the function still exists in the cited file,
  2. hashes the function body (first N lines) and compares against the
     hash recorded in data/source-constants.lock.json.

On first run (or after intentional re-verification) run with --update to
record current hashes. A mismatch afterwards prints a loud warning listing
which yaml sections need a human re-check. Exit 0 always — this is a
warning system, not a gate (the patch pipeline must not hard-fail on it).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "reference" / "Source"
LOCK = ROOT / "data" / "source-constants.lock.json"

# (file, function name, lines-of-body to hash, what to re-verify on change)
WATCHED = [
    ("Base/Game/GameCore/Player.cs", "doFamilyReligion", 80,
     "conversion.yaml → family: rotation/startTurn/threshold/scoring"),
    ("Base/Game/GameCore/Character.cs", "chooseReligion", 120,
     "conversion.yaml → character: threshold/cityScoring/roleScoring"),
    ("Base/Game/GameCore/Character.cs", "doReligion", 60,
     "conversion.yaml → character: whoRolls (prob/age gates)"),
    ("Base/Game/GameCore/Character.cs", "canConvertReligion", 60,
     "conversion.yaml → character: whoRolls (eligibility)"),
    ("Base/Game/GameCore/Character.cs", "getCognomenMinValue", 40,
     "cognomens.json calculator thresholds (build_cognomens.py)"),
    ("Base/Game/GameCore/Character.cs", "updateCognomen", 80,
     "cognomens-tracker award routine (build_cognomens.py)"),
    ("Base/Game/GameCore/Player.cs", "updateFamilyHead", 110,
     "family_heads.json weights (d1000 +400 elder +200 council +200 job) — family-heads page"),
    ("Base/Game/GameCore/Character.cs", "canHeadFamily", 60,
     "family_heads.json eligibility (adult/not-leader/not-religion-head/traits) — family-heads page"),
    ("Base/Game/GameCore/Tile.cs", "skipImprovementUnitTurns", 30,
     "tribe_camps.json pause rule (cap, no-raid-target halving, area cap) — camp-spawning page"),
    ("Base/Game/GameCore/Tile.cs", "resetImprovementUnitTurns", 35,
     "tribe_camps.json interval math (level modifier, co-op factor, turn-1 halving) — camp-spawning page"),
    ("Base/Game/GameCore/Unit.cs", "makeDead", 60,
     "tribe_camps.json kill acceleration (nearest settlement ×4/5 while >4) — camp-spawning page"),
]


def extract_function(text: str, name: str, n_lines: int) -> tuple[int, str] | None:
    """Return (1-based line number, first n_lines of body) of the function."""
    pat = re.compile(rf"^\s*(?:public|protected|private|internal)[^\n=]*\b{re.escape(name)}\s*\(", re.M)
    m = pat.search(text)
    if not m:
        return None
    line_no = text.count("\n", 0, m.start()) + 1
    lines = text[m.start():].splitlines()[:n_lines]
    return line_no, "\n".join(lines)


def main() -> int:
    update = "--update" in sys.argv
    if not SOURCE.exists():
        print("⚠ reference/Source not present — skipping source-constant check")
        return 0

    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    new_lock: dict[str, dict] = {}
    stale: list[str] = []
    missing: list[str] = []

    for rel, fn, n, what in WATCHED:
        key = f"{rel}::{fn}"
        path = SOURCE / rel
        if not path.exists():
            missing.append(f"{key} — file not found")
            continue
        got = extract_function(path.read_text(errors="replace"), fn, n)
        if got is None:
            missing.append(f"{key} — function not found (renamed?) → re-verify: {what}")
            continue
        line_no, body = got
        digest = hashlib.sha256(body.encode()).hexdigest()[:16]
        new_lock[key] = {"line": line_no, "hash": digest}
        prev = lock.get(key)
        if prev and prev.get("hash") != digest:
            stale.append(f"{key} (line {prev.get('line')}→{line_no}) → re-verify: {what}")

    if update or not LOCK.exists():
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        LOCK.write_text(json.dumps(new_lock, indent=2, sort_keys=True) + "\n")
        print(f"✓ recorded {len(new_lock)} source-function hashes → {LOCK.relative_to(ROOT)}")

    for m_ in missing:
        print(f"⚠ {m_}")
    if stale:
        print("⚠ GAME SOURCE CHANGED — hand-maintained constants need re-verification:")
        for s in stale:
            print(f"  • {s}")
        print("  After re-verifying/updating the yaml, run: python3 scripts/verify_source_constants.py --update")
    elif not missing:
        print(f"✓ source-constant check: {len(new_lock)} watched functions unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
