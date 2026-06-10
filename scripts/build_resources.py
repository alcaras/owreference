#!/usr/bin/env python3
"""
Build src/data/resources.json from resource.xml + its cross-references.

Per resource:
- name (text-*.xml), icon (zIconName → public/img/icons/resources/*.png), DLC
- category: Luxury / Strategic / Bonus — all derived, the XML has no flag:
    * Luxury    = appears in any effectCity <aeLuxuryResources> (the union of
                  worked-luxury markers + GIVE_* project effects covers all 24)
    * Strategic = a unit's EffectCityPrereq points at the resource's
                  "city is working this" marker (Horse / Camel / Elephant)
    * Bonus     = everything else
- tile yields: aiYieldNoImprovement (per-turn rate, /10 for display),
  aiYieldReveal (one-time stockpile near closest city, RAW — the game shows
  these via processYieldWholeTile / no YIELDS_MULTIPLIER divide)
- harvest: aiYieldHarvest (RAW for the same reason) + regrow roll
- worked by: improvementClass.abResourceValid → base improvement of that
  class; worked yields from improvementClass.aaiResourceYieldOutput (/10);
  improvement.abNoBaseOutput marks "replaces the improvement's base yield"
- spawn: abTerrainValid/abHeightValid/abVegetationValid + latitude band +
  iProbThousand / iMinDist / iMinPerPlayer; empty terrain list = the
  resource never spawns on the map (events / trade / tech cards only)
- effects: luxury payload (EFFECTCITY_LUXURY via render_effect_city), family
  favorites (familyClass.aeLuxuryEffectCity), luxury-producing specialist
  (specialistClass.aeResourceCityEffect → bLuxury), Precious marker
  (EffectCityUnlock → EFFECTCITY_RESOURCE_PRECIOUS), unit unlocks
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_city, fmt_decimal, yield_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "resources.json"
IMG_DIR = ROOT / "public" / "img" / "icons" / "resources"

DLC_NAMES = {
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus",
    "SACRED_AND_PROFANE": "Sacred and Profane",
    "WONDERS_AND_DYNASTIES": "Wonders and Dynasties",
    "BEHIND_THE_THRONE": "Behind the Throne",
    "EDGE_OF_THE_ICE": "Edge of the Ice",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def token_words(token: str, prefix: str) -> str:
    return token.replace(prefix, "").replace("_", " ").title()


def resolve_icon(entry: ET.Element, ztype: str) -> str:
    """resource.xml's zIconName redirects shared art (MARBLE→STONE, ORE→IRON,
    IVORY/TEA/… → GENERIC_LUXURY). Follow it, then fall back to the id."""
    for cand in (entry.findtext("zIconName") or "", ztype):
        slug = cand.replace("RESOURCE_", "").lower()
        if slug and (IMG_DIR / f"{slug}.png").exists():
            return f"img/icons/resources/{slug}.png"
    return ""


def yield_pairs(entry: ET.Element, tag: str, *, divide: bool) -> list[str]:
    out: list[str] = []
    for pair in entry.findall(f"{tag}/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v / 10 if divide else v)} {y}")
    return out


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text = indexes["__text__"]

    res_root = parse("resource.xml")
    effect_city = indexes["effectCity.xml"]

    # ── Luxury set: union of every aeLuxuryResources list in effectCity.xml.
    # (City.changeEffectCityCount → player().changeLuxuryCount; covers both
    # the worked-marker luxuries and the GIVE_* event/project luxuries.)
    luxuries: set[str] = set()
    for entry in effect_city.values():
        for zv in entry.findall("aeLuxuryResources/zValue"):
            if zv.text:
                luxuries.add(zv.text)

    # ── Worked-by: improvementClass.abResourceValid; pick the class's base
    # buildable improvement from improvement.xml (first bBuild entry of class).
    imp_root = parse("improvement.xml")
    class_to_improvement: dict[str, str] = {}
    no_base_output: dict[str, set[str]] = {}  # resource -> improvement ids
    for e in imp_root.findall("Entry"):
        zt = e.findtext("zType") or ""
        cls = e.findtext("Class") or ""
        if zt and cls and (e.findtext("bBuild") or "0") == "1":
            class_to_improvement.setdefault(cls, zt)
        for pair in e.findall("abNoBaseOutput/Pair"):
            if pair.findtext("bValue") == "1":
                r = pair.findtext("zIndex") or ""
                no_base_output.setdefault(r, set()).add(zt)

    cls_root = parse("improvementClass.xml")
    worked_by: dict[str, dict] = {}  # resource -> {classId, improvementId, yields, effectCity}
    for e in cls_root.findall("Entry"):
        cls = e.findtext("zType") or ""
        if not cls:
            continue
        valid = {p.findtext("zIndex") for p in e.findall("abResourceValid/Pair")
                 if p.findtext("bValue") == "1"}
        if not valid:
            continue
        # per-resource worked yields (rates, /10)
        ylines: dict[str, list[str]] = {}
        for pair in e.findall("aaiResourceYieldOutput/Pair"):
            r = pair.findtext("zIndex") or ""
            lines = []
            for sp in pair.findall("SubPair"):
                y = yield_name(sp.findtext("zSubIndex"))
                v = int(sp.findtext("iValue") or "0") / 10
                lines.append(f"{fmt_decimal(v)} {y}")
            ylines[r] = lines
        # worked marker effectCity (unit prereqs hang off these)
        markers: dict[str, str] = {}
        for pair in e.findall("aeResourceCityEffect/Pair"):
            markers[pair.findtext("zIndex") or ""] = pair.findtext("zValue") or ""
        for r in valid:
            imp_id = class_to_improvement.get(cls, "")
            worked_by[r] = {
                "classId": cls,
                "improvementId": imp_id,
                "yields": ylines.get(r, []),
                "marker": markers.get(r, ""),
                "replacesBase": imp_id in no_base_output.get(r, set()),
            }

    # ── Strategic: units gated on a resource's worked marker.
    marker_to_resource = {v["marker"]: r for r, v in worked_by.items() if v["marker"]}
    units_by_resource: dict[str, list[str]] = {}
    for e in parse("unit.xml").findall("Entry"):
        pre = e.findtext("EffectCityPrereq") or ""
        r = marker_to_resource.get(pre)
        if r:
            uname = text.get(e.findtext("Name") or "",
                             token_words(e.findtext("zType") or "", "UNIT_"))
            if uname not in units_by_resource.setdefault(r, []):
                units_by_resource[r].append(uname)

    # ── Luxury payloads.
    # Generic city effect (every luxury assigned to a city):
    lux_entry = effect_city["EFFECTCITY_LUXURY"]
    lux_generic = render_effect_city(lux_entry, per_city=False, indexes=indexes)
    # render_effect_city doesn't cover aaiImprovementYield (the Market-tier-3
    # culture kicker); add it here rather than touching the shared humanizer.
    for pair in lux_entry.findall("aaiImprovementYield/Pair"):
        imp_id = pair.findtext("zIndex") or ""
        imp_entry = indexes["improvement.xml"].get(imp_id)
        imp_name = text.get(imp_entry.findtext("Name") or "", "") if imp_entry is not None else ""
        imp_name = imp_name or token_words(imp_id, "IMPROVEMENT_")
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0") / 10
            lux_generic.append(f"{fmt_decimal(v)} {y} on {imp_name}")
    # Family-class favorites (familyClass.aeLuxuryEffectCity → extra effect):
    favorites: dict[str, list[tuple[str, list[str]]]] = {}
    for e in parse("familyClass.xml").findall("Entry"):
        cls_name = text.get(e.findtext("Name") or "",
                            token_words(e.findtext("zType") or "", "FAMILYCLASS_"))
        for pair in e.findall("aeLuxuryEffectCity/Pair"):
            r = pair.findtext("zIndex") or ""
            eff_id = pair.findtext("zValue") or ""
            eff = effect_city.get(eff_id)
            lines = render_effect_city(eff, per_city=False, indexes=indexes) if eff is not None else []
            favorites.setdefault(r, []).append((cls_name, lines))
    # Which specialist's work turns the map resource into a tradeable luxury:
    lux_specialist: dict[str, str] = {}
    for e in parse("specialistClass.xml").findall("Entry"):
        spec_name = text.get(e.findtext("Name") or "",
                             token_words(e.findtext("zType") or "", "SPECIALISTCLASS_"))
        for pair in e.findall("aeResourceCityEffect/Pair"):
            eff = effect_city.get(pair.findtext("zValue") or "")
            if eff is not None and eff.findtext("bLuxury") == "1":
                lux_specialist[pair.findtext("zIndex") or ""] = spec_name

    # ── Precious markers (EffectCityUnlock → EFFECTCITY_RESOURCE_PRECIOUS).
    precious: set[str] = set()
    for r, v in worked_by.items():
        eff = effect_city.get(v["marker"])
        if eff is not None and eff.findtext("EffectCityUnlock") == "EFFECTCITY_RESOURCE_PRECIOUS":
            precious.add(r)

    # ── Assemble.
    items: list[dict] = []
    for e in res_root.findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        slug = zt.replace("RESOURCE_", "").lower()
        name = text.get(e.findtext("Name") or "", token_words(zt, "RESOURCE_"))

        is_lux = zt in luxuries
        is_strategic = zt in units_by_resource
        category = "Strategic" if is_strategic else ("Luxury" if is_lux else "Bonus")

        # Spawn placement
        terrains = [token_words(p.findtext("zIndex") or "", "TERRAIN_")
                    for p in e.findall("abTerrainValid/Pair") if p.findtext("bValue") == "1"]
        heights = [token_words(p.findtext("zIndex") or "", "HEIGHT_")
                   for p in e.findall("abHeightValid/Pair") if p.findtext("bValue") == "1"]
        vegetation = [token_words(p.findtext("zIndex") or "", "VEGETATION_")
                      for p in e.findall("abVegetationValid/Pair") if p.findtext("bValue") == "1"]
        spawns = bool(terrains)

        spawn_notes: list[str] = []
        min_lat = int(e.findtext("iMinLatitude") or "0")
        max_lat = int(e.findtext("iMaxLatitude") or "90")
        if spawns and (min_lat > 0 or max_lat < 90):
            spawn_notes.append(f"Latitude {min_lat}–{max_lat}°")
        prob = int(e.findtext("iProbThousand") or "0")
        if prob:
            spawn_notes.append(f"Spawn weight {prob}/1000")
        min_dist = int(e.findtext("iMinDist") or "0")
        if min_dist:
            spawn_notes.append(f"Min {min_dist} tiles apart")
        min_pp = int(e.findtext("iMinPerPlayer") or "0")
        if min_pp:
            spawn_notes.append(f"Min {min_pp} per player")

        # Tile yields
        tile_yield = yield_pairs(e, "aiYieldNoImprovement", divide=True)   # per-turn rate
        reveal = yield_pairs(e, "aiYieldReveal", divide=False)             # one-time, raw
        harvest = yield_pairs(e, "aiYieldHarvest", divide=False)           # one-time, raw
        harvest_roll = int(e.findtext("iHarvestRoll") or "0")
        harvest_note = f"Regrows over time (roll {harvest_roll})" if harvest and harvest_roll else ""

        # Worked-by
        wb = worked_by.get(zt)
        worked = None
        if wb:
            worked = {
                "improvementId": wb["improvementId"],
                "class": token_words(wb["classId"], "IMPROVEMENTCLASS_"),
                "yields": wb["yields"],
                "replacesBase": wb["replacesBase"],
            }

        # Effects
        effects: list[str] = []
        if is_strategic:
            effects.append("Enables while worked: " + ", ".join(units_by_resource[zt]))
        if is_lux:
            effects.append("Luxury — city it is sent to gets " + ", ".join(lux_generic))
            effects.append("Sending it earns +20 Family Opinion (+40 for Players and Tribes)")
            for cls_name, lines in favorites.get(zt, []):
                extra = f" (extra {', '.join(lines)})" if lines else ""
                effects.append(f"Favorite of {cls_name} families{extra}")
            spec = lux_specialist.get(zt)
            if spec:
                effects.append(f"Becomes available as a luxury once a {spec} works it")
            if not spawns:
                effects.append("Acquired through events, trade missions or tech bonus cards only")
        if zt in precious:
            effects.append("Counts as Precious (Patrons cities: +25% Culture)")

        items.append({
            "id": zt,
            "slug": slug,
            "name": name,
            "icon": resolve_icon(e, zt),
            "dlc": DLC_NAMES.get(e.findtext("GameContentRequired") or "",
                                 (e.findtext("GameContentRequired") or "").replace("_", " ").title()) or None,
            "category": category,
            "spawns": spawns,
            "spawnTerrain": terrains,
            "spawnHeight": heights,
            "spawnVegetation": vegetation,
            "spawnNotes": spawn_notes,
            "tileYield": tile_yield,
            "reveal": reveal,
            "harvest": harvest,
            "harvestNote": harvest_note,
            "workedBy": worked,
            "effects": effects,
        })

    # Order: category (Bonus → Strategic → Luxury), then name; stable & scannable.
    cat_rank = {"Bonus": 0, "Strategic": 1, "Luxury": 2}
    items.sort(key=lambda x: (cat_rank[x["category"]], not x["spawns"], x["name"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    n_lux = sum(1 for i in items if i["category"] == "Luxury")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(items)} resources ({n_lux} luxuries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
