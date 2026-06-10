#!/usr/bin/env python3
"""
Build src/data/terrain.json from terrain.xml + vegetation.xml + height.xml.

Three sections — terrains, vegetations, heights — each in XML file order
(the game's canonical ordering). Cross-references:

  * resources per terrain/height/vegetation come from resource.xml's
    abTerrainValid / abHeightValid / abVegetationValid maps.
  * rural improvements per terrain/height/vegetation come from
    improvement.xml TerrainValid → terrainTarget.xml. A TerrainValid list
    is OR'd in game code (Tile.isValidImprovementTerrain), and each target
    constrains one or more dimensions (Terrains / Heights / Vegetations),
    so each target is reverse-mapped per dimension independently.
    Targets with an AdjacentTerrain requirement get a short annotation.

Scale notes (verified against reference/Source):
  * MOVEMENT_MULTIPLER = 9 → iMovementCost 9 = 1 MP, 18 = 2 MP.
    Terrain cost is the tile's base; vegetation/height costs are additive.
  * Vegetation aiYieldRemove / aiYieldBuild are RAW stockpile amounts
    (Player.getYieldRemove returns them as-is) — no /10.
  * Height aiRoadCost / aiUrbanCost are RAW stockpile costs — no /10.
  * Vegetation aiDefendEffectUnit is an attack penalty for units with that
    trait attacking INTO the tile (Unit.cs: iModifier += -(value)).
  * bRequiresUnlock (Jungle) → removal needs the "remove all vegetation"
    unlock (Tile.cs canRemoveVegetation).

tileTag.xml is an empty stub in the current patch — nothing to read there.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import load_xml_indexes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "terrain.json"

MOVEMENT_MULTIPLIER = 9  # globalsInt.xml MOVEMENT_MULTIPLER

# Religious / urban-flair improvement classes excluded from the rural
# improvement cross-reference (same set build_rural_improvements.py skips).
SKIP_CLASSES = {
    "IMPROVEMENTCLASS_SHRINE", "IMPROVEMENTCLASS_MONASTERY",
    "IMPROVEMENTCLASS_TEMPLE", "IMPROVEMENTCLASS_CATHEDRAL",
    "IMPROVEMENTCLASS_HOLY_SITE", "IMPROVEMENTCLASS_ALTAR_ATEN",
    "IMPROVEMENTCLASS_CULT",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def yield_label(token: str) -> str:
    return (token or "").replace("YIELD_", "").replace("_", " ").title()


def pretty_token(token: str, *prefixes: str) -> str:
    s = token or ""
    for p in prefixes:
        s = s.replace(p, "")
    return s.replace("_", " ").title()


def content_label(token: str) -> str:
    """EMPIRES_OF_THE_INDUS → 'Empires of the Indus'."""
    words = (token or "").split("_")
    small = {"OF", "THE", "AND"}
    out = [w.title() if (i == 0 or w not in small) else w.lower()
           for i, w in enumerate(words)]
    return " ".join(out)


def mp(cost_str: str | None) -> int:
    """iMovementCost (multiples of 9) → movement points."""
    v = int(cost_str or "0")
    return v // MOVEMENT_MULTIPLIER


def yield_pairs_raw(parent: ET.Element, tag: str, prefix: str = "+") -> list[str]:
    out: list[str] = []
    for pair in parent.findall(f"{tag}/Pair"):
        y = yield_label(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{prefix}{v} {y}" if prefix else f"{v} {y}")
    return out


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text: dict[str, str] = indexes["__text__"]  # type: ignore[assignment]

    def name_of(entry: ET.Element, strip: str) -> str:
        key = entry.findtext("Name") or ""
        zt = entry.findtext("zType") or ""
        return text.get(key) or pretty_token(zt, strip)

    # ── terrainTarget.xml: target → constrained dimensions ─────────────
    targets: dict[str, dict] = {}
    for e in parse("terrainTarget.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        targets[zt] = {
            "terrains": list(dict.fromkeys(  # TERRAIN_TARGET_LAND lists ARID twice
                v.text for v in e.findall("Terrains/zValue") if v.text)),
            "heights": [v.text for v in e.findall("Heights/zValue") if v.text],
            "vegetations": [v.text for v in e.findall("Vegetations/zValue")
                            if v.text and v.text != "NONE"],
            "adjacent": e.findtext("AdjacentTerrain") or "",
        }

    ADJ_LABELS = {  # friendlier renderings of adjacency-target tokens
        "TERRAIN_TARGET_VOLCANO_MOUNTAIN": "Mountain/Volcano",
        "TERRAIN_TARGET_SALT_WATER": "salt water",
        "TERRAIN_TARGET_LAND": "land",
    }

    def adjacency_note(target_id: str) -> str:
        adj = targets.get(target_id, {}).get("adjacent", "")
        if not adj:
            return ""
        return f"adj. {ADJ_LABELS.get(adj, pretty_token(adj, 'TERRAIN_TARGET_'))}"

    # ── improvement.xml: rural buildables → reverse maps per dimension ──
    imp_by_terrain: dict[str, list[str]] = {}
    imp_by_height: dict[str, list[str]] = {}
    imp_by_vegetation: dict[str, list[str]] = {}
    for e in parse("improvement.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt or (e.findtext("bBuild") or "0") != "1":
            continue
        if (e.findtext("bUrban") or "0") == "1":
            continue
        if (e.findtext("bWonder") or "0") == "1":
            continue
        if (e.findtext("Class") or "") in SKIP_CLASSES:
            continue
        imp_name = name_of(e, "IMPROVEMENT_")
        for tv in e.findall("TerrainValid/zValue"):
            tgt = targets.get(tv.text or "")
            if not tgt:
                continue
            note = adjacency_note(tv.text or "")
            label = f"{imp_name} ({note})" if note else imp_name
            for t in tgt["terrains"]:
                imp_by_terrain.setdefault(t, []).append(label)
            for h in tgt["heights"]:
                imp_by_height.setdefault(h, []).append(label)
            for v in tgt["vegetations"]:
                imp_by_vegetation.setdefault(v, []).append(label)

    # ── resource.xml: reverse maps per dimension ─────────────────────────
    res_by_terrain: dict[str, list[dict]] = {}
    res_by_height: dict[str, list[dict]] = {}
    res_by_vegetation: dict[str, list[dict]] = {}
    for e in parse("resource.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        chip = {
            "id": zt,
            "name": name_of(e, "RESOURCE_"),
            "slug": zt.replace("RESOURCE_", "").lower(),
        }
        for pair in e.findall("abTerrainValid/Pair"):
            if pair.findtext("bValue") == "1":
                res_by_terrain.setdefault(pair.findtext("zIndex") or "", []).append(chip)
        for pair in e.findall("abHeightValid/Pair"):
            if pair.findtext("bValue") == "1":
                res_by_height.setdefault(pair.findtext("zIndex") or "", []).append(chip)
        for pair in e.findall("abVegetationValid/Pair"):
            if pair.findtext("bValue") == "1":
                res_by_vegetation.setdefault(pair.findtext("zIndex") or "", []).append(chip)

    def uniq(seq: list[str]) -> list[str]:
        """Dedupe, and drop annotated variants ('Quarry (adj. …)') when the
        plain label is already valid here — TerrainValid targets are OR'd,
        so the unconditional one subsumes the conditional one."""
        out = list(dict.fromkeys(seq))
        plain = {s for s in out if "(" not in s}
        return [s for s in out if "(" not in s or s.split(" (")[0] not in plain]

    # ── terrains ─────────────────────────────────────────────────────────
    terrains: list[dict] = []
    terrain_names: dict[str, str] = {}
    for e in parse("terrain.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        name = name_of(e, "TERRAIN_")
        terrain_names[zt] = name

        props: list[str] = []
        if e.findtext("bWater") == "1":
            props.append("Water")
        if e.findtext("bUrban") == "1":
            props.append("Urban")
        if e.findtext("bCitySite") == "1":
            props.append("City site")
        if e.findtext("bFreshWaterSource") == "1":
            props.append("Fresh water source")
        if e.findtext("bNoVegetation") == "1":
            props.append("No vegetation")
        if e.findtext("bRoadFree") == "1":
            props.append("Roads free")
        elif e.findtext("bRoadValid") == "1":
            props.append("Roads allowed")
        else:
            props.append("No roads")
        bc = int(e.findtext("iBuildChange") or "0")
        if bc:
            props.append(f"+{bc} turn to build improvements")
        dmg = int(e.findtext("iUnitDamage") or "0")
        if dmg:
            props.append(f"Units take {dmg} damage/turn")

        dh = e.findtext("DefaultHeight") or ""
        terrains.append({
            "id": zt,
            "slug": zt.replace("TERRAIN_", "").lower(),
            "name": name,
            "moveCost": mp(e.findtext("iMovementCost")),
            "borderValue": int(e.findtext("iBorderValue") or "0"),
            "properties": props,
            "defaultHeight": pretty_token(dh, "HEIGHT_") if dh else "",
            "resources": res_by_terrain.get(zt, []),
            "improvements": uniq(imp_by_terrain.get(zt, [])),
        })

    # ── vegetations ──────────────────────────────────────────────────────
    veg_root = parse("vegetation.xml")
    veg_names = {
        e.findtext("zType"): name_of(e, "VEGETATION_")
        for e in veg_root.findall("Entry") if e.findtext("zType")
    }
    vegetations: list[dict] = []
    for e in veg_root.findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue

        lifecycle: list[str] = []
        rem = e.findtext("VegetationRemove") or ""
        if rem:
            lifecycle.append(f"Cut → {veg_names.get(rem, pretty_token(rem, 'VEGETATION_'))}")
        grow = e.findtext("VegetationGrow") or ""
        if grow:
            lifecycle.append(f"Grows into {veg_names.get(grow, pretty_token(grow, 'VEGETATION_'))}")
        spread = e.findtext("VegetationSpread") or ""
        if spread:
            lifecycle.append(f"Spreads as {veg_names.get(spread, pretty_token(spread, 'VEGETATION_'))}")

        # Attack penalty for units with the trait attacking into this tile
        defense: list[str] = []
        for pair in e.findall("aiDefendEffectUnit/Pair"):
            trait = pretty_token(pair.findtext("zIndex") or "", "EFFECTUNIT_")
            v = int(pair.findtext("iValue") or "0")
            defense.append(f"-{v}% {trait} attacks vs this tile")

        notes: list[str] = []
        if e.findtext("bRequiresUnlock") == "1":
            notes.append("Removal requires unlock")
        rc = int(e.findtext("iRemoveCost") or "0")
        if rc:
            notes.append(f"Remove cost: {rc} Order{'s' if rc != 1 else ''}")

        content = e.findtext("GameContentDisplay") or ""
        vegetations.append({
            "id": zt,
            "slug": zt.replace("VEGETATION_", "").lower(),
            "name": veg_names[zt],
            "dlc": content_label(content) if content else "",
            "moveCostExtra": mp(e.findtext("iMovementCost")),
            "yieldRemove": yield_pairs_raw(e, "aiYieldRemove"),
            "yieldBuild": yield_pairs_raw(e, "aiYieldBuild"),
            "defense": defense,
            "lifecycle": lifecycle,
            "notes": notes,
            "resources": res_by_vegetation.get(zt, []),
            "improvements": uniq(imp_by_vegetation.get(zt, [])),
        })

    # ── heights ──────────────────────────────────────────────────────────
    heights: list[dict] = []
    all_terrain_ids = [t["id"] for t in terrains]
    for e in parse("height.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue

        props: list[str] = []
        if e.findtext("bImpassable") == "1":
            props.append("Impassable")
        if e.findtext("bRangedAttackBlock") == "1":
            props.append("Blocks ranged attacks")
        if e.findtext("bElevation") == "1":
            props.append("Elevated")
        if e.findtext("bCitySite") == "1":
            props.append("City site")
        if e.findtext("bFreshWaterSource") == "1":
            props.append("Fresh water source")
        if e.findtext("bSupportsAqueduct") == "1":
            props.append("Supports aqueduct")
        if e.findtext("bNoVegetation") == "1":
            props.append("No vegetation")

        bonuses: list[str] = []
        rng = int(e.findtext("iRangeChange") or "0")
        if rng:
            bonuses.append(f"+{rng} attack range")
        rev = int(e.findtext("iRevealChange") or "0")
        if rev:
            bonuses.append(f"+{rev} sight")
        bc = int(e.findtext("iBuildChange") or "0")
        if bc:
            bonuses.append(f"+{bc} turn to build improvements")

        invalid = [v.text for v in e.findall("TerrainInvalid/zValue") if v.text]
        valid_terrains = [terrain_names[t] for t in all_terrain_ids if t not in invalid]

        heights.append({
            "id": zt,
            "slug": zt.replace("HEIGHT_", "").lower(),
            "name": name_of(e, "HEIGHT_"),
            "moveCostExtra": mp(e.findtext("iMovementCost")),
            "properties": props,
            "bonuses": bonuses,
            "roadCost": yield_pairs_raw(e, "aiRoadCost", prefix=""),
            "urbanCost": yield_pairs_raw(e, "aiUrbanCost", prefix=""),
            "validTerrains": valid_terrains,
            "resources": res_by_height.get(zt, []),
            "improvements": uniq(imp_by_height.get(zt, [])),
        })

    data = {"terrains": terrains, "vegetations": vegetations, "heights": heights}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — "
          f"{len(terrains)} terrains, {len(vegetations)} vegetations, {len(heights)} heights")
    return 0


if __name__ == "__main__":
    sys.exit(main())
