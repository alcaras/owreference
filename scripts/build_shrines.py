#!/usr/bin/env python3
"""
Build src/data/shrines.json from improvement.xml.

Every Pagan Shrine (`Class=IMPROVEMENTCLASS_SHRINE`) is rendered as a row
with: deity name, type (from AssetVariation), nation, primary yield output,
humanized effects (tile bonuses, adjacency, etc.), and the cost/specialist.

Shrine type is the Cinzel headline (with glyph), the deity is italic, and
the page colors each shrine cell by the type-derived primary yield (mirrors
the Nations page).
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_shrine_effects, load_text, fmt_decimal, yield_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "shrines.json"


# Mirrors SHRINE_TYPE_YIELD in nations.astro — keeps the page color scheme
# identical to the per-nation shrine column.
SHRINE_TYPE_YIELD = {
    "WAR":        "training",
    "KINGSHIP":   "civics",
    "WISDOM":     "science",
    "SUN":        "orders",
    "WATER":      "money",
    "LOVE":       "growth",
    "UNDERWORLD": "culture",
    "HEARTH":     "culture",
    "FIRE":       "iron",      # modifier-based: mines / lumber mills
    "HEALING":    "growth",    # modifier-based: groves / healers
    "HUNTING":    "food",      # modifier-based: camps / farms
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def main() -> int:
    text_improvement = load_text(XML_DIR, "text-improvement.xml")
    text_nation = load_text(XML_DIR, "text-nation.xml")
    indexes = load_xml_indexes(XML_DIR)

    # Dynasty → nation (Serapis is gated on DYNASTY_PTOLEMY instead of a
    # NationPrereq; resolve through nation.xml aeDynasties → Greece).
    dynasty_nation: dict[str, str] = {}
    for n_entry in parse("nation.xml").findall("Entry"):
        n_id = n_entry.findtext("zType") or ""
        for d in n_entry.findall("aeDynasties/zValue"):
            if d.text:
                dynasty_nation[d.text] = n_id

    shrines: list[dict] = []
    for entry in parse("improvement.xml").findall("Entry"):
        if (entry.findtext("Class") or "") != "IMPROVEMENTCLASS_SHRINE":
            continue

        zt = entry.findtext("zType") or ""
        nation = entry.findtext("NationPrereq") or ""
        dynasty = entry.findtext("DynastyPrereq") or ""
        if not nation.startswith("NATION_") and dynasty:
            nation = dynasty_nation.get(dynasty, "")
        if not nation.startswith("NATION_"):
            # Skip shrines without a clear nation (or dynasty) prereq.
            continue

        # Type from AssetVariation (WAR/WATER/etc.)
        av = entry.findtext("AssetVariation") or ""
        m = re.match(r"ASSET_VARIATION_IMPROVEMENT_SHRINE_([A-Z]+)", av)
        type_key = m.group(1) if m else "UNKNOWN"

        # Name: "Shrine of Ninurta" → strip prefix to "Ninurta"
        name_key = entry.findtext("Name") or ""
        full_name = text_improvement.get(name_key, zt.replace("IMPROVEMENT_SHRINE_", "").title())
        deity = re.sub(r"^Shrine of ", "", full_name).strip()

        # Religion this shrine spreads.
        religion = entry.findtext("ReligionSpread") or ""
        religion_slug = religion.replace("RELIGION_", "").lower()

        # Specialist unlocked by the shrine (acolyte tier).
        specialist = entry.findtext("Specialist") or ""
        specialist_label = specialist.replace("SPECIALIST_", "").replace("_", " ").title() if specialist else ""

        # Yield output (the per-shrine signature: +2 Training for WAR, etc.).
        outputs: list[str] = []
        for pair in entry.findall("aiYieldOutput/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0") / 10
            outputs.append(f"{fmt_decimal(v)} {y}")

        # Build cost (resource investment).
        costs: list[str] = []
        for pair in entry.findall("aiYieldCost/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0")
            costs.append(f"{v} {y}")

        # Tile-bonus / adjacency / improvement-class effects (e.g., the
        # FIRE / HEALING / HUNTING shrines that work by modifying nearby
        # improvements rather than producing yields directly).
        effects = render_shrine_effects(entry)
        # The output is already covered above, so drop duplicates.
        effects = [e for e in effects if e not in outputs]

        # Adjacency: +X% on a specific improvement class (e.g., +20% Mines).
        for pair in entry.findall("aiAdjacentImprovementClassModifier/Pair"):
            imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENTCLASS_", "").title()
            v = int(pair.findtext("iValue") or "0")
            effects.append(f"{fmt_decimal(v)}% adjacent {imp}")

        # Adjacency: +X% on a specific improvement (e.g., +20% Nets).
        for pair in entry.findall("aiAdjacentImprovementModifier/Pair"):
            imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENT_", "").title()
            v = int(pair.findtext("iValue") or "0")
            effects.append(f"{fmt_decimal(v)}% adjacent {imp}")

        # Adjacency: yield bonus on improvement class.
        for pair in entry.findall("aaiAdjacentImprovementClassYield/Pair"):
            imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENTCLASS_", "").title()
            for sp in pair.findall("SubPair"):
                y = yield_name(sp.findtext("zSubIndex"))
                v = int(sp.findtext("iValue") or "0") / 10
                effects.append(f"{fmt_decimal(v)} {y}/adjacent {imp}")

        # Adjacency: yield bonus per adjacent resource (zIndex = YIELD_*).
        for pair in entry.findall("aiAdjacentResourceYieldOutput/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0") / 10
            effects.append(f"{fmt_decimal(v)} {y} per adjacent Resource")

        # Adjacency: yield bonus per adjacent wonder (zIndex = YIELD_*).
        for pair in entry.findall("aiAdjacentWonderYieldOutput/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0") / 10
            effects.append(f"{fmt_decimal(v)} {y} per adjacent Wonder")

        # Height-based adjacency (e.g., shrines on hills/plains).
        for pair in entry.findall("aaiAdjacentHeightYieldModifier/Pair"):
            h = (pair.findtext("zIndex") or "").replace("HEIGHT_", "").title()
            for sp in pair.findall("SubPair"):
                y = yield_name(sp.findtext("zSubIndex"))
                v = int(sp.findtext("iValue") or "0")
                effects.append(f"{fmt_decimal(v)}% {y}/adjacent {h}")

        # Unit-trait XP grants (e.g., Bellona → +10 XP to Infantry).
        # XP is raw, NOT a /10 yield rate — HelpText.Improvement.cs renders
        # aiUnitTraitXP unscaled (matches the in-game tooltip).
        #
        # A non-zero aiUnitTraitXP also makes the shrine a *spawn point* for
        # promotable units of that trait: InfoHelpers.getUnitSpawnImprovements
        # (City.cs:8721) adds any improvement where maiUnitTraitXP[trait] > 0
        # to a unit's spawn-tile list. So the WAR shrine isn't just an XP
        # ground — Infantry can be trained directly onto its tile.
        for pair in entry.findall("aiUnitTraitXP/Pair"):
            trait = (pair.findtext("zIndex") or "").replace("UNITTRAIT_", "").title()
            v = int(pair.findtext("iValue") or "0")
            effects.append(f"{fmt_decimal(v)} {trait} XP")
            effects.append(f"Spawn point for {trait} units")

        # EffectCity attached to the shrine (extra per-city yield).
        ec_id = entry.findtext("EffectCity") or ""
        if ec_id:
            ec = indexes.get("effectCity.xml", {}).get(ec_id)
            if ec is not None:
                from humanize import render_effect_city
                for line in render_effect_city(ec, per_city=False, indexes=indexes):
                    if line not in effects and line not in outputs:
                        effects.append(line)

        nation_slug = nation.replace("NATION_", "").lower()
        nation_name = text_nation.get(f"TEXT_{nation}", nation.replace("NATION_", "").title())

        shrines.append({
            "id": zt,
            "slug": zt.replace("IMPROVEMENT_SHRINE_", "").lower(),
            "deity": deity,
            "fullName": full_name,
            "dynastyPrereq": dynasty.replace("DYNASTY_", "").title() if dynasty else None,
            "type": type_key,
            "typeLabel": type_key.title(),
            "primaryYield": SHRINE_TYPE_YIELD.get(type_key, "misc"),
            "subClass": int(entry.findtext("iSubClass") or "0"),
            "nation": {
                "id": nation,
                "slug": nation_slug,
                "name": nation_name,
            },
            "religion": {
                "id": religion,
                "slug": religion_slug,
            },
            "specialist": specialist_label,
            "outputs": outputs,
            "costs": costs,
            "effects": effects,
        })

    # Sort by type → nation → deity for a stable, readable order.
    type_order = ["WAR", "KINGSHIP", "WISDOM", "SUN", "WATER",
                  "LOVE", "UNDERWORLD", "HEARTH", "FIRE", "HEALING", "HUNTING"]
    type_rank = {t: i for i, t in enumerate(type_order)}
    shrines.sort(key=lambda s: (type_rank.get(s["type"], 99), s["nation"]["name"], s["deity"]))

    # Group by type for the page section banners.
    by_type: dict[str, list[dict]] = {}
    for s in shrines:
        by_type.setdefault(s["type"], []).append(s)

    type_groups: list[dict] = []
    for t in type_order:
        if t not in by_type:
            continue
        type_groups.append({
            "type": t,
            "label": t.title(),
            "primaryYield": SHRINE_TYPE_YIELD.get(t, "misc"),
            "shrines": by_type[t],
        })

    out_obj = {
        "shrines": shrines,
        "groups": type_groups,
        "totals": {
            "shrines": len(shrines),
            "types": len(type_groups),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out_obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — "
          f"{len(shrines)} shrines across {len(type_groups)} types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
