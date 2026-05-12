#!/usr/bin/env python3
"""
Build src/data/units.json from unit.xml + effectUnit.xml + unitTrait.xml.

For each combat-relevant unit we capture stats (strength, HP, move, sight,
range, attack pattern), training cost / upkeep yields, traits, tech prereq,
and a flattened "counters" list derived from the unit's built-in EffectUnit
modifiers — anything with an aiUnitTraitModifier* or aiAttackPercent line
becomes a "+50% vs Mounted" entry.

Non-combat units (settlers, workers, scouts) are kept but flagged so the
page can group them separately.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, fmt_decimal,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "units.json"


# The classes we surface as primary "unit class" labels. Same vocabulary the
# spreadsheet's rock-paper-scissors chart uses. Order matters — the first
# matching trait wins, so POLEARM is checked before INFANTRY (a Hoplite is
# tagged with both, and "Polearm" is the more useful column for combat math).
PRIMARY_TRAITS = [
    "UNITTRAIT_SIEGE",
    "UNITTRAIT_RANGED",
    "UNITTRAIT_POLEARM",
    "UNITTRAIT_MOUNTED",
    "UNITTRAIT_INFANTRY",
    "UNITTRAIT_SHIP",
    "UNITTRAIT_DISCIPLE",
    "UNITTRAIT_WORKER",
    "UNITTRAIT_HORSE",
    "UNITTRAIT_CAMEL",
    "UNITTRAIT_ELEPHANT",
]

# Skinny labels for trait references in counter strings.
TRAIT_LABEL_OVERRIDES = {
    "UNITTRAIT_INFANTRY": "Infantry",
    "UNITTRAIT_POLEARM":  "Polearm",
    "UNITTRAIT_MOUNTED":  "Mounted",
    "UNITTRAIT_MELEE":    "Melee",
    "UNITTRAIT_RANGED":   "Ranged",
    "UNITTRAIT_SIEGE":    "Siege",
    "UNITTRAIT_SHIP":     "Ship",
    "UNITTRAIT_HORSE":    "Horse",
    "UNITTRAIT_CAMEL":    "Camel",
    "UNITTRAIT_ELEPHANT": "Elephant",
    "UNITTRAIT_TRIBAL":   "Tribal",
    "UNITTRAIT_WORKER":   "Worker",
    "UNITTRAIT_DISCIPLE": "Disciple",
    "UNITTRAIT_PROMOTABLE": "Promotable",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def trait_label(t: str) -> str:
    return TRAIT_LABEL_OVERRIDES.get(t, t.replace("UNITTRAIT_", "").title())


def attack_label(t: str) -> str:
    return t.replace("ATTACK_", "").title()


def collect_counter_lines(effect_ids: list[str], eu_idx: dict[str, ET.Element]) -> list[dict]:
    """Walk the unit's EffectUnits and pull counter-style modifiers as
    structured rows: {kind, target, value}. Lets the page render either a
    chip or a row."""
    rows: list[dict] = []
    for eid in effect_ids:
        e = eu_idx.get(eid)
        if e is None:
            continue
        for tag, kind in [
            ("aiUnitTraitModifier",        "vs"),
            ("aiUnitTraitModifierMelee",   "melee vs"),
            ("aiUnitTraitModifierAttack",  "attack vs"),
            ("aiUnitTraitModifierDefense", "defense vs"),
        ]:
            for pair in e.findall(f"{tag}/Pair"):
                t = pair.findtext("zIndex") or ""
                v = int(pair.findtext("iValue") or "0")
                if v != 0:
                    rows.append({
                        "source": eid,
                        "kind": kind,
                        "target": trait_label(t),
                        "targetId": t,
                        "value": v,
                    })
        # Attack pattern boost (Pierce I etc.) — informational, not a counter
        for pair in e.findall("aiAttackPercent/Pair"):
            a = pair.findtext("zIndex") or ""
            v = int(pair.findtext("iValue") or "0")
            if v != 0:
                rows.append({
                    "source": eid,
                    "kind": "attack",
                    "target": attack_label(a),
                    "targetId": a,
                    "value": v,
                })
    return rows


def is_combat_unit(entry: ET.Element) -> bool:
    """A unit is 'combat' if it has Strength > 0 and bRegular=1 (regular army),
    OR is a barbarian raider / tribe unit with strength. Settlers/workers
    have iStrength but aren't combat-trained."""
    strength = int(entry.findtext("iStrength") or "0")
    if strength <= 0:
        return False
    if (entry.findtext("bFound") or "0") == "1":  # settler
        return False
    if (entry.findtext("bBuild") or "0") == "1":  # worker
        return False
    if (entry.findtext("bCaravan") or "0") == "1":
        return False
    if (entry.findtext("bGeneral") or "0") == "1" and (entry.findtext("bRegular") or "0") != "1":
        return False
    return True


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text = indexes.get("__text__", {})
    eu_idx = indexes.get("effectUnit.xml", {})

    units: list[dict] = []
    for entry in parse("unit.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt or not zt.startswith("UNIT_"):
            continue

        name_key = entry.findtext("Name") or ""
        name = text.get(name_key, zt.replace("UNIT_", "").replace("_", " ").title())

        traits = [t.text for t in entry.findall("aeUnitTrait/zValue") if t.text]
        # Primary class follows PRIMARY_TRAITS priority — pick the *highest-
        # priority* trait this unit carries, not the first one listed on the unit.
        traits_set = set(traits)
        primary = next((t for t in PRIMARY_TRAITS if t in traits_set), traits[0] if traits else "")

        effect_ids = [t.text for t in entry.findall("aeEffectUnit/zValue") if t.text]

        # Costs and consumption
        costs: list[dict] = []
        for pair in entry.findall("aiYieldCost/Pair"):
            yk = (pair.findtext("zIndex") or "").replace("YIELD_", "").lower()
            iv = int(pair.findtext("iValue") or "0")
            if yk and iv:
                costs.append({"yield": yk, "value": iv})

        consumption: list[dict] = []
        for pair in entry.findall("aiYieldConsumption/Pair"):
            yk = (pair.findtext("zIndex") or "").replace("YIELD_", "").lower()
            iv = int(pair.findtext("iValue") or "0")
            if yk and iv:
                consumption.append({"yield": yk, "value": iv})

        upgrade_to = [t.text for t in entry.findall("aeUpgradeUnit/zValue") if t.text]
        obsolete_tech = [t.text for t in entry.findall("aeObsoleteTech/zValue") if t.text]

        # XML-derived counter modifiers
        counters = collect_counter_lines(effect_ids, eu_idx)

        units.append({
            "id": zt,
            "slug": zt.replace("UNIT_", "").lower(),
            "name": name,
            "isCombat": is_combat_unit(entry),
            "iconSlug": (entry.findtext("zIconName") or zt).replace("UNIT_", "").lower(),
            "techPrereq": entry.findtext("TechPrereq") or "",
            "nationPrereq": entry.findtext("NationPrereq") or "",
            "primaryTrait": primary,
            "primaryLabel": trait_label(primary) if primary else "",
            "traits": [trait_label(t) for t in traits],
            "traitIds": traits,
            "strength":  int(entry.findtext("iStrength")  or "0"),
            "hp":        int(entry.findtext("iHPMax")     or "0"),
            "movement":  int(entry.findtext("iMovement")  or "0"),
            "vision":    int(entry.findtext("iVision")    or "0"),
            "rangeMin":  int(entry.findtext("iRangeMin")  or "0"),
            "rangeMax":  int(entry.findtext("iRangeMax")  or "0"),
            "fatigue":   int(entry.findtext("iFatigue")   or "0"),
            "production":   int(entry.findtext("iProduction")   or "0"),
            "upgradeCost":  int(entry.findtext("iUpgradeCost")  or "0"),
            "trainingYield": (entry.findtext("ProductionType") or "").replace("YIELD_", "").lower(),
            "isMelee":     (entry.findtext("bMelee")    or "0") == "1",
            "isWater":     (entry.findtext("bWater")    or "0") == "1",
            "isRangeFlat": (entry.findtext("bRangeFlat") or "0") == "1",
            "costs": costs,
            "consumption": consumption,
            "upgradeTo": upgrade_to,
            "obsoleteTech": obsolete_tech,
            "effectUnits": effect_ids,
            "counters": counters,
            "gameContent": entry.findtext("GameContentRequired") or "",
        })

    units.sort(key=lambda u: (not u["isCombat"], u["primaryLabel"] or "z", u["strength"], u["slug"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(units, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(units)} units")
    return 0


if __name__ == "__main__":
    sys.exit(main())
