#!/usr/bin/env python3
"""Build src/data/tribe_conversion.json — barbarian sites turning into tribe sites.

An in-play mechanic, not map generation: every turn, each barbarian-owned
settlement rolls to be adopted by the nearest real (diplomacy-capable) tribe.
Transcribed from Tile.doTribeTurn (Tile.cs ~11372) and
Game.findNearestSettlementTribe (Game.cs:15111); the numbers are per
tribe-level difficulty setting in tribeLevel.xml.

Emitted:
  levels[]  — per tribe level: the start turn, the per-turn percent, and the
              derived odds of having converted by turn N
  search    — the pathfind range for finding an adopting tribe
  tribes    — which tribes can adopt (bDiplomacy) vs which are barbarian pools
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "tribe_conversion.json"

# Tile.cs: findNearestSettlementTribe(this, 12) — hardcoded at the call site,
# not an XML field, so it is transcribed here with its source location.
SEARCH_RANGE = 12
SEARCH_SOURCE = "Tile.cs — findNearestSettlementTribe(this, 12)"


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("text-*.xml")):
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        for e in root.findall("Entry"):
            k, v = e.findtext("zType"), e.findtext("en-US")
            if k and v and k not in out:
                v = re.sub(r"\{[^}]*\}", "", v.split("~")[0])
                out[k] = re.sub(r"\s{2,}", " ", v).strip()
    return out


def load_gendered() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("genderedText*.xml")):
        for entry in ET.parse(p).getroot().findall("Entry"):
            zid = entry.findtext("zType") or ""
            for pair in entry.findall("Texts/Pair"):
                if (pair.findtext("zIndex") or "").endswith("MASCULINE"):
                    out[zid] = pair.findtext("zValue") or ""
                    break
    return out


def main() -> int:
    text = load_text()
    gendered = load_gendered()

    def name_of(key: str, fallback: str) -> str:
        if key.startswith("GENDERED_TEXT_"):
            key = gendered.get(key, key)
        return text.get(key, fallback)

    levels = []
    for e in parse("tribeLevel.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        turn = int(e.findtext("iTribeConvertTurn") or "0")
        prob = int(e.findtext("iTribeConvertProb") or "0")
        row = {
            "id": z,
            "name": text.get(e.findtext("Name") or "", z.replace("TRIBELEVEL_", "").title()),
            "startTurn": turn,
            "percent": prob,
            "unitRange": int(e.findtext("iMaxUnitsRange") or "0"),
            "canConvert": turn > 0 and prob > 0,
        }
        # P(at least one success) over N eligible turns — the roll is per site
        # per turn, so this is the odds a given quiet site has flipped by then.
        if row["canConvert"]:
            row["odds"] = [
                {"turnsAfter": n,
                 "byTurn": turn + n,
                 "chance": round((1 - (1 - prob / 100) ** n) * 100, 1)}
                for n in (10, 25, 50, 100)
            ]
        else:
            row["odds"] = []
        levels.append(row)

    adopters, barbarian = [], []
    for e in parse("tribe.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        entry = {
            "id": z,
            "name": name_of(e.findtext("GenderedName") or "", z.replace("TRIBE_", "").title()),
            "diplomacy": (e.findtext("bDiplomacy") or "0") == "1",
        }
        (adopters if entry["diplomacy"] else barbarian).append(entry)

    data = {
        "levels": levels,
        "search": {"range": SEARCH_RANGE, "source": SEARCH_SOURCE},
        "adopters": adopters,
        "barbarian": barbarian,
        "counts": {
            "convertingLevels": sum(1 for l in levels if l["canConvert"]),
            "adopters": len(adopters),
        },
    }
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(levels)} tribe levels "
          f"({data['counts']['convertingLevels']} can convert), {len(adopters)} adopting tribes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
