#!/usr/bin/env python3
"""
Shared reader for terrainTarget.xml — the game's named terrain groups.

improvement.xml's TerrainValid / TerrainInvalid, wonder locations, occurrence
targets and effect hide-lists never name a terrain directly: they name a
TERRAIN_TARGET_*, which is a *group* of tile conditions ("Fertile Land",
"Habitable Land", "Wet"). Tile.isTerrainTarget (Tile.cs:3058 →
TileData.isTerrainTarget, TileData.cs:395) tests one as an AND across the
dimensions the group constrains:

  * Terrains / Heights / Vegetations — each list is an OR, and an EMPTY list
    means that dimension is unconstrained.
  * bFreshWaterAccess — the tile must have fresh water access.
  * AdjacentTerrain — some adjacent tile must itself match that group.

A `<Vegetations><zValue>NONE</zValue>` entry is a real constraint ("the tile
must be bare"), not an empty list, so it is kept separately from the named
vegetations.

A TerrainValid *list* on an improvement is OR'd (Tile.isValidImprovementTerrain,
Tile.cs:5537), so any one group qualifies.

Every builder that surfaces one of these tokens resolves its label here, so the
site shows the game's own name ("Fertile Land", not a prettified "Fertile") and
can link the tag to the group's row on /terrain. Three builders used to
prettify the token themselves and a fourth kept a hand-written label map; they
disagreed with each other and none of them explained the term anywhere.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

PREFIX = "TERRAIN_TARGET_"


def pretty(token: str, strip: str = PREFIX) -> str:
    s = (token or "").replace(strip, "")
    return s.replace("_", " ").title() if s else ""


def _first_form(raw: str | None) -> str:
    """text-*.xml packs declensions as 'Nominative~Genitive~…'."""
    return ((raw or "").split("~")[0]).strip()


def load_text(xml_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(xml_dir.glob("text-*.xml")):
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        for entry in root.findall("Entry"):
            k = entry.findtext("zType") or ""
            en = _first_form(entry.findtext("en-US"))
            if k and en:
                out.setdefault(k, en)
    return out


def _names(xml_dir: Path, fname: str, strip: str, text: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    path = xml_dir / fname
    if not path.exists():
        return out
    for e in ET.parse(path).getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        out[zt] = text.get(e.findtext("Name") or "") or pretty(zt, strip)
    return out


def load_groups(xml_dir: Path, text: dict[str, str] | None = None) -> dict[str, dict]:
    """token → group dict, in terrainTarget.xml order.

    Keys: id, slug, name, terrainIds/terrains, heightIds/heights,
    vegetationIds/vegetations, bare, freshWater, adjacentId/adjacent.
    """
    text = text if text is not None else load_text(xml_dir)
    terrain_names = _names(xml_dir, "terrain.xml", "TERRAIN_", text)
    height_names = _names(xml_dir, "height.xml", "HEIGHT_", text)
    veg_names = _names(xml_dir, "vegetation.xml", "VEGETATION_", text)

    groups: dict[str, dict] = {}
    for e in ET.parse(xml_dir / "terrainTarget.xml").getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        # TERRAIN_TARGET_LAND lists TERRAIN_ARID twice — dedupe, keep order.
        terrain_ids = list(dict.fromkeys(
            v.text for v in e.findall("Terrains/zValue") if v.text))
        height_ids = [v.text for v in e.findall("Heights/zValue") if v.text]
        veg_raw = [v.text for v in e.findall("Vegetations/zValue") if v.text]
        veg_ids = [v for v in veg_raw if v != "NONE"]
        adj = e.findtext("AdjacentTerrain") or ""
        groups[zt] = {
            "id": zt,
            "slug": zt.replace(PREFIX, "").lower(),
            "name": text.get(e.findtext("Name") or "") or pretty(zt),
            "terrainIds": terrain_ids,
            "terrains": [terrain_names.get(t, pretty(t, "TERRAIN_")) for t in terrain_ids],
            "heightIds": height_ids,
            "heights": [height_names.get(h, pretty(h, "HEIGHT_")) for h in height_ids],
            "vegetationIds": veg_ids,
            "vegetations": [veg_names.get(v, pretty(v, "VEGETATION_")) for v in veg_ids],
            "bare": "NONE" in veg_raw,
            "freshWater": (e.findtext("bFreshWaterAccess") or "0") == "1",
            "adjacentId": adj,
            "adjacent": "",  # filled below, once every group has a name
        }

    for g in groups.values():
        if g["adjacentId"]:
            adj_g = groups.get(g["adjacentId"])
            g["adjacent"] = adj_g["name"] if adj_g else pretty(g["adjacentId"])

    return groups


def ref(token: str, groups: dict[str, dict], negated: bool = False) -> dict:
    """JSON shape for a terrain requirement tag: the game's label plus the
    /terrain anchor slug (empty when a patch adds a token we have no entry
    for, so the page renders it as plain text instead of a dead link)."""
    g = groups.get(token or "")
    out = {
        "label": g["name"] if g else pretty(token),
        "slug": g["slug"] if g else "",
    }
    if negated:
        out["not"] = True
    return out
