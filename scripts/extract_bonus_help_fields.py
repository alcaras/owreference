#!/usr/bin/env python3
"""Add every bonus field the game's help code reads to the helptext registry.

The registry (scripts/data/helptext_registry.json) was extracted from
HelpText.buildBonusHelp. The event popup uses a second renderer,
HelpText.buildBonusHelpRolePlaying (HelpText.Bonus.cs:15), and the fields only
IT prints (occurrence starts and ends, tribute/send/trade yields, goals,
missions, forced laws) were never enumerated, so audit_coverage.py could not
see that the site dropped them. This script finds every `bonus(eBonus).mX`
member in HelpText.Bonus.cs, maps it to its XML tag (InfoBase.cs read calls)
and, for members the registry lacks, adds an entry with the nearest TEXT key
and its en-US template. Existing entries are never touched or removed.

Idempotent: rerun after a patch (`python3 scripts/extract_bonus_help_fields.py`);
audit_coverage.py fails when the source names a member the registry lacks.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "reference" / "Source" / "Base" / "Game" / "GameCore"
HELP = SRC / "HelpText" / "HelpText.Bonus.cs"
INFOBASE = SRC / "InfoBase.cs"
REG = ROOT / "scripts" / "data" / "helptext_registry.json"
XML_DIR = ROOT / "reference" / "XML" / "Infos"

MEMBER_RE = re.compile(r"bonus\(eBonus\)\.(m[a-zA-Z]+)")

# Members that only change how ANOTHER field's line reads; they print nothing
# of their own. Recorded with "qualifies" so renderers fold them in.
QUALIFIERS = {
    "mbIgnoreDelayTurns": "occurrence start: skip the occurrence's iDelayTurns ('in N turns')",
    "mbOccurrenceSetPending": "occurrence start: add it as pending instead of starting it (debug-only line in game)",
    "mbMissionFree": "Mission: the mission costs nothing",
    "miMissionReverse": "Mission: swap actor and target",
    "miTributeTurns": "aiYieldsTribute*: how many turns the tribute lasts",
    "mbOccurrenceStart": "starts the event's own occurrence (eOccurrence from the trigger/subject)",
    "mbOccurrenceStartPending": "activates the event's pending occurrence",
    "miOccurrenceTargetSubject": "which event subject the event's occurrence starts on",
}


def member_to_xml() -> dict[str, str]:
    src = INFOBASE.read_text(errors="replace")
    return {m.group(2): m.group(1) for m in re.finditer(r'read\w*\(ctx, "(\w+)", ref (m\w+)\b', src)}


def load_text() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("text-*.xml")):
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            if k and k not in out:
                out[k] = e.findtext("en-US") or ""
    return out


def help_members() -> dict[str, tuple[int, str]]:
    """member → (first line index, renderer) for every bonus member HelpText reads."""
    lines = HELP.read_text(errors="replace").split("\n")
    fn = ""
    out: dict[str, tuple[int, str]] = {}
    for i, ln in enumerate(lines):
        m = re.match(r"\s*public virtual \w+ (build\w+)\(", ln)
        if m:
            fn = m.group(1)
        for mem in MEMBER_RE.findall(ln):
            out.setdefault(mem, (i, fn))
    return out


def main() -> int:
    reg = json.loads(REG.read_text())
    bonus = reg["bonus"]
    xml_of = member_to_xml()
    text = load_text()
    lines = HELP.read_text(errors="replace").split("\n")
    added = []
    for mem, (i, fn) in sorted(help_members().items()):
        if mem in bonus:
            continue
        keys: list[str] = []
        for ln in lines[i:i + 14]:
            keys += [k for k in re.findall(r'"(TEXT_[A-Z0-9_]+)"', ln) if k not in keys]
        # The first key near a member is sometimes a debug-only branch
        # (…_PENDING under bDebug); prefer the line players actually see.
        shown = [k for k in keys if not k.endswith("_PENDING")]
        key = (shown or keys or [None])[0]
        entry = {
            "args": [],
            "notes": f"added by extract_bonus_help_fields.py from {fn} (HelpText.Bonus.cs:{i + 1})",
            "perEntry": "none",
            "renderer": fn,
            "template": text.get(key) if key else None,
            "textKey": key,
            "valueScale": 1,
            "xmlField": xml_of.get(mem, mem[2:] if mem.startswith("m") else mem),
        }
        if mem in QUALIFIERS:
            entry["qualifies"] = QUALIFIERS[mem]
        bonus[mem] = entry
        added.append(f"{mem} → {entry['xmlField']} ({key or 'no text key'})")
    if added:
        reg.setdefault("_meta", {})["bonusHelpFields"] = (
            "bonus entries with a 'renderer' key were added by scripts/extract_bonus_help_fields.py: "
            "fields HelpText.Bonus.cs reads outside buildBonusHelp (mostly buildBonusHelpRolePlaying, "
            "the event popup), including the occurrence start/end fields the unmappedFields note "
            "below calls unrendered — the popup does render them")
        REG.write_text(json.dumps(reg, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ helptext registry: {len(added)} bonus field(s) added")
    for a in added:
        print(f"  + {a}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
