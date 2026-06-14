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

Each unit also carries a `category` ("normal" | "unique" | "tribal"), Culture
tier (`era`/`eraOrder` for unique units), `nationLabel`, `techLabel` and a
`source` DLC label, feeding the Units and Unique Units catalog pages.
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


# Effect-icon art lives in two extracted folders; an EffectUnit's zIconName may
# point at either (Disarm's icon is a UnitTrait sprite, most are EffectUnit
# sprites). Resolve to whichever file actually exists.
EFFECT_ICON_DIRS = ["effects", "unit_traits"]


def effect_icon_path(icon_token: str) -> str | None:
    slug = (icon_token or "").replace("EFFECTUNIT_", "").replace("UNITTRAIT_", "") \
        .replace("CONCEPT_", "").lower()
    if not slug:
        return None
    for d in EFFECT_ICON_DIRS:
        if (ROOT / "public" / "img" / "icons" / d / f"{slug}.png").exists():
            return f"{d}/{slug}"
    return None


def effect_label(eff_id: str, gendered: str | None, text: dict[str, str]) -> str:
    """Resolve an EffectUnit's display name. The game keys these a few ways
    (TEXT_EFFECTUNIT_*, the GenderedName, or a CONCEPT alias); take the first
    that resolves, else humanize the zType."""
    for cand in (eff_id,
                 eff_id.replace("EFFECTUNIT_", "TEXT_EFFECTUNIT_"),
                 gendered,
                 (gendered or "").replace("GENDERED_", "")):
        if cand and cand in text:
            return text[cand]
    return token_title(eff_id, "EFFECTUNIT_")


def collect_abilities(effect_ids: list[str], eu_idx: dict[str, ET.Element],
                      text: dict[str, str]) -> list[dict]:
    """Every aeEffectUnit a unit carries, as a named ability (Disarm, Rout,
    Testudo, …). These are the signature unique-unit specials — distinct from
    the numeric `counters` (stat modifiers) collect_counter_lines pulls. Both
    are derived from the same EffectUnits; abilities keeps the human label so
    the catalog pages can show what a unit actually *does*, not just its
    damage math."""
    out: list[dict] = []
    for eid in effect_ids:
        e = eu_idx.get(eid)
        gendered = e.findtext("GenderedName") if e is not None else None
        icon_tok = (e.findtext("zIconName") if e is not None else None) or eid
        out.append({
            "id": eid,
            "label": effect_label(eid, gendered, text),
            "icon": effect_icon_path(icon_tok),
        })
    return out


# Culture-tier gating for unique units (they have no TechPrereq — a nation
# unlocks them at a Culture level instead). Steppe Rider has no CulturePrereq
# and no building gate: a true turn-one unique, surfaced as "Initial". The
# D'mt Warrior also has no CulturePrereq but DOES need a Stronghold, so it is
# gated by improvement instead (handled below) — not "from start".
ERA_BY_CULTURE = {
    "":                   {"order": 1, "label": "Initial"},
    "CULTURE_WEAK":       {"order": 1, "label": "Weak"},
    "CULTURE_DEVELOPING": {"order": 2, "label": "Developing"},
    "CULTURE_STRONG":     {"order": 3, "label": "Strong"},
    "CULTURE_LEGENDARY":  {"order": 4, "label": "Legendary"},
}

