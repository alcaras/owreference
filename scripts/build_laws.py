#!/usr/bin/env python3
"""
Build src/data/laws.json from law.xml + lawClass.xml.

Laws come in pairs at each civic tier — players pick one of two within each
LawClass once they've researched its TechPrereq. Output groups laws by tier
(derived from the tech's iColumn) and by class within each tier.

Succession laws (LAWCLASS_ORDER) are handled separately as a 5-way pick at
game start; we still emit them as a single "Succession" group.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_player, yield_name, fmt_decimal,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "laws.json"

# Hand-curated descriptions for succession laws (no EffectPlayer in XML —
# they only set SuccessionOrder, whose meaning is the rule itself).
SUCCESSION_EFFECTS: dict[str, list[str]] = {
    "LAW_PRIMOGENITURE": ["Heir is the eldest son"],
    "LAW_ULTIMOGENITURE": ["Heir is the youngest son"],
    "LAW_LATERAL":        ["Heir is the eldest sibling, then the eldest son"],
    "LAW_DYNASTIC":       ["Heir is the highest Rated dynastic child"],
    "LAW_SENIORITY":      ["Heir is the eldest dynastic family member"],
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text(*filenames: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for entry in ET.parse(p).getroot().findall("Entry"):
            z = entry.findtext("zType") or ""
            en = ((entry.findtext("en-US") or "").split("~")[0]).strip()
            if z and en and z not in out:
                out[z] = en
    return out


def render_upkeep(ep_upkeep_id: str, indexes: dict) -> list[str]:
    """Render an EFFECTPLAYER_UPKEEP_* entry's aiYieldUpkeep pairs.

    Per the game source (Player.getYieldUpkeepNet), the upkeep value is
    multiplied by the number of cities, so it's a per-city per-turn cost.
    Values are 10× display (e.g. -10 CIVICS → "-1 Civics/City").
    """
    ep = indexes.get("effectPlayer.xml", {}).get(ep_upkeep_id)
    if ep is None:
        return []
    out: list[str] = []
    for pair in ep.findall("aiYieldUpkeep/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        if v:
            out.append(f"{fmt_decimal(v)} {y}/City")
    return out


def load_law_opinions(text_infos: dict[str, str]) -> dict[str, list[dict]]:
    """Invert aiLawOpinion from familyClass.xml and trait.xml (archetypes).

    Returns LAW_X → [{group, label, value}], families first, then archetypes,
    each alphabetical by label. Opinion values come straight from the XML
    (currently all +20).
    """
    by_law: dict[str, list[dict]] = defaultdict(list)

    # Family classes: Name → TEXT_FAMILYCLASS_* lives in text-infos.xml
    for e in parse("familyClass.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        label = text_infos.get(e.findtext("Name") or "",
                               zt.replace("FAMILYCLASS_", "").replace("_", " ").title())
        for pair in e.findall("aiLawOpinion/Pair"):
            law_id = pair.findtext("zIndex") or ""
            val = int(pair.findtext("iValue") or "0")
            if law_id and val:
                by_law[law_id].append({"group": "family", "label": label, "value": val})

    # Archetype traits: no Name field — derive from zType (TRAIT_HERO_ARCHETYPE → Hero)
    for e in parse("trait.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        label = zt.replace("TRAIT_", "").replace("_ARCHETYPE", "").replace("_", " ").title()
        for pair in e.findall("aiLawOpinion/Pair"):
            law_id = pair.findtext("zIndex") or ""
            val = int(pair.findtext("iValue") or "0")
            if law_id and val:
                by_law[law_id].append({"group": "archetype", "label": label, "value": val})

    group_rank = {"family": 0, "archetype": 1}
    for law_id in by_law:
        by_law[law_id].sort(key=lambda o: (group_rank[o["group"]], o["label"]))
    return by_law


def main() -> int:
    text_law = load_text("text-law.xml")
    text_tech = load_text("text-tech.xml")
    text_infos = load_text("text-infos.xml")

    # Map TECH_X → iColumn (0..7). Used to derive civic tier.
    tech_col: dict[str, int] = {}
    tech_name: dict[str, str] = {}
    for e in parse("tech.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        col = e.findtext("iColumn")
        if zt and col is not None and col != "":
            try:
                tech_col[zt] = int(col)
            except ValueError:
                pass
        if zt:
            tech_name[zt] = text_tech.get(e.findtext("Name") or "",
                                          zt.replace("TECH_", "").replace("_", " ").title())

    indexes = load_xml_indexes(XML_DIR)
    law_opinions = load_law_opinions(text_infos)

    # Read every LawClass with its TechPrereq
    classes: dict[str, dict] = {}
    for e in parse("lawClass.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        tech_prereq = (e.findtext("TechPrereq") or "").strip()
        starting = (e.findtext("StartingLaw") or "").strip()
        is_succession = (e.findtext("bSuccession") or "0") == "1"
        col = tech_col.get(tech_prereq, -1) if tech_prereq else -1
        classes[zt] = {
            "id": zt,
            "techPrereq": tech_prereq,
            "techPrereqLabel": tech_name.get(tech_prereq, ""),
            "techColumn": col,
            "startingLaw": starting,
            "isSuccession": is_succession,
        }

    # Read each law entry
    laws_by_class: dict[str, list[dict]] = defaultdict(list)
    for e in parse("law.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        cls = e.findtext("LawClass") or ""
        if not cls:
            continue
        name_key = e.findtext("Name") or ""
        name = text_law.get(name_key, zt.replace("LAW_", "").replace("_", " ").title())
        cost = int(e.findtext("iCostBase") or "0")
        switch = int(e.findtext("iSwitchCostBase") or "0")
        per_change = int(e.findtext("iCostPerChange") or "0")
        succession_order = (e.findtext("SuccessionOrder") or "").replace("SUCCESSIONORDER_", "").title()

        ep_id = (e.findtext("EffectPlayer") or "").strip()
        effects = render_effect_player(ep_id, indexes) if ep_id else []
        # Fallback for succession laws (no EffectPlayer)
        if not effects and zt in SUCCESSION_EFFECTS:
            effects = SUCCESSION_EFFECTS[zt]

        # Per-city per-turn upkeep (EFFECTPLAYER_UPKEEP_*)
        ep_upkeep_id = (e.findtext("EffectPlayerUpkeep") or "").strip()
        upkeep = render_upkeep(ep_upkeep_id, indexes) if ep_upkeep_id else []

        laws_by_class[cls].append({
            "id": zt,
            "slug": zt.replace("LAW_", "").lower(),
            "name": name,
            "cost": cost,
            "switchCost": switch,
            "perChangeCost": per_change,
            "successionOrder": succession_order,
            "effects": effects,
            "upkeep": upkeep,
            "opinions": law_opinions.get(zt, []),
        })

    # Build the grouped output: list of groups, each {tier, label, classes: [{class, laws}]}
    # Tier ordering derived from tech iColumn. Succession is tier 0.
    # Within a tier, classes ordered by the canonical xlsx layout.

    # Canonical tier groupings (matches the spreadsheet's "Tier 1..5" tabs)
    TIER_LAYOUT: list[dict] = [
        {"tier": 0, "label": "Succession (Order)", "classes": ["LAWCLASS_ORDER"]},
        {"tier": 1, "label": "Tier 1 (early civic techs)",
         "classes": ["LAWCLASS_EPICS_EXPLORATION",
                     "LAWCLASS_SLAVERY_FREEDOM",
                     "LAWCLASS_CENTRALIZATION_VASSALAGE"]},
        {"tier": 2, "label": "Tier 2",
         "classes": ["LAWCLASS_TYRANNY_CONSTITUTION",
                     "LAWCLASS_COLONIES_SERFDOM",
                     "LAWCLASS_MONOTHEISM_POLYTHEISM"]},
        {"tier": 3, "label": "Tier 3",
         "classes": ["LAWCLASS_DIVINE_RULE_LEGAL_CODE",
                     "LAWCLASS_TOLERANCE_ORTHODOXY",
                     "LAWCLASS_PHILOSOPHY_ENGINEERING"]},
        {"tier": 4, "label": "Tier 4",
         "classes": ["LAWCLASS_PROFESSIONAL_ARMY_VOLUNTEERS",
                     "LAWCLASS_ICONOGRAPHY_CALLIGRAPHY",
                     "LAWCLASS_PILGRIMAGE_HOLY_WAR"]},
        {"tier": 5, "label": "Tier 5 (late civic techs)",
         "classes": ["LAWCLASS_GUILDS_ELITES",
                     "LAWCLASS_AUTARKY_TRADE_LEAGUE",
                     "LAWCLASS_COIN_DEBASEMENT_MONETARY_REFORM"]},
    ]

    groups: list[dict] = []
    seen_classes: set[str] = set()
    for tier in TIER_LAYOUT:
        out_classes: list[dict] = []
        for cls_id in tier["classes"]:
            if cls_id not in classes:
                continue
            seen_classes.add(cls_id)
            cls_info = classes[cls_id]
            laws_in_class = laws_by_class.get(cls_id, [])
            # Sort: starting law first (for succession), otherwise XML order is fine
            if cls_info["isSuccession"] and cls_info["startingLaw"]:
                laws_in_class = sorted(
                    laws_in_class,
                    key=lambda l: 0 if l["id"] == cls_info["startingLaw"] else 1,
                )
            out_classes.append({
                "id": cls_id,
                "slug": cls_id.replace("LAWCLASS_", "").lower(),
                "techPrereq": cls_info["techPrereq"],
                "techPrereqLabel": cls_info["techPrereqLabel"],
                "isSuccession": cls_info["isSuccession"],
                "laws": laws_in_class,
            })
        groups.append({
            "tier": tier["tier"],
            "label": tier["label"],
            "classes": out_classes,
        })

    # Stragglers (DLC adds a new lawclass?): tack onto the end
    for cls_id, cls_info in sorted(classes.items()):
        if cls_id in seen_classes:
            continue
        groups[-1]["classes"].append({
            "id": cls_id,
            "slug": cls_id.replace("LAWCLASS_", "").lower(),
            "techPrereq": cls_info["techPrereq"],
            "techPrereqLabel": cls_info["techPrereqLabel"],
            "isSuccession": cls_info["isSuccession"],
            "laws": laws_by_class.get(cls_id, []),
        })

    n_laws = sum(len(c["laws"]) for g in groups for c in g["classes"])
    n_pairs = sum(1 for g in groups for c in g["classes"] if not c["isSuccession"])

    payload = {"groups": groups, "totalLaws": n_laws, "totalPairs": n_pairs}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {n_laws} laws across {n_pairs} pair-classes (+1 succession class)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
