#!/usr/bin/env python3
"""
Build src/data/entities.json — the registry of every linkable thing in the site:
nations, yields, resources, techs, families, units, archetypes, laws.

Each entry has:
  { id, slug, name, aliases, type, page, icon, color? }

A separate aliases→id index makes runtime text-scanning fast.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
PUBLIC = ROOT / "public" / "img"
OUT = ROOT / "src" / "data" / "entities.json"


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def first_form(s: str | None) -> str:
    if not s:
        return ""
    return s.split("~")[0].strip()


def text_lookup(filenames: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        if not (XML_DIR / fn).exists():
            continue
        for entry in parse(fn).findall("Entry"):
            z = entry.findtext("zType") or ""
            en = first_form(entry.findtext("en-US"))
            if z and en:
                out[z] = en
    return out


# Yield → color (sampled to match in-game UI palette)
YIELD_COLORS = {
    "ORDERS":      "#d96e3a",   # warm scroll-orange
    "SCIENCE":     "#9c6cc9",   # purple flask
    "CIVICS":      "#c0823a",   # tan/civics
    "CULTURE":     "#d877a1",   # pink culture
    "MONEY":       "#d9b13a",   # gold
    "TRAINING":    "#c25555",   # red training
    "FOOD":        "#7fb15e",   # green food
    "GROWTH":      "#5fa37e",   # green growth
    "WOOD":        "#a9764c",   # brown wood
    "STONE":       "#9a9aa3",   # grey stone
    "IRON":        "#cfd0d2",   # silver iron
    "HAPPINESS":   "#74b7d4",   # light blue
    "DISCONTENT":  "#704949",   # dark red
    "INFLUENCE":   "#c8c9d3",   # silver
    "INTRIGUE":    "#735483",   # purple
    "LEGITIMACY":  "#c9a04a",   # parchment gold
    "MAINTENANCE": "#8a6a55",   # brown
    "DIVINE_FAVOR":"#e3c45f",   # warm gold
    "WRATH":       "#a83838",   # dark red
}

# Concepts that aren't single XML entities but are mentioned constantly in
# bonus text — give them their own canonical slug and color (mapped to yield).
# Extra short-form aliases for yields that show up in spreadsheet text.
# Slug must match the YIELD_ slug exactly (lowercased) so they merge.
# These also cover mechanic words that map to a yield (Mint→money,
# Harvest→food, Focus→training, etc.) so bonus/shrine text gets a sensible
# color even when no literal yield word appears.
YIELD_ALIASES: dict[str, list[str]] = {
    # Only true yield-name synonyms — not mechanic words. "Ranged", "Focus",
    # "Pillage", "XP" are unit mechanics, not yields, so they no longer drag
    # a cell into yield-training.
    "orders":       ["Order", "Orders"],
    "training":     ["Training", "Train"],
    "civics":       ["Civics", "Civic", "Civ"],
    "culture":      ["Culture", "Cult"],
    "science":      ["Science", "Sci"],
    "money":        ["Money", "Coin", "Coins", "Mint"],
    "growth":       ["Growth", "Settler", "Settlers"],
    "food":         ["Food", "Harvest", "Farms", "Farm", "Pastures", "Pasture"],
    "wood":         ["Wood", "Lumber", "Chop", "Chopping", "Forests", "Forest"],
    "stone":        ["Stone", "Quarry", "Quarries"],
    "iron":         ["Iron", "Mines", "Mine"],
    "happiness":    ["Happiness"],
    "discontent":   ["Discontent"],
    "influence":    ["Influence"],
    "intrigue":     ["Intrigue"],
    "legitimacy":   ["Legitimacy"],
    "divine_favor": ["Divine Favor"],
    "wrath":        ["Wrath"],
    "maintenance":  ["Maintenance"],
}


def icon_url(rel: str) -> str | None:
    """Return /img/{rel} if the file exists, else None."""
    if (PUBLIC / rel).exists():
        return f"img/{rel}"
    return None


def build() -> dict:
    text_nation = text_lookup(["text-nation.xml"])
    text_family = text_lookup(["text-family.xml"])
    text_infos = text_lookup(["text-infos.xml"])
    text_unit = text_lookup(["text-unit.xml"])
    text_tech = text_lookup(["text-tech.xml"])
    text_law = text_lookup(["text-law.xml"])

    entities: list[dict] = []

    # Yields (with merged short-form aliases)
    for ykey, color in YIELD_COLORS.items():
        slug = ykey.lower()
        entities.append({
            "id": f"YIELD_{ykey}",
            "slug": slug,
            "type": "yield",
            "name": ykey.replace("_", " ").title(),
            "aliases": YIELD_ALIASES.get(slug, []),
            "page": f"yields/{slug}",
            "icon": icon_url(f"icons/yields/{slug}.png"),
            "color": color,
        })

    # Nations
    for entry in parse("nation.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("NATION_"):
            continue
        gendered = entry.findtext("GenderedName") or ""
        name = text_nation.get(gendered.replace("GENDERED_", ""), zt.replace("NATION_", "").title())
        slug = zt.replace("NATION_", "").lower()
        entities.append({
            "id": zt,
            "slug": slug,
            "type": "nation",
            "name": name,
            "aliases": [name],
            "page": "nations",
            "icon": icon_url(f"crests/{slug}.png"),
        })

    # Families (just the names; class colors come from family.xml)
    for entry in parse("family.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("FAMILY_"):
            continue
        name = text_family.get(entry.findtext("Name") or "", zt.replace("FAMILY_", "").title())
        slug = zt.replace("FAMILY_", "").lower()
        entities.append({
            "id": zt,
            "slug": slug,
            "type": "family",
            "name": name,
            "aliases": [name],
            "page": "families",
            "icon": icon_url(f"families/{slug}.png"),
        })

    # Technologies (lightweight — full data in technologies.xml later)
    if (XML_DIR / "tech.xml").exists():
        for entry in parse("tech.xml").findall("Entry"):
            zt = entry.findtext("zType") or ""
            if not zt.startswith("TECH_"):
                continue
            name_key = entry.findtext("Name") or ""
            name = text_tech.get(name_key, zt.replace("TECH_", "").replace("_", " ").title())
            slug = zt.replace("TECH_", "").lower().replace("_", "-")
            entities.append({
                "id": zt,
                "slug": slug,
                "type": "tech",
                "name": name,
                "aliases": [name],
                "page": "technologies",
                "icon": icon_url(f"icons/techs/{zt[5:].lower()}.png"),
            })

    # Resources
    if (XML_DIR / "resource.xml").exists():
        for entry in parse("resource.xml").findall("Entry"):
            zt = entry.findtext("zType") or ""
            if not zt.startswith("RESOURCE_"):
                continue
            name_key = entry.findtext("Name") or ""
            name = text_infos.get(name_key, zt.replace("RESOURCE_", "").replace("_", " ").title())
            slug = zt.replace("RESOURCE_", "").lower()
            entities.append({
                "id": zt,
                "slug": slug,
                "type": "resource",
                "name": name,
                "aliases": [name],
                "page": "rural-improvements",
                "icon": icon_url(f"icons/resources/{slug}.png"),
            })

    # Units (just names for linking)
    if (XML_DIR / "unit.xml").exists():
        for entry in parse("unit.xml").findall("Entry"):
            zt = entry.findtext("zType") or ""
            if not zt.startswith("UNIT_"):
                continue
            name = text_unit.get(entry.findtext("Name") or "", zt.replace("UNIT_", "").replace("_", " ").title())
            slug = zt.replace("UNIT_", "").lower().replace("_", "-")
            entities.append({
                "id": zt,
                "slug": slug,
                "type": "unit",
                "name": name,
                "aliases": [name],
                "page": "unit-damage",
            })

    # Laws
    if (XML_DIR / "law.xml").exists():
        for entry in parse("law.xml").findall("Entry"):
            zt = entry.findtext("zType") or ""
            if not zt.startswith("LAW_"):
                continue
            name = text_law.get(entry.findtext("Name") or "", zt.replace("LAW_", "").replace("_", " ").title())
            slug = zt.replace("LAW_", "").lower().replace("_", "-")
            entities.append({
                "id": zt,
                "slug": slug,
                "type": "law",
                "name": name,
                "aliases": [name],
                "page": "laws",
            })

    # De-duplicate by id
    seen: set[str] = set()
    deduped: list[dict] = []
    for e in entities:
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        deduped.append(e)

    deduped.sort(key=lambda e: (e["type"], e["slug"]))

    # Build alias→id map for runtime scanning. Longer aliases first so
    # "Heavy Cavalry" matches before "Cavalry".
    alias_pairs: list[tuple[str, str]] = []
    for e in deduped:
        for alias in {e["name"], *e["aliases"]}:
            if alias and len(alias) >= 2:
                alias_pairs.append((alias, e["id"]))
    alias_pairs.sort(key=lambda p: -len(p[0]))
    alias_index = [{"alias": a, "id": i} for a, i in alias_pairs]

    return {
        "entities": deduped,
        "aliasIndex": alias_index,
        "yieldColors": YIELD_COLORS,
    }


def main() -> int:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(data['entities'])} entities, {len(data['aliasIndex'])} aliases")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
