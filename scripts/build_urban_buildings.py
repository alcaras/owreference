#!/usr/bin/env python3
"""
Build src/data/urban_improvements.json from improvement.xml + improvementClass.xml.

Picks every improvement where bUrban=1 (city-tile structures), excluding
shrines (their own page), holy-city placeholders, and the bonus/permanent
template entries. Resolves tech prereq via the class, culture prereq from
the improvement, yield cost, specialist slot, ongoing city effect (via
the humanizer), terrain validity, and restrictions like "max 2/city".
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_city, fmt_decimal, yield_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "urban_improvements.json"
IMG_DIR = ROOT / "public" / "img" / "icons" / "improvements"

# Extracted improvement art is keyed by the building's display name, not its
# class (Baths tiers ship as cold/warm/heated_baths, Theater tiers as
# theater/odeon/amphitheater). A few names don't slugify onto their file —
# patch those by hand.
ICON_ALIASES = {"ministry": "ministries"}


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def resolve_icon(name: str, ztype: str) -> str:
    """name-slug → id-slug → alias. Returns site path or '' if no art."""
    name_slug = slugify(name)
    id_slug = ztype.replace("IMPROVEMENT_", "").lower()
    for cand in (name_slug, id_slug, ICON_ALIASES.get(name_slug, "")):
        if cand and (IMG_DIR / f"{cand}.png").exists():
            return f"img/icons/improvements/{cand}.png"
    return ""


def load_text(*filenames: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").split("~")[0].strip()
            if k:
                out[k] = en
    return out


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def render_yield_pairs(parent: ET.Element, tag: str, divide: bool = True, *, suffix: str = "", as_cost: bool = False) -> list[str]:
    out: list[str] = []
    for pair in parent.findall(f"{tag}/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        raw = int(pair.findtext("iValue") or "0")
        v = raw / 10 if divide else raw
        if as_cost:
            # Build costs are RAW integers — the game's getBuildCost returns
            # maiYieldCost as-is, displayed with no YIELDS_MULTIPLIER divisor
            # (unlike per-turn rates). Render absolute, no leading +.
            out.append(f"{abs(raw)} {y}{suffix}")
        else:
            out.append(f"{fmt_decimal(v)} {y}{suffix}")
    return out


def fmt_terrain(token: str) -> str:
    s = (token or "").replace("TERRAIN_TARGET_", "").replace("TERRAIN_", "")
    return s.replace("_", " ").title() if s else ""


def main() -> int:
    text_imp = load_text("text-improvement.xml", "text-improvementClass.xml", "text-infos.xml")
    text_specialist = load_text("text-infos.xml")
    indexes = load_xml_indexes(XML_DIR)

    # Class → TechPrereq + class display name
    class_root = parse("improvementClass.xml")
    class_index: dict[str, ET.Element] = {
        e.findtext("zType"): e for e in class_root.findall("Entry") if e.findtext("zType")
    }

    imp_root = parse("improvement.xml")
    items: list[dict] = []

    for e in imp_root.findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        if (e.findtext("bUrban") or "0") != "1":
            continue
        cls = e.findtext("Class") or ""
        # Exclude shrines (own page), monasteries / religious buildings, holy sites
        if cls in {"IMPROVEMENTCLASS_SHRINE", "IMPROVEMENTCLASS_MONASTERY",
                   "IMPROVEMENTCLASS_TEMPLE", "IMPROVEMENTCLASS_CATHEDRAL",
                   "IMPROVEMENTCLASS_HOLY_SITE", "IMPROVEMENTCLASS_ALTAR_ATEN",
                   "IMPROVEMENTCLASS_CULT", "IMPROVEMENTCLASS_KUSHITE_PYRAMIDS",
                   "IMPROVEMENTCLASS_AKSUM_STELE"}:
            continue
        # Exclude permanent / map-only placeholders
        if (e.findtext("bWonder") or "0") == "1":
            continue
        # Skip stuff like IMPROVEMENT_ANCIENT_RUINS, IMPROVEMENT_VILLAGE/TOWN (no bBuild, just upgrades)
        if (e.findtext("bBuild") or "0") != "1":
            # Permit village/town/hamlet upgrade chain only if they have Specialist slots — they do
            continue

        name = text_imp.get(e.findtext("Name") or "", zt.replace("IMPROVEMENT_", "").replace("_", " ").title())

        # Tech prereq — primarily from class
        tech_id = ""
        cls_entry = class_index.get(cls)
        if cls_entry is not None:
            tech_id = cls_entry.findtext("TechPrereq") or ""
        # Per-entry tech prereq overrides (rare)
        tech_id = e.findtext("TechPrereq") or tech_id

        culture_prereq = e.findtext("CulturePrereq") or ""
        family_prereq = e.findtext("FamilyPrereq") or ""
        nation_prereq = e.findtext("NationPrereq") or ""
        law_prereq = e.findtext("LawPrereq") or ""

        # Build cost (yields) and build time (own field/column, not
        # mixed into the cost list).
        cost_lines: list[str] = render_yield_pairs(e, "aiYieldCost", as_cost=True)
        bt = e.findtext("iBuildTurns")
        build_turns = int(bt) if bt and bt != "0" else 0

        # Specialist slot
        specialist_id = e.findtext("Specialist") or ""
        specialist_name = ""
        specialist_slug = ""
        if specialist_id:
            spec_name_key = ""
            for s_entry in indexes.get("specialist.xml", {}).values():
                if s_entry.findtext("zType") == specialist_id:
                    spec_name_key = s_entry.findtext("Name") or ""
                    break
            specialist_name = text_specialist.get(spec_name_key, specialist_id.replace("SPECIALIST_", "").replace("_", " ").title())
            # Map to class icon
            class_token = specialist_id.replace("SPECIALIST_", "").lower()
            # Strip trailing _1/_2/_3 (icons are per-class)
            for suffix in ("_1", "_2", "_3"):
                if class_token.endswith(suffix):
                    class_token = class_token[: -len(suffix)]
                    break
            specialist_slug = class_token

        # Direct yield output on the improvement itself (e.g., Hamlet → +10 Money)
        effects: list[str] = []
        effects.extend(render_yield_pairs(e, "aiYieldOutput"))

        # Yield output (ongoing) — from EffectCity if any
        ec_id = e.findtext("EffectCity") or ""
        ec = indexes.get("effectCity.xml", {}).get(ec_id) if ec_id else None
        if ec is not None:
            effects.extend(render_effect_city(ec, per_city=False, indexes=indexes))

        # Adjacent improvement class modifier (e.g., Barracks: +20% Garrison)
        for pair in e.findall("aiAdjacentImprovementClassModifier/Pair"):
            imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENTCLASS_", "").title()
            v = int(pair.findtext("iValue") or "0")
            effects.append(f"{fmt_decimal(v)}% Adjacent {imp}")

        # Unit XP via this building
        for pair in e.findall("aiUnitTraitXP/Pair"):
            trait = (pair.findtext("zIndex") or "").replace("UNITTRAIT_", "").title()
            v = int(pair.findtext("iValue") or "0")
            effects.append(f"+{v} XP for {trait} Units")

        # Specialist XP (officer barracks, etc.)
        for pair in e.findall("aiSpecialistClassXP/Pair"):
            cls_tok = (pair.findtext("zIndex") or "").replace("SPECIALISTCLASS_", "").title()
            v = int(pair.findtext("iValue") or "0")
            effects.append(f"+{v} XP for {cls_tok}")

        # Per-turn upkeep (aiYieldConsumption is a RATE → /10). Its own
        # column, not folded into effects. Value is negative in XML; show
        # the absolute drain.
        upkeep: list[str] = []
        for pair in e.findall("aiYieldConsumption/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = abs(int(pair.findtext("iValue") or "0")) / 10
            vs = f"{v:g}" if v != int(v) else f"{int(v)}"
            upkeep.append(f"{vs} {y}/turn")

        # Terrain validity
        terrain_tokens = [tv.text or "" for tv in e.findall("TerrainValid/zValue") if tv.text]
        terrains = [fmt_terrain(t) for t in terrain_tokens]

        # Restrictions
        restrictions: list[str] = []
        # Placement rule — whether it must follow urban-tile rules or can go
        # anywhere in territory. (All current urban improvements are urban +
        # territory-only, but surface it from XML so it stays honest if a
        # patch adds a free-placement one.)
        if (e.findtext("bUrban") or "0") == "1":
            restrictions.append("Urban tile only")
        elif (e.findtext("bTerritoryOnly") or "0") == "1":
            restrictions.append("Anywhere in own territory")
        max_city = e.findtext("iMaxCityCount")
        if max_city and max_city != "0":
            restrictions.append(f"Max {max_city}/City")
        max_family = e.findtext("iMaxFamilyCount")
        if max_family and max_family != "0":
            restrictions.append(f"Max {max_family}/Family")
        max_player = e.findtext("iMaxPlayerCount")
        if max_player and max_player != "0":
            restrictions.append(f"Max {max_player}/Player")
        if (e.findtext("bRequiresBorder") or "0") == "1":
            restrictions.append("Requires border")
        if (e.findtext("bFreshWaterSource") or "0") == "1":
            restrictions.append("Provides fresh water")
        if (e.findtext("bAqueduct") or "0") == "1":
            restrictions.append("Aqueduct segment")

        # Upgrade target (Library_1 → Library_2 etc.)
        upgrade = e.findtext("UpgradeImprovement") or ""
        upgrade_name = ""
        if upgrade:
            up_entry = next((x for x in imp_root.findall("Entry") if x.findtext("zType") == upgrade), None)
            if up_entry is not None:
                upgrade_name = text_imp.get(up_entry.findtext("Name") or "", upgrade.replace("IMPROVEMENT_", "").replace("_", " ").title())

        # Replaces (ImprovementPrereq)
        prereq_imp = e.findtext("ImprovementPrereq") or ""
        prereq_imp_name = ""
        if prereq_imp:
            pr_entry = next((x for x in imp_root.findall("Entry") if x.findtext("zType") == prereq_imp), None)
            if pr_entry is not None:
                prereq_imp_name = text_imp.get(pr_entry.findtext("Name") or "", prereq_imp.replace("IMPROVEMENT_", "").replace("_", " ").title())

        # Resolve tech name
        tech_name = ""
        if tech_id:
            tech_entry = indexes.get("tech.xml", {}).get(tech_id)
            tech_name_key = tech_entry.findtext("Name") if tech_entry is not None else ""
            tech_name = text_imp.get(tech_name_key or "", tech_id.replace("TECH_", "").replace("_", " ").title())

        slug = zt.replace("IMPROVEMENT_", "").lower()
        items.append({
            "id": zt,
            "slug": slug,
            "name": name,
            "icon": resolve_icon(name, zt),
            "class": cls.replace("IMPROVEMENTCLASS_", "").title() if cls else "",
            "classId": cls,
            "tech": {
                "id": tech_id,
                "slug": tech_id.replace("TECH_", "").lower() if tech_id else "",
                "name": tech_name,
            } if tech_id else None,
            "culturePrereq": culture_prereq.replace("CULTURE_", "").title() if culture_prereq else "",
            "familyPrereq": family_prereq.replace("FAMILY_", "").replace("_", " ").title() if family_prereq else "",
            "nationPrereq": nation_prereq.replace("NATION_", "").title() if nation_prereq else "",
            "lawPrereq": law_prereq.replace("LAW_", "").replace("_", " ").title() if law_prereq else "",
            "cost": cost_lines,
            "buildTurns": build_turns,
            "upkeep": upkeep,
            "specialist": {
                "id": specialist_id,
                "slug": specialist_slug,
                "name": specialist_name,
            } if specialist_id else None,
            "effects": effects,
            "terrains": terrains,
            "restrictions": restrictions,
            "upgradesTo": upgrade_name,
            "replaces": prereq_imp_name,
        })

    # Sort by class, then name
    # Default order: by tech-unlock progression (tech.xml file order ≈
    # research order), then class, then name. Users can re-sort any column.
    tech_order = {
        t.findtext("zType"): i
        for i, t in enumerate(parse("tech.xml").findall("Entry"))
        if t.findtext("zType")
    }
    items.sort(key=lambda x: (
        tech_order.get((x.get("tech") or {}).get("id"), -1),
        x["class"], x["name"],
    ))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(items)} urban improvements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
