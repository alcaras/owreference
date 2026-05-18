#!/usr/bin/env python3
"""
Build src/data/rural_improvements.json from improvement.xml + improvementClass.xml.

Picks every improvement with bBuild=1 that is NOT urban and NOT a shrine.
For each: name, tech prereq (via class), build cost (yield + turns),
direct yield output, terrain validity, adjacency bonuses (improvement class,
terrain, resource, fresh-water), and specialist slot.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, fmt_decimal, yield_name, condition_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "rural_improvements.json"
IMG_DIR = ROOT / "public" / "img" / "icons" / "improvements"


def resolve_icon(ztype: str) -> str:
    """Rural improvement art is keyed by class slug (farm, mine, …)."""
    slug = ztype.replace("IMPROVEMENT_", "").lower()
    if slug and (IMG_DIR / f"{slug}.png").exists():
        return f"img/icons/improvements/{slug}.png"
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


def fmt_terrain(token: str) -> str:
    s = (token or "").replace("TERRAIN_TARGET_", "").replace("TERRAIN_", "")
    return s.replace("_", " ").title() if s else ""


def fmt_class(token: str) -> str:
    return (token or "").replace("IMPROVEMENTCLASS_", "").title()


def fmt_resource(token: str) -> str:
    return (token or "").replace("RESOURCE_", "").replace("_", " ").title()


def cost_pairs(parent: ET.Element, tag: str) -> list[str]:
    """Render yield costs as 'N Yield' (absolute, no leading sign).

    Build costs are RAW integers — the game's getBuildCost returns
    maiYieldCost as-is and displays it with no YIELDS_MULTIPLIER divisor
    (unlike per-turn yield rates, which are /10). Do NOT divide here."""
    out: list[str] = []
    for pair in parent.findall(f"{tag}/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = abs(int(pair.findtext("iValue") or "0"))
        out.append(f"{v} {y}")
    return out


def output_pairs(parent: ET.Element, tag: str, *, suffix: str = "") -> list[str]:
    out: list[str] = []
    for pair in parent.findall(f"{tag}/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"{fmt_decimal(v)} {y}{suffix}")
    return out


def main() -> int:
    text_imp = load_text("text-improvement.xml", "text-improvementClass.xml", "text-infos.xml")
    indexes = load_xml_indexes(XML_DIR)

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
        if (e.findtext("bBuild") or "0") != "1":
            continue
        if (e.findtext("bUrban") or "0") == "1":
            continue
        cls = e.findtext("Class") or ""
        if cls in {"IMPROVEMENTCLASS_SHRINE", "IMPROVEMENTCLASS_MONASTERY",
                   "IMPROVEMENTCLASS_TEMPLE", "IMPROVEMENTCLASS_CATHEDRAL",
                   "IMPROVEMENTCLASS_HOLY_SITE", "IMPROVEMENTCLASS_ALTAR_ATEN",
                   "IMPROVEMENTCLASS_CULT"}:
            continue
        if (e.findtext("bWonder") or "0") == "1":
            continue

        name = text_imp.get(e.findtext("Name") or "", zt.replace("IMPROVEMENT_", "").replace("_", " ").title())

        # Tech prereq via class
        tech_id = ""
        cls_entry = class_index.get(cls)
        if cls_entry is not None:
            tech_id = cls_entry.findtext("TechPrereq") or ""
        tech_id = e.findtext("TechPrereq") or tech_id

        tech_name = ""
        if tech_id:
            tech_entry = indexes.get("tech.xml", {}).get(tech_id)
            tech_name_key = tech_entry.findtext("Name") if tech_entry is not None else ""
            tech_name = text_imp.get(tech_name_key or "", tech_id.replace("TECH_", "").replace("_", " ").title())

        # Build cost: yield cost + turns
        cost_lines = cost_pairs(e, "aiYieldCost")
        bt = e.findtext("iBuildTurns")
        if bt and bt != "0":
            cost_lines.append(f"{bt} turns")

        # Output yields (direct)
        output_lines = output_pairs(e, "aiYieldOutput")

        # Per-turn upkeep (aiYieldConsumption is a RATE → /10; negative in
        # XML, show absolute drain). Own column.
        upkeep_lines: list[str] = []
        for pair in e.findall("aiYieldConsumption/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = abs(int(pair.findtext("iValue") or "0")) / 10
            vs = f"{v:g}" if v != int(v) else f"{int(v)}"
            upkeep_lines.append(f"{vs} {y}/turn")

        # Specialist slot
        specialist_id = e.findtext("Specialist") or ""
        specialist_name = ""
        specialist_slug = ""
        if specialist_id:
            spec_entry = indexes.get("specialist.xml", {}).get(specialist_id)
            spec_name_key = spec_entry.findtext("Name") if spec_entry is not None else ""
            specialist_name = text_imp.get(spec_name_key or "", specialist_id.replace("SPECIALIST_", "").replace("_", " ").title())
            specialist_slug = specialist_id.replace("SPECIALIST_", "").lower()
            for suffix in ("_1", "_2", "_3"):
                if specialist_slug.endswith(suffix):
                    specialist_slug = specialist_slug[: -len(suffix)]
                    break

        # Terrain validity
        terrain_tokens = [tv.text or "" for tv in e.findall("TerrainValid/zValue") if tv.text]
        terrains = [fmt_terrain(t) for t in terrain_tokens]
        # River-edge improvements (Watermill) carry no TerrainValid — the
        # requirement is the bRiverValid / bRotateToRiverEdge flags instead.
        if (e.findtext("bRiverValid") or "0") == "1" or (e.findtext("bRotateToRiverEdge") or "0") == "1":
            terrains.append("River")
        if (e.findtext("bCoastalValid") or "0") == "1" or (e.findtext("bCoast") or "0") == "1":
            terrains.append("Coast")
        # Some improvements explicitly exclude a terrain (Watermill: no Hill)
        ti = e.findtext("TerrainInvalid") or ""
        if ti:
            terrains.append(f"not {fmt_terrain(ti)}")

        # Adjacency / yield modifiers
        adjacency: list[str] = []
        # Same-class adjacent improvement modifier
        for pair in e.findall("aiAdjacentImprovementModifier/Pair"):
            imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENT_", "").title()
            v = int(pair.findtext("iValue") or "0")
            adjacency.append(f"{fmt_decimal(v)}% Adjacent {imp}")
        # Adjacent class modifier
        for pair in e.findall("aiAdjacentImprovementClassModifier/Pair"):
            imp = fmt_class(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0")
            adjacency.append(f"{fmt_decimal(v)}% Adjacent {imp}")
        # Adjacent class flat yield bonus
        for pair in e.findall("aaiAdjacentImprovementClassYield/Pair"):
            imp = fmt_class(pair.findtext("zIndex"))
            for sp in pair.findall("SubPair"):
                y = yield_name(sp.findtext("zSubIndex"))
                v = int(sp.findtext("iValue") or "0") / 10
                adjacency.append(f"{fmt_decimal(v)} {y} per adjacent {imp}")
        # Adjacent specific-improvement flat yield bonus
        for pair in e.findall("aaiAdjacentImprovementYield/Pair"):
            imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENT_", "").title()
            for sp in pair.findall("SubPair"):
                y = yield_name(sp.findtext("zSubIndex"))
                v = int(sp.findtext("iValue") or "0") / 10
                adjacency.append(f"{fmt_decimal(v)} {y} per adjacent {imp}")
        # Adjacent resource flat yield
        for pair in e.findall("aiAdjacentResourceYieldOutput/Pair"):
            r = fmt_resource(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0") / 10
            adjacency.append(f"{fmt_decimal(v)} per adjacent {r}")

        # Terrain modifiers
        terrain_mods: list[str] = []
        for pair in e.findall("aaiTerrainYieldOutput/Pair"):
            t = condition_name(pair.findtext("zIndex"))
            for sp in pair.findall("SubPair"):
                y = yield_name(sp.findtext("zSubIndex"))
                v = int(sp.findtext("iValue") or "0") / 10
                terrain_mods.append(f"{fmt_decimal(v)} {y} on {t}")
        for pair in e.findall("aaiTerrainYieldModifier/Pair"):
            t = condition_name(pair.findtext("zIndex"))
            for sp in pair.findall("SubPair"):
                y = yield_name(sp.findtext("zSubIndex"))
                v = int(sp.findtext("iValue") or "0")
                terrain_mods.append(f"{fmt_decimal(v)}% {y} on {t}")
        # Fresh-water yield bonus
        for pair in e.findall("aiYieldFreshWaterModifier/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0")
            terrain_mods.append(f"{fmt_decimal(v)}% {y} on Fresh Water")
        # Height-adjacent (volcano, mountain) modifier
        for pair in e.findall("aaiAdjacentHeightYieldModifier/Pair"):
            t = condition_name(pair.findtext("zIndex"))
            for sp in pair.findall("SubPair"):
                y = yield_name(sp.findtext("zSubIndex"))
                v = int(sp.findtext("iValue") or "0")
                terrain_mods.append(f"{fmt_decimal(v)}% {y} adjacent to {t}")

        # Restrictions
        restrictions: list[str] = []
        max_city = e.findtext("iMaxCityCount")
        if max_city and max_city != "0":
            restrictions.append(f"Max {max_city}/City")
        max_player = e.findtext("iMaxPlayerCount")
        if max_player and max_player != "0":
            restrictions.append(f"Max {max_player}/Player")
        if (e.findtext("bFreshWaterSource") or "0") == "1":
            restrictions.append("Provides fresh water")
        if (e.findtext("bCanal") or "0") == "1":
            restrictions.append("Canal")
        if (e.findtext("bAqueductEndpoint") or "0") == "1":
            restrictions.append("Aqueduct endpoint")

        slug = zt.replace("IMPROVEMENT_", "").lower()
        items.append({
            "id": zt,
            "slug": slug,
            "name": name,
            "icon": resolve_icon(zt),
            "class": fmt_class(cls),
            "classId": cls,
            "tech": {
                "id": tech_id,
                "slug": tech_id.replace("TECH_", "").lower() if tech_id else "",
                "name": tech_name,
            } if tech_id else None,
            "cost": cost_lines,
            "upkeep": upkeep_lines,
            "output": output_lines,
            "specialist": {
                "id": specialist_id,
                "slug": specialist_slug,
                "name": specialist_name,
            } if specialist_id else None,
            "terrains": terrains,
            "adjacency": adjacency,
            "terrainMods": terrain_mods,
            "restrictions": restrictions,
        })

    # Default order: by tech-unlock progression (tech.xml file order ≈
    # research order), then name. Users can re-sort any column.
    tech_order = {
        t.findtext("zType"): i
        for i, t in enumerate(parse("tech.xml").findall("Entry"))
        if t.findtext("zType")
    }
    items.sort(key=lambda x: (
        tech_order.get((x.get("tech") or {}).get("id"), -1),
        x["name"],
    ))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(items)} rural improvements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
