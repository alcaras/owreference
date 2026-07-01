#!/usr/bin/env python3
"""
Build src/data/wonders.json from improvement.xml (entries with bWonder=1)
plus their EffectPlayer/EffectCity chains and Bonus one-time payloads.

Each wonder row carries:
  - name, slug, id, gameContent (DLC tag)
  - era       (from CulturePrereq: Weak/Developing/Strong/Legendary)
  - location  (one-line hint pulled from TerrainValid + boolean flags)
  - cost      (yield → amount, divided by 10 where appropriate)
  - effects   (humanized list — ongoing bonus)
  - oneTime   (humanized list — Bonus payload, if any)
  - nation    ("Any" by default; "Hittite Bonus"/"Maurya Bonus" only when
               the wonder lives behind a DLC tag)

Run after `make sync` or whenever XML changes.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_player, render_bonus,
    render_effect_city, render_effect_player_scalars,
    render_effect_city_state_religion, render_effect_city_capital,
    fmt_decimal, yield_name,
)


def _nice_token(token: str) -> str:
    """UNIT_CARAVAN → Caravan, RELIGION_BUDDHISM → Buddhism, etc."""
    return (token.split("_", 1)[-1] if "_" in token else token).replace("_", " ").title()


def tile_and_oneoff_lines(entry: ET.Element, indexes: dict,
                          include_bonus_cities: bool = True) -> list[str]:
    """One-time / tile / recurring effects the EffectPlayer chain misses:
    BonusCities payloads, periodic free units (iUnitTurns + aiUnitDie),
    unit-trait XP, religion spread, and adjacent-tile class yields.
    All read from improvement.xml — no spreadsheet.

    `include_bonus_cities` is True for the flat oneTime list; scoped_effects()
    passes False because it routes the every-city payload to its own bucket."""
    out: list[str] = []

    # Bonus applied to every city on completion (Ishtar Gate, Hagia
    # Sophia, Jebel Barkal). render_bonus already phrases "in every City".
    if include_bonus_cities:
        bc_id = (entry.findtext("BonusCities") or "").strip()
        if bc_id:
            bc = indexes.get("bonus.xml", {}).get(bc_id)
            if bc is not None:
                out.extend(render_bonus(bc, indexes))

    # Periodic free unit: iUnitTurns = period, aiUnitDie = which unit(s).
    period = entry.findtext("iUnitTurns")
    if period and period != "0":
        for pair in entry.findall("aiUnitDie/Pair"):
            unit = _nice_token(pair.findtext("zIndex") or "")
            out.append(f"Free {unit} every {int(period)} turns")

    # Bonus XP for a unit trait built here (Circus Maximus, Cothon).
    for pair in entry.findall("aiUnitTraitXP/Pair"):
        trait = _nice_token(pair.findtext("zIndex") or "")
        v = int(pair.findtext("iValue") or "0")
        out.append(f"+{v} XP for {trait} units built here")

    # Religion this wonder spreads (Monumental Buddhas).
    rel = (entry.findtext("ReligionSpread") or "").strip()
    if rel:
        out.append(f"Spreads {_nice_token(rel)}")

    # Yield to adjacent tiles of an improvement class (Chittorgarh:
    # +2 Training to adjacent Farms). Tile-yield values are 10× display.
    for pair in entry.findall("aaiAdjacentImprovementClassYield/Pair"):
        cls = _nice_token(pair.findtext("zIndex") or "")
        sp = pair.find("SubPair")
        if sp is None:
            continue
        y = yield_name(sp.findtext("zSubIndex"))
        v = int(sp.findtext("iValue") or "0") / 10
        if v == int(v):
            v = int(v)
        out.append(f"{fmt_decimal(v)} {y} to adjacent {cls}s")

    return out


def _dedup(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def scoped_effects(entry: ET.Element, indexes: dict) -> dict[str, list[str]]:
    """Partition a wonder's humanized effects into the four scopes the legacy
    spreadsheet distinguished, decided by WHICH XML side-channel each effect
    comes from (the game encodes scope structurally — see CLAUDE.md):

      global    — EffectPlayer scalar fields: player-wide modifiers, rates,
                  and unlocks (e.g. Pyramids' -50% Law Cost).
      allCities — the EffectPlayer's EffectCity / EffectCityExtra (applied to
                  every city), StateReligionEffectCity, and the improvement's
                  BonusCities payload (granted to every city on completion).
      localCity — the improvement's OWN EffectCity + its one-time Bonus, which
                  land only on the wonder's city; plus any CapitalEffectCity.
      tile      — adjacency yields, periodic free units, unit-trait XP, and
                  religion spread that live physically on the wonder tile. The
                  tile's per-turn yield output is surfaced separately as chips
                  (culturePerTurn / otherOutput), so it is not repeated here.

    Union of the four buckets equals the old flat effects+oneTime set; this
    only re-partitions it. Wonders use no nested EffectPlayer / EffectUnit
    (verified against improvement.xml), so those channels are intentionally
    not walked here."""
    ecidx = indexes.get("effectCity.xml", {})
    bidx = indexes.get("bonus.xml", {})
    g: list[str] = []
    ac: list[str] = []
    lc: list[str] = []
    tile: list[str] = []

    ep_id = (entry.findtext("EffectPlayer") or "").strip()
    ep = indexes.get("effectPlayer.xml", {}).get(ep_id) if ep_id else None
    if ep is not None:
        # Player-wide scalars (VP is handled separately, as a chip).
        g.extend(ln for ln in render_effect_player_scalars(ep)
                 if not re.match(r"\+\d+ Victory Points", ln))
        # Every-city per-turn effects.
        for tag in ("EffectCity", "EffectCityExtra"):
            ec = ecidx.get((ep.findtext(tag) or "").strip())
            if ec is not None:
                ac.extend(render_effect_city(ec, per_city=True, indexes=indexes))
        srec = ecidx.get((ep.findtext("StateReligionEffectCity") or "").strip())
        if srec is not None:
            ac.extend(render_effect_city_state_religion(srec, indexes=indexes))
        capc = ecidx.get((ep.findtext("CapitalEffectCity") or "").strip())
        if capc is not None:
            lc.extend(render_effect_city_capital(capc, indexes=indexes))
        # Player-level one-time bonuses (none in the current data, kept for safety).
        for tag in ("StartBonus", "FoundBonus", "Bonus"):
            b = bidx.get((ep.findtext(tag) or "").strip())
            if b is not None:
                for line in render_bonus(b, indexes):
                    g.append(line if line.startswith("Unlocks ")
                             else "On completion: " + line)

    # The improvement's OWN EffectCity → the wonder's city only.
    ec_direct = ecidx.get((entry.findtext("EffectCity") or "").strip())
    if ec_direct is not None:
        lc.extend(render_effect_city(ec_direct, per_city=True, indexes=indexes))

    # The improvement's OWN Bonus is a player-wide grant applied at the moment
    # of completion. The only case (Oracle → bHolyCityAgents) hands the free
    # agent network to your Holy Cities *on completion* — it does not cover
    # Holy Cities founded later — so it is a one-time grant, filed under
    # `global` (matching the SS) with an "On completion:" marker.
    b_direct = bidx.get((entry.findtext("Bonus") or "").strip())
    if b_direct is not None:
        for line in render_bonus(b_direct, indexes):
            g.append(line if line.startswith("Unlocks ")
                     else "On completion: " + line)

    # BonusCities → a genuinely one-time payload granted to EVERY city on
    # completion (Ishtar Gate culture, Hagia Sophia happiness, Jebel temple).
    bc = bidx.get((entry.findtext("BonusCities") or "").strip())
    if bc is not None:
        for line in render_bonus(bc, indexes):
            ac.append("On completion: " + line)

    # Tile-bound effects (adjacency, periodic units, XP, spread) — no BonusCities.
    tile.extend(tile_and_oneoff_lines(entry, indexes, include_bonus_cities=False))

    return {
        "global": _dedup(g),
        "allCities": _dedup(ac),
        "localCity": _dedup(lc),
        "tile": _dedup(tile),
    }


ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "wonders.json"
IMG_DIR = ROOT / "public" / "img" / "icons" / "improvements"
# Curation layer: MP tier rating + strategy notes (the one thing XML lacks).
ANNO = ROOT / "src" / "data" / "annotations" / "wonders.yaml"


def load_annotations() -> dict[str, dict]:
    """slug → {tier, notes} from the curated yaml (empty if absent)."""
    if not ANNO.exists():
        return {}
    import yaml  # local import: only this build needs it
    data = yaml.safe_load(ANNO.read_text()) or {}
    return data.get("wonders", {}) or {}


# Letter-tier rank for sorting/coloring; free-text caveats sort last.
TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}

# Cost columns surfaced on the page, in in-game yield order.
COST_YIELDS = ["food", "iron", "stone", "wood", "civics"]


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def resolve_icon(name: str, ztype: str, icon_name: str) -> str:
    """Sprite path for a wonder, '' if none was extracted.

    Tries, in order: display-name slug → zType slug → zIconName slug
    (and its raw apostrophe form). zIconName is the reliable key for the
    handful whose art ships under a different name (Acropolis→Parthenon,
    Via Recta Souk→Grand Bazaar, Mahavihara→Nalanda Mahavihra, …).
    Resolves 27/28 — only Sanchi's Stupa has no extracted sprite.
    """
    icn = icon_name.replace("IMPROVEMENT_", "")
    cands = [
        slugify(name),
        ztype.replace("IMPROVEMENT_", "").lower(),
        slugify(icn),
        icn.lower(),
    ]
    for cand in cands:
        if cand and (IMG_DIR / f"{cand}.png").exists():
            return f"img/icons/improvements/{cand}.png"
    return ""


ERA_BY_CULTURE = {
    "CULTURE_WEAK":       {"order": 1, "label": "Weak"},
    "CULTURE_DEVELOPING": {"order": 2, "label": "Developing"},
    "CULTURE_STRONG":     {"order": 3, "label": "Strong"},
    "CULTURE_LEGENDARY":  {"order": 4, "label": "Legendary"},
}

# Map TerrainValid tokens to a short, user-facing location label
TERRAIN_LOCATION_LABEL: dict[str, str] = {
    "TERRAIN_TARGET_DRY":                      "Arid or Sand",
    "TERRAIN_TARGET_HILL":                     "Hill",
    "TERRAIN_TARGET_COAST":                    "Coastal Water",
    "TERRAIN_TARGET_ADJACENT_VOLCANO_MOUNTAIN": "Adj. Mountain / Volcano",
    "TERRAIN_TARGET_HABITABLE":                "Habitable Tile",
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


def humanize_imp_name(zt: str) -> str:
    """Fallback when text lookup fails: IMPROVEMENT_GREAT_ZIGGURAT → Great Ziggurat."""
    return zt.replace("IMPROVEMENT_", "").replace("_", " ").title()


def _location_parts(entry: ET.Element) -> list[str]:
    """Primitive location-requirement tags from terrain + flags."""
    parts: list[str] = []
    for t in entry.findall("TerrainValid/zValue"):
        token = (t.text or "").strip()
        if not token:
            continue
        parts.append(TERRAIN_LOCATION_LABEL.get(token, token.replace("TERRAIN_TARGET_", "").replace("_", " ").title()))
    if (entry.findtext("bRiverValid") or "") == "1":
        parts.append("River")
    if (entry.findtext("bHolyCityValid") or "") == "1":
        parts.append("Holy City")
    if (entry.findtext("bFreshWaterSource") or "") == "1" and "Fresh Water source" not in parts:
        parts.append("Fresh Water source")
    return parts


def location_from(entry: ET.Element) -> str:
    """One-line location requirement string from terrain + flags."""
    parts = _location_parts(entry)
    return " or ".join(parts) if parts else "Any tile"


def location_tags(entry: ET.Element) -> list[str]:
    """Faceted-filter tags — same primitives, 'Any tile' when unconstrained."""
    return _location_parts(entry) or ["Any tile"]


# Short source label for the Source/DLC facet.
SOURCE_LABEL = {
    "":                     "Base game",
    "WONDERS_DYNASTIES":    "Wonders & Dynasties",
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus",
    "SEARCH_AND_PROGRESS":  "Search & Progress",
    "BEHIND_THE_THRONE":    "Behind the Throne",
}

# Curated Wikipedia targets — the *historical* wonder, not the generic
# term. Keyed by improvement zType. Anything not listed falls back to the
# default generator (name minus "The ", spaces→underscores), which is
# already correct for Ishtar Gate, Hagia Sophia, Jebel Barkal, etc.
WIKI_OVERRIDE = {
    "IMPROVEMENT_PYRAMIDS":           "Egyptian pyramids",
    "IMPROVEMENT_GREAT_ZIGGURAT":     "Ziggurat of Ur",
    "IMPROVEMENT_ORACLE":             "Pythia",
    "IMPROVEMENT_HANGING_GARDENS":    "Hanging Gardens of Babylon",
    "IMPROVEMENT_LIGHTHOUSE":         "Lighthouse of Alexandria",
    "IMPROVEMENT_COLOSSUS":           "Colossus of Rhodes",
    "IMPROVEMENT_MAUSOLEUM":          "Mausoleum at Halicarnassus",
    "IMPROVEMENT_ACROPOLIS":          "Acropolis of Athens",
    "IMPROVEMENT_ROYAL_LIBRARY":      "Library of Alexandria",
    "IMPROVEMENT_MUSAEUM":            "Musaeum",
    "IMPROVEMENT_PANTHEON":           "Pantheon, Rome",
    "IMPROVEMENT_NECROPOLIS":         "Valley of the Kings",
    "IMPROVEMENT_HELIOPOLIS":         "Heliopolis (ancient Egypt)",
    "IMPROVEMENT_STUPA":              "Sanchi",
    "IMPROVEMENT_THE_MAHAVIHARA":     "Nalanda",
    "IMPROVEMENT_MONUMENTAL_BUDDHAS": "Buddhas of Bamiyan",
    "IMPROVEMENT_HILL_FORT":          "Chittor Fort",
    "IMPROVEMENT_VIA_RECTA_SOUK":     "Straight Street",
    "IMPROVEMENT_JERWAN_AQUEDUCT":    "Jerwan",
    "IMPROVEMENT_YAZILIKAYA":         "Yazılıkaya",
    "IMPROVEMENT_COTHON":             "Cothon",
    "IMPROVEMENT_AL_KHAZNEH":         "Al-Khazneh",
}


def cost_lines(entry: ET.Element) -> list[dict]:
    """[{yield: 'civics', value: 100, label: '+100 Civics'}, …] — values shown as
    in-game numbers (not divided by 10; build cost is already at user-facing scale)."""
    out: list[dict] = []
    for pair in entry.findall("aiYieldCost/Pair"):
        y_key = (pair.findtext("zIndex") or "").replace("YIELD_", "").lower()
        iv = int(pair.findtext("iValue") or "0")
        out.append({"yield": y_key, "value": iv, "label": f"{iv} {y_key.title()}"})
    return out


def output_lines(entry: ET.Element) -> list[dict]:
    """Yields produced once per turn by the wonder tile itself.
    Game stores at 10× user-facing — divide by 10 for display."""
    out: list[dict] = []
    for pair in entry.findall("aiYieldOutput/Pair"):
        y_key = (pair.findtext("zIndex") or "").replace("YIELD_", "").lower()
        raw = int(pair.findtext("iValue") or "0")
        v = raw / 10
        if v == int(v):
            v = int(v)
        out.append({"yield": y_key, "value": v, "label": f"+{v} {y_key.title()}/Turn"})
    return out


DLC_LABEL = {
    "WONDERS_DYNASTIES":  "Wonders & Dynasties DLC",
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus DLC",
    "SEARCH_AND_PROGRESS": "Search & Progress DLC",
    "BEHIND_THE_THRONE":   "Behind the Throne DLC",
}


def main() -> int:
    text_imp = load_text(
        "text-improvement.xml",
        "text-wonders-dynasties-infos.xml",
        "text-eoti.xml",
        "text-improvement-sap.xml",
        "text-improvement-hittite.xml",
    )
    indexes = load_xml_indexes(XML_DIR)
    anno = load_annotations()

    wonders: list[dict] = []
    for entry in parse("improvement.xml").findall("Entry"):
        if (entry.findtext("bWonder") or "0") != "1":
            continue
        zt = entry.findtext("zType") or ""
        if not zt:
            continue
        name_key = entry.findtext("Name") or ""
        name = text_imp.get(name_key, humanize_imp_name(zt))
        # Drop a leading "The " for cleaner alphabetical sorting
        sort_name = re.sub(r"^The\s+", "", name).strip()

        culture = entry.findtext("CulturePrereq") or "CULTURE_WEAK"
        era = ERA_BY_CULTURE.get(culture, {"order": 0, "label": culture})

        cost = cost_lines(entry)
        # Per-yield cost map for the sortable columns (None where the
        # wonder doesn't use that yield, so the column shows a dash).
        cost_by = {c["yield"]: c["value"] for c in cost}
        cost_map = {y: cost_by.get(y) for y in COST_YIELDS}
        icon = resolve_icon(name, zt, entry.findtext("zIconName") or "")
        output = output_lines(entry)
        location = location_from(entry)
        build_turns = int(entry.findtext("iBuildTurns") or "0")
        vp = 0  # filled below from effect player
        dlc_tag = entry.findtext("GameContentRequired") or ""
        dlc_label = DLC_LABEL.get(dlc_tag, dlc_tag.replace("_", " ").title() if dlc_tag else "")

        # Ongoing + scalar bonus via humanizer (chain through EffectPlayer)
        ep_id = (entry.findtext("EffectPlayer") or "").strip()
        effects_all: list[str] = render_effect_player(ep_id, indexes) if ep_id else []
        # Extract VP if humanizer surfaced it, so we can show it as a chip
        for ln in list(effects_all):
            m = re.match(r"\+(\d+) Victory Points", ln)
            if m:
                vp = int(m.group(1))
        # We display VP separately — drop the line from the effects list
        effects = [ln for ln in effects_all if not re.match(r"\+\d+ Victory Points", ln)]

        # Direct EffectCity (some wonders, e.g., Great Ziggurat aiYieldRate global)
        ec_direct = (entry.findtext("EffectCity") or "").strip()
        if ec_direct:
            ec = indexes.get("effectCity.xml", {}).get(ec_direct)
            if ec is not None:
                from humanize import render_effect_city
                for ln in render_effect_city(ec, per_city=True, indexes=indexes):
                    if ln not in effects:
                        effects.append(ln)

        # One-time bonus (Bonus = on-build payload) + per-city / tile /
        # recurring effects the EffectPlayer chain doesn't cover.
        one_time: list[str] = []
        b_id = (entry.findtext("Bonus") or "").strip()
        if b_id:
            b = indexes.get("bonus.xml", {}).get(b_id)
            if b is not None:
                one_time.extend(render_bonus(b, indexes))
        for ln in tile_and_oneoff_lines(entry, indexes):
            if ln not in one_time:
                one_time.append(ln)

        # Split the wonder-tile per-turn output: Culture gets its own
        # sortable column; anything else stays as chips.
        culture_per_turn = 0
        other_output = []
        for o in output:
            if o["yield"] == "culture":
                culture_per_turn = o["value"]
            else:
                other_output.append(o)

        # External reference (game files carry no prose). Prefer the
        # curated historical article; else derive from the name.
        wiki_title = WIKI_OVERRIDE.get(zt) or re.sub(r"^The\s+", "", name).strip()
        from urllib.parse import quote
        # Wikipedia title chars that should stay literal in the path.
        wiki = "https://en.wikipedia.org/wiki/" + quote(
            wiki_title.replace(" ", "_"), safe="(),'-_")

        slug = zt.replace("IMPROVEMENT_", "").lower()
        # XML-derived scope buckets (global / all cities / local city / tile).
        scopes = scoped_effects(entry, indexes)
        # Curated MP tier + notes (the only non-XML content on the page).
        a = anno.get(slug, {})
        tier = (a.get("tier") or "").strip()
        wonders.append({
            "id": zt,
            "slug": slug,
            "name": name,
            "sortName": sort_name,
            "era": era["label"],
            "eraOrder": era["order"],
            "culturePrereq": culture,
            "location": location,
            "locationTags": location_tags(entry),
            "source": SOURCE_LABEL.get(dlc_tag, dlc_tag.replace("_", " ").title() if dlc_tag else "Base game"),
            "buildTurns": build_turns,
            "cost": cost,
            "costMap": cost_map,
            "icon": icon,
            "output": output,
            "otherOutput": other_output,
            "culturePerTurn": culture_per_turn,
            "wikipedia": wiki,
            "vp": vp,
            "effects": effects,
            "oneTime": one_time,
            "scopes": scopes,
            "tier": tier,
            "tierRank": TIER_RANK.get(tier, 90) if tier else 99,
            "notes": (a.get("notes") or "").strip(),
            "dlc": dlc_tag,
            "dlcLabel": dlc_label,
            "nation": "Any",     # All XML wonders are universal in OW
            "isHolyCity": (entry.findtext("bHolyCityValid") or "") == "1",
        })

    # Stable order: era first, then alphabetical by sortName
    wonders.sort(key=lambda w: (w["eraOrder"], w["sortName"].lower()))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(wonders, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(wonders)} wonders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