# DLC tag → short source label, mirroring build_wonders.py.
SOURCE_LABEL = {
    "":                     "Base game",
    "WONDERS_DYNASTIES":    "Wonders & Dynasties",
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus",
    "SEARCH_AND_PROGRESS":  "Search & Progress",
    "BEHIND_THE_THRONE":    "Behind the Throne",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def token_title(token: str, prefix: str = "") -> str:
    """NATION_YUEZHI → Yuezhi, TECH_LAND_CONSOLIDATION → Land Consolidation."""
    if not token:
        return ""
    return token.replace(prefix, "", 1).replace("_", " ").title() if prefix else token.replace("_", " ").title()


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

    # Improvement display names, for units gated behind a city building
    # (ImprovementPrereq) or obsoleted by one (ImprovementObsolete):
    # GARRISON_2 → Stronghold, GARRISON_3 → Citadel.
    imp_name: dict[str, str] = {}
    for ie in parse("improvement.xml").findall("Entry"):
        iz = ie.findtext("zType") or ""
        if iz:
            imp_name[iz] = text.get(ie.findtext("Name") or "", token_title(iz, "IMPROVEMENT_"))

    units: list[dict] = []
    for entry in parse("unit.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt or not zt.startswith("UNIT_"):
            continue

        name_key = entry.findtext("Name") or ""
        zt_name = zt.replace("UNIT_", "").replace("_", " ").title()
        name = text.get(name_key, zt_name)
        # Religion disciples carry a parameterized name ("{UNIT-RELIGION,1}
        # Disciple") that the game fills in per religion at runtime. The zType
        # already names the religion (UNIT_BUDDHISM_DISCIPLE), so fall back to
        # it whenever the text still has an unresolved {…} template.
        if "{" in name:
            name = zt_name

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

        # XML-derived counter modifiers + named special abilities
        counters = collect_counter_lines(effect_ids, eu_idx)
        abilities = collect_abilities(effect_ids, eu_idx, text)

        imp_prereq = entry.findtext("ImprovementPrereq") or ""
        imp_obsolete = entry.findtext("ImprovementObsolete") or ""

        # Classification axis used by the Units / Unique Units pages:
        #   unique  → has a NationPrereq (nation-only build; wins even if the
        #             unit also carries UNITTRAIT_TRIBAL, e.g. Yuezhi Steppe Rider)
        #   tribal  → carries UNITTRAIT_TRIBAL and no nation gate (barbarian/tribe)
        #   normal  → everything else (the roster any nation can build)
        nation_prereq = entry.findtext("NationPrereq") or ""
        is_tribal = "UNITTRAIT_TRIBAL" in traits_set
        if nation_prereq:
            category = "unique"
        elif is_tribal:
            category = "tribal"
        else:
            category = "normal"

        # Unique units gate on Culture tier, not tech (TechPrereq is empty).
        # Exception: a unit with no CulturePrereq but an ImprovementPrereq is
        # gated by that building, not "from start" — label it by the building
        # (e.g. the D'mt Warrior needs a Stronghold). Order it next to the
        # Developing/Strong base tiers that share the same Garrison level.
        culture = entry.findtext("CulturePrereq") or ""
        if nation_prereq and not culture and imp_prereq:
            order = 3 if imp_prereq.endswith("GARRISON_3") else 2
            era = {"order": order,
                   "label": imp_name.get(imp_prereq, token_title(imp_prereq, "IMPROVEMENT_"))}
        else:
            era = ERA_BY_CULTURE.get(culture, {"order": 0, "label": token_title(culture, "CULTURE_")})
        dlc = entry.findtext("GameContentRequired") or ""

        units.append({
            "id": zt,
            "slug": zt.replace("UNIT_", "").lower(),
            "name": name,
            "isCombat": is_combat_unit(entry),
            "category": category,
            "isTribal": is_tribal,
            "culturePrereq": culture,
            "era": era["label"] if nation_prereq else "",
            "eraOrder": era["order"] if nation_prereq else 0,
            "nationLabel": token_title(nation_prereq, "NATION_"),
            "improvementPrereq": imp_prereq,
            "improvementPrereqLabel": imp_name.get(imp_prereq, "") if imp_prereq else "",
            "improvementObsolete": imp_obsolete,
            "improvementObsoleteLabel": imp_name.get(imp_obsolete, "") if imp_obsolete else "",
            "techLabel": token_title(entry.findtext("TechPrereq") or "", "TECH_"),
            "source": SOURCE_LABEL.get(dlc, token_title(dlc) if dlc else "Base game"),
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
            "abilities": abilities,
            "gameContent": entry.findtext("GameContentRequired") or "",
        })

    units.sort(key=lambda u: (not u["isCombat"], u["primaryLabel"] or "z", u["strength"], u["slug"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(units, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(units)} units")
    return 0


if __name__ == "__main__":
    sys.exit(main())
