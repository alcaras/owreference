#!/usr/bin/env python3
"""Pipeline guard: every content pack is labelled the way the game labels it.

This exists because `AKSUM` was labelled "Sacred & the Profane (Aksum)" in four
builders for three months. It ships with DLC_CALAMITIES — "Wrath of Gods" — and
nothing in the data corrects the guess: Aksum's 69 entries live in the BASE xml
files rather than a `-wog` suffixed one, and `bonus-event-sap.xml` really does
mention RELIGION_PAGAN_AKSUM. Seven builders each carried their own hand-written
map, so there was no single place the answer could be checked.

Four checks, in the order they would have caught that bug:

  1. the derived map is NON-EMPTY. Every lookup in scripts/dlc.py returns "" on a
     missing or unparseable additionalContent.xml, which would silently relabel
     everything as the base game rather than failing. Today's session hit that
     exact failure mode three separate times in other lookups, so assert it.
  2. every GameContentRequired token that appears anywhere in reference/XML/Infos
     resolves through the map. A new pack, or a renamed token, fails here rather
     than falling through to a title-cased guess.
  3. no builder hardcodes a DLC display name against a content token again.
  4. no generated dataset still carries a retired wrong label.

Run by `make audit`.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dlc as dlcmap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "src" / "data"

# Tokens no DLC grants: the game's own "you do not own this" placeholder.
UNOWNED = {"EVENT_CONTENT_UNAVAILABLE"}

# Labels that were wrong and must never reappear in generated output.
RETIRED = {
    "Sacred & the Profane (Aksum)": "AKSUM ships with Wrath of Gods",
}

# A hand-written map is a dict literal mapping a KNOWN content token to a
# string. That is what went wrong; the derived map is the only allowed source.
HANDWRITTEN = re.compile(r'"(AKSUM|CALAMITIES|EVENTPACK_RELIGION|EVENTPACK_SCANDAL|'
                         r'WONDERS_DYNASTIES|EMPIRES_OF_THE_INDUS|PHARAOHS|'
                         r'NATION_HITTITES|CAMPAIGN_GREECE)"\s*:\s*"')


def content_tokens_in_use() -> dict[str, int]:
    """Every GameContentRequired value the shipped XML actually uses."""
    out: dict[str, int] = {}
    for p in sorted(XML_DIR.glob("*.xml")):
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        for e in root.iter("GameContentRequired"):
            tok = (e.text or "").strip()
            if tok:
                out[tok] = out.get(tok, 0) + 1
    return out


def main() -> int:
    problems: list[str] = []

    # 1 — the map resolved at all.
    by_content = dlcmap.dlc_by_content()
    by_token = dlcmap.dlc_token_by_content()
    if not by_content or not by_token:
        print(f"✗ dlc map is EMPTY — is {XML_DIR / 'additionalContent.xml'} there?")
        return 1

    # 2 — every token in use is claimed by a DLC.
    used = content_tokens_in_use()
    for tok, n in sorted(used.items()):
        if tok not in by_content and tok not in UNOWNED:
            problems.append(f"content token {tok} ({n} entries) is granted by no "
                            f"DLC in additionalContent.xml — new pack? renamed token?")

    # 3 — nobody hand-wrote a label again.
    for p in sorted(SCRIPTS.glob("*.py")):
        if p.name in ("verify_dlc_labels.py", "dlc.py"):
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if HANDWRITTEN.search(line) and "dlc_by_content" not in line:
                problems.append(f"{p.name}:{i} hardcodes a DLC label — use "
                                f"dlc.label() / dlc.dlc_by_content() instead:"
                                f"\n      {line.strip()}")

    # 4 — no retired label survives in generated data.
    for p in sorted(DATA.rglob("*.json")):
        text = p.read_text()
        for bad, why in RETIRED.items():
            if bad in text:
                problems.append(f"{p.relative_to(ROOT)} still says {bad!r} — {why}")

    if problems:
        print("✗ DLC label check failed:")
        for msg in problems:
            print(f"  · {msg}")
        return 1

    print(f"✓ DLC labels: {len(by_content)} content types across "
          f"{len(set(by_token.values()))} packs, all {len(used)} tokens in use resolve")
    for tok in sorted(used):
        print(f"    {tok:24s} {used[tok]:5d} entries  →  "
              f"{by_content.get(tok, '(unowned placeholder)')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
