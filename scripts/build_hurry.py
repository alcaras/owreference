#!/usr/bin/env python3
"""Build src/data/hurry.json — everything the rush calculator needs.

The hurry cost formulas live in City.cs (getHurry{Civics,Training,Money,Orders,
Population}Cost + getModifiedHurryCost); the constants they read live in
globalsInt.xml. We emit the constants rather than the results so the page can
replay the engine's exact integer arithmetic client-side.

Four things move a hurry cost, and only four:
  1. missing production  — getBuildDiffWholePositive(build, false)
  2. prior hurries of that channel IN THAT CITY — iCost *= (10 + count) / 10
  3. progress below 50%  — cost modified by (50 - percent)
  4. the build's production type — yield.iHurryModifier, and only YIELD_GROWTH
     carries one (+50), which is why Workers/Settlers rush dearer than soldiers
     of the same cost.

The unit identity itself never enters the formula, only its production cost and
production type — so the picker is a convenience over a plain cost number.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "hurry.json"

# Constants the client needs to replay City.cs arithmetic.
WANTED_GLOBALS = [
    "HURRY_CIVICS_COST_BASE", "HURRY_CIVICS_COST_MODIFIER",
    "HURRY_TRAINING_COST_BASE", "HURRY_TRAINING_COST_MODIFIER",
    "HURRY_MONEY_COST_BASE", "HURRY_MONEY_COST_PER",
    "HURRY_ORDERS_COST_BASE", "HURRY_ORDERS_COST_MODIFIER",
    "HURRY_POPULATION_COST_BASE", "HURRY_POPULATION_COST_PER",
    "HURRY_DISCONTENT_COST_BASE", "HURRY_DISCONTENT_COST_PER",
]


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
                out[k] = re.sub(r"^icon\([^)]*\)", "", v.split("~")[0]).strip()
    return out


def main() -> int:
    text = load_text()

    globals_int = {}
    for e in parse("globalsInt.xml").findall("Entry"):
        z = e.findtext("zType")
        if z in WANTED_GLOBALS:
            globals_int[z] = int(e.findtext("iValue") or "0")
    missing = [g for g in WANTED_GLOBALS if g not in globals_int]
    if missing:
        print(f"✗ globalsInt.xml is missing {missing}", file=sys.stderr)
        return 1

    # Only YIELD_GROWTH carries one today; read them all so a patch that adds
    # another surfaces without a code change.
    yield_hurry = {}
    for e in parse("yield.xml").findall("Entry"):
        v = e.findtext("iHurryModifier")
        if v and int(v):
            yield_hurry[e.findtext("zType")] = int(v)

    units = []
    for e in parse("unit.xml").findall("Entry"):
        prod_type = e.findtext("ProductionType")
        if not prod_type:
            continue
        z = e.findtext("zType") or ""
        production = int(e.findtext("iProduction") or "0")
        if production <= 0:
            continue  # free/event units (Hanno's scout) — nothing to hurry
        units.append({
            "id": z,
            "name": text.get(e.findtext("Name") or "", z.replace("UNIT_", "").title()),
            "productionType": prod_type,
            "production": production,
            # each copy already built in this city adds this to the cost
            "productionCity": int(e.findtext("iProductionCity") or "0"),
            "productionPer": int(e.findtext("iProductionPer") or "0"),
            "strength": int(e.findtext("iStrength") or "0") // 10,
            "nation": e.findtext("NationPrereq") or "",
            "noHurry": (e.findtext("bNoHurry") or "0") == "1",
            "dlc": e.findtext("GameContentRequired") or "",
        })
    units.sort(key=lambda u: (u["productionType"], u["production"], u["name"]))

    projects = []
    for e in parse("project.xml").findall("Entry"):
        cost = int(e.findtext("iCost") or "0")
        if cost <= 0 or (e.findtext("bHidden") or "0") == "1":
            continue
        z = e.findtext("zType") or ""
        projects.append({
            "id": z,
            "name": text.get(e.findtext("Name") or "", z.replace("PROJECT_", "").title()),
            "productionType": e.findtext("ProductionType") or "YIELD_CIVICS",
            "production": cost,
            "noHurry": (e.findtext("bNoHurry") or "0") == "1",
            "dlc": e.findtext("GameContentRequired") or "",
        })
    projects.sort(key=lambda p: (p["production"], p["name"]))

    data = {
        "globals": globals_int,
        "yieldsMultiplier": 10,
        "yieldHurryModifier": yield_hurry,
        "units": units,
        "projects": projects,
    }
    OUT.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(units)} units, "
          f"{len(projects)} projects, {len(yield_hurry)} yield hurry modifier(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
