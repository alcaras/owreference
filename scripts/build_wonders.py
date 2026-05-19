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
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "wonders.json"
IMG_DIR = ROOT / "public" / "img" / "icons" / "improvements"

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


def location_from(entry: ET.Element) -> str:
    """Build a one-line location requirement string from terrain + flags."""
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
    if (entry.findtext("bFreshWaterSource") or "") == "1":
        # Often combined with TerrainValid; surface separately as a note
        if "Fresh Water" not in parts:
            parts.append("Fresh Water source")
    return " or ".join(parts) if parts else "Any tile"


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

        # One-time bonus (Bonus = on-build payload)
        one_time: list[str] = []
        b_id = (entry.findtext("Bonus") or "").strip()
        if b_id:
            b = indexes.get("bonus.xml", {}).get(b_id)
            if b is not None:
                one_time = render_bonus(b, indexes)

        wonders.append({
            "id": zt,
            "slug": zt.replace("IMPROVEMENT_", "").lower(),
            "name": name,
            "sortName": sort_name,
            "era": era["label"],
            "eraOrder": era["order"],
            "culturePrereq": culture,
            "location": location,
            "buildTurns": build_turns,
            "cost": cost,
            "costMap": cost_map,
            "icon": icon,
            "output": output,
            "vp": vp,
            "effects": effects,
            "oneTime": one_time,
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
