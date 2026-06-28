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


# Yield → color. MUST stay in sync with the `.yield-{key}` rules in
# src/styles/theme.css — those are the canonical palette (matched to
# the spreadsheet's Intro-tab legend). Bug history: when these drifted,
# multi-yield diagonal cells used the wrong colors (Culture rendered
# pink because this dict was out of date).
YIELD_COLORS = {
    "SCIENCE":     "#6b5ea6",   # light purple (was #9c6cc9)
    "CIVICS":      "#c98b46",   # peach
    "TRAINING":    "#c25555",   # light pink/red
    "MONEY":       "#d9b13a",   # light yellow
    "FOOD":        "#5e8c43",   # green
    "IRON":        "#8a8a8e",   # grey
    "STONE":       "#b3b3b8",   # light grey
    "WOOD":        "#8a4a08",   # brown
    "CULTURE":     "#4e84b8",   # light blue (was pink — FIX 2026-05-12)
    "GROWTH":      "#6ba368",   # light green
    "ORDERS":      "#b8b8c0",   # white/grey
    "DISCONTENT":  "#7a6ea3",   # lavender
    "HAPPINESS":   "#d9b13a",   # gold (same as money)
    "INFLUENCE":   "#c8c9d3",   # silver
    "INTRIGUE":    "#735483",   # purple
    "LEGITIMACY":  "#c9a04a",   # parchment gold
    "MAINTENANCE": "#a35858",   # red-salmon
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
    # "Train" excluded — it's the verb (e.g. "train Specialist more quickly"),
    # not the Training yield; aliasing it iconized prose verbs as the glyph.
    "training":     ["Training"],
    "civics":       ["Civics", "Civic", "Civ"],
    "culture":      ["Culture", "Cult"],
    "science":      ["Science", "Sci"],
    # "Coin"/"Coins"/"Mint" deliberately excluded — they're project names
    # ("Mint Coin", "Mint Coinage") and would mis-iconize as the Money glyph.
    "money":        ["Money"],
    "growth":       ["Growth", "Settler", "Settlers"],
    # "Harvest" excluded — it's a mechanic word (e.g. "+50% Harvest"), not a
    # Food synonym; aliasing it iconized the word as the Food glyph. Farm/Pasture
    # are improvement entities (see IMPROVEMENT aliases below), not yields.
    "food":         ["Food"],
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
            "page": f"nations/{slug}",   # dedicated detail page
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
            # Named royal families (Achaemenid, Pandya, …) have no detail page of
            # their own — only the 10 family CLASSES do (added below). Land on the
            # Families overview.
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

    # Improvements (rural + urban + wonders). Aliases include the common
    # shorthand the legacy spreadsheet uses: "LM" → Lumbermill, "Nets" →
    # Nets, "Grove" → Grove, "Courthouse" → Courthouse, "Odeon" → Odeon,
    # "Camp" → Camp, "Farms"/"Farm" → Farm, "Pastures"/"Pasture" → Pasture,
    # "Mines"/"Mine" → Mine. Used by the icon-only renderer in shrine /
    # bonus effect text.
    IMPROVEMENT_ALIASES = {
        "LUMBERMILL":  ["Lumbermill", "Lumber Mill", "LM", "LMs", "Lumbermills"],
        "NETS":        ["Nets", "Net", "Fishing Nets"],
        "GROVE":       ["Grove", "Groves"],
        "COURTHOUSE":  ["Courthouse", "Courthouses"],
        "ODEON":       ["Odeon", "Odeons"],
        "CAMP":        ["Camp", "Camps"],
        "FARM":        ["Farm", "Farms"],
        "PASTURE":     ["Pasture", "Pastures"],
        "MINE":        ["Mine", "Mines"],
        "QUARRY":      ["Quarry", "Quarries"],
        "HARBOR":      ["Harbor", "Harbors", "Harbour"],
        "WATERMILL":   ["Watermill", "Watermills"],
        "WINDMILL":    ["Windmill", "Windmills"],
        "BARRACKS":    ["Barracks"],
        "GARRISON_3":  ["Citadel", "Citadels"],
        "TEMPLE":      ["Temple", "Temples"],
        "MONASTERY":   ["Monastery", "Monasteries"],
        "CATHEDRAL":   ["Cathedral", "Cathedrals"],
        "PALACE":      ["Palace"],
        "LIBRARY":     ["Library", "Libraries"],
        "UNIVERSITY":  ["University", "Universities"],
        "MARKET":      ["Market", "Markets"],
        "BATHS":       ["Heated Baths", "Baths"],
        "GRANARY":     ["Granary", "Granaries"],
        "AMPHITHEATER":["Amphitheater", "Amphitheaters"],
        "FORT":        ["Fort", "Forts"],
        "STELE":       ["Stele", "Steles"],
    }
    PUBLIC_IMPROVEMENTS = ROOT / "public" / "img" / "icons" / "improvements"
    for key, aliases in IMPROVEMENT_ALIASES.items():
        filename = key.lower() + ".png"
        if not (PUBLIC_IMPROVEMENTS / filename).exists():
            continue  # icon wasn't extracted, skip
        # Use the first alias as the canonical display name
        name = aliases[0]
        slug = key.lower().replace("_", "-")
        entities.append({
            "id": f"IMPROVEMENT_{key}",
            "slug": slug,
            "type": "improvement",
            "name": name,
            "aliases": aliases,
            "page": "urban-improvements",   # most improvements live here; LM/Farm/etc. would route to rural-improvements
            "icon": f"img/icons/improvements/{filename}",
        })

    # Project icons (city projects referenced in bonus / shrine text)
    PROJECT_ALIASES: dict[str, list[str]] = {
        "treasury_1":   ["Treasury"],
        "olympics_1":   ["Olympics", "Olympiad", "Olympic Games"],
        # Mint Coin has no dedicated sprite; register with no icon so the
        # text "Mint Coin" stays as plain text rather than mis-iconizing.
    }
    PUBLIC_PROJECTS = ROOT / "public" / "img" / "icons" / "projects"
    for key, aliases in PROJECT_ALIASES.items():
        filename = key + ".png"
        if not (PUBLIC_PROJECTS / filename).exists():
            continue
        entities.append({
            "id": f"PROJECT_{key.upper()}",
            "slug": key.split("_")[0],
            "type": "project",
            "name": aliases[0],
            "aliases": aliases,
            "page": "wonders",
            "icon": f"img/icons/projects/{filename}",
        })

    # Unit-effect / promotion icons (Focus tiers etc.)
    PROMOTION_ALIASES: dict[str, list[str]] = {
        "focus1": ["Focus I", "Focus 1"],
        "focus2": ["Focus II", "Focus 2"],
        "focus3": ["Focus III", "Focus 3"],
    }
    PUBLIC_EFFECTS = ROOT / "public" / "img" / "icons" / "effects"
    for key, aliases in PROMOTION_ALIASES.items():
        filename = key + ".png"
        if not (PUBLIC_EFFECTS / filename).exists():
            continue
        entities.append({
            "id": f"EFFECTUNIT_{key.upper()}",
            "slug": key,
            "type": "promotion",
            "name": aliases[0],
            "aliases": aliases,
            "page": "promotions",
            "icon": f"img/icons/effects/{filename}",
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
                "page": "resources",   # dedicated resources overview
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
                "page": "units",   # roster overview (no per-unit detail page)
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

    # ── Richer entity types, sourced from the generated src/data JSON (which
    # already carries the exact slugs the pages render), so links land on the
    # right anchor. build_entities runs LAST in the data target, so these exist.
    def load_data(name: str):
        p = ROOT / "src" / "data" / name
        return json.loads(p.read_text()) if p.exists() else None

    # Shrines → the Shrines overview, anchored to the deity's shrine-type
    # section (#type-war …). Aliased by deity name (specific; safe to scan).
    shrines_data = load_data("shrines.json")
    if shrines_data:
        for sh in shrines_data.get("shrines", []):
            deity = sh.get("deity") or ""
            stype = (sh.get("type") or "").lower()
            if not (sh.get("id") and deity and stype):
                continue
            entities.append({
                "id": sh["id"],
                "slug": f"type-{stype}",          # → shrines#type-war
                "type": "shrine",
                "name": deity,
                "aliases": [deity, sh.get("fullName") or f"Shrine of {deity}"],
                "page": "shrines",
                "icon": icon_url(f"icons/shrines/{stype}.png"),
            })

    # Family CLASSES (Champions, Hunters, …) → their dedicated detail pages.
    for fc in (load_data("families.json") or []):
        if not (fc.get("id") and fc.get("slug")):
            continue
        entities.append({
            "id": fc["id"], "slug": fc["slug"], "type": "family",
            "name": fc.get("name") or fc["slug"], "aliases": [fc.get("name") or fc["slug"]],
            "page": f"families/{fc['slug']}",
        })

    # Wonders → dedicated detail pages.
    for w in (load_data("wonders.json") or []):
        if not (w.get("id") and w.get("slug")):
            continue
        entities.append({
            "id": w["id"], "slug": w["slug"], "type": "wonder",
            "name": w.get("name") or w["slug"], "aliases": [w.get("name") or w["slug"]],
            "page": f"wonders/{w['slug']}",
        })

    # Tribes → dedicated detail pages.
    for t in (load_data("tribes.json") or []):
        if not (t.get("id") and t.get("slug")):
            continue
        entities.append({
            "id": t["id"], "slug": t["slug"], "type": "tribe",
            "name": t.get("name") or t["slug"], "aliases": [t.get("name") or t["slug"]],
            "page": f"tribes/{t['slug']}",
        })

    # Theologies → the Theologies overview, anchored per theology.
    theo = load_data("theologies.json")
    if theo:
        for tier in theo.get("tiers", []):
            for th in tier.get("theologies", []):
                if not (th.get("id") and th.get("slug")):
                    continue
                entities.append({
                    "id": th["id"], "slug": th["slug"], "type": "theology",
                    "name": th.get("name") or th["slug"], "aliases": [th.get("name") or th["slug"]],
                    "page": "theologies",
                })

    # Archetypes → the Archetypes overview, anchored per archetype. Registered
    # before traits so the shared TRAIT_*_ARCHETYPE ids resolve here (dedup wins).
    for a in (load_data("archetypes.json") or []):
        if not (a.get("id") and a.get("slug")):
            continue
        entities.append({
            "id": a["id"], "slug": a["slug"], "type": "archetype",
            "name": a.get("name") or a["slug"], "aliases": [a.get("name") or a["slug"]],
            "page": "archetypes",
        })

    # Traits → the Traits overview, anchored per trait. Registered with
    # scan=False: there are 300+ and many are common words (Brave, Tough, …),
    # so they only link via explicit <Term id="TRAIT_X">, never free-text scan.
    traits_data = load_data("traits.json") or {}
    for cat, items in traits_data.items():
        if cat == "archetype" or not isinstance(items, list):
            continue  # archetype category handled above
        for t in items:
            if not (t.get("id") and t.get("slug") and t.get("name")):
                continue
            entities.append({
                "id": t["id"], "slug": t["slug"], "type": "trait",
                "name": t["name"], "aliases": [t["name"]],
                "page": "traits", "scan": False,
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
        if not e.get("scan", True):
            continue  # registered for explicit <Term> use, but never free-text scanned
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
