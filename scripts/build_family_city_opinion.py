#!/usr/bin/env python3
"""Build src/data/family_city_opinion.json — the three city-count terms of
family opinion (Most Cities / Fewest Cities / Envy).

None of this is a table in the XML: the engine recomputes it every time a city
changes hands, in Player.calculateFamilyOpinion{MostCities,FewestCities,Envy}
(PlayerOpinion.cs). We emit the *inputs* — the globals, the per-class extras,
the bracket thresholds — so the page can replay the three routines client-side
for any split of cities the reader types in.

    Most Cities    (familyClass.iMostCitiesOpinion + MOST_CITIES_OPINION)
                   / (number of families tied at the top), and nothing at all
                   when every family is tied.
    Fewest Cities  same shape with FEWEST_CITIES_OPINION, tie at the bottom.
    Envy           triangle(mostCities - (ourCities + 1)) * ENVY_OPINION,
                   i.e. nothing until you are two cities behind the leader,
                   then -20, -60, -120, -200 … (Utils.triangle).

Only Landowners carry class extras today (+40 / -40, doubling both terms); the
Champions pair (largest/smallest military) is the same mechanic on unit counts
and is emitted alongside for context.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "family_city_opinion.json"

WANTED_GLOBALS = [
    "MOST_CITIES_OPINION",
    "FEWEST_CITIES_OPINION",
    "ENVY_OPINION",
    "MAX_FAMILIES",
]

BRACKET_ORDER = ["FURIOUS", "ANGRY", "UPSET", "CAUTIOUS", "PLEASED", "FRIENDLY"]


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text(*filenames: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Returns ({key: first form}, {key: all ~-separated forms})."""
    first: dict[str, str] = {}
    forms: dict[str, list[str]] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").strip()
            if k and k not in first:
                parts = [f.strip() for f in en.split("~")]
                first[k] = parts[0]
                forms[k] = parts
    return first, forms


def strip_links(text: str, forms: dict[str, list[str]]) -> str:
    """`link(CONCEPT_OPINION_FAMILY,3)` → `Opinion`.

    The trailing number is a *form index* into the token's own ~-separated
    TEXT entry ("Opinion: Family~Family Opinion~Family Opinions~Opinion"), not
    decoration — humanize.py's blanket title-casing would render this one as
    "Opinion Family". Falls back to the title-cased token when the form is
    missing, which is what humanize does for every other link.
    """
    def sub(m: "re.Match[str]") -> str:
        token, _, idx = m.group(1).partition(",")
        token = token.strip()
        variants = forms.get(f"TEXT_{token}") or forms.get(token) or []
        if variants:
            i = int(idx) if idx.strip().isdigit() else 0
            if i < len(variants):
                return variants[i]
            return variants[0]
        return re.sub(r"^(CONCEPT|TEXT)_", "", token).replace("_", " ").title()

    text = re.sub(r"\{lowercase:link\(([^)]*)\)\}", lambda m: sub(m).lower(), text)
    text = re.sub(r"link\(([^)]*)\)", sub, text)
    text = re.sub(r"</?[a-z]+>", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def main() -> int:
    text, forms = load_text(
        "text-infos.xml", "text-helptext.xml", "text-family.xml",
        "text-family-hittite.xml", "text-nation.xml", "text-concept.xml",
    )

    globals_int = {}
    for e in parse("globalsInt.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if z in WANTED_GLOBALS:
            globals_int[z] = int(e.findtext("iValue") or "0")

    colors: dict[str, str] = {}
    for e in parse("color.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        hexv = (e.findtext("zHexValue") or "").strip()
        if z and hexv:
            colors[z] = hexv[:7] if re.fullmatch(r"#[0-9a-fA-F]{8}", hexv) else hexv

    # ── family classes: which ones bend the city terms ────────────────
    classes = []
    for e in parse("familyClass.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        slug = z.replace("FAMILYCLASS_", "").lower()
        classes.append({
            "id": z,
            "name": text.get(f"TEXT_{z}", slug.title()),
            "slug": slug,
            "icon": f"img/archetypes/{slug}.png",
            "mostCities": int(e.findtext("iMostCitiesOpinion") or "0"),
            "fewestCities": int(e.findtext("iFewestCitiesOpinion") or "0"),
            "largestMilitary": int(e.findtext("iLargestMilitaryOpinion") or "0"),
            "smallestMilitary": int(e.findtext("iSmallestMilitaryOpinion") or "0"),
        })
    class_by_id = {c["id"]: c for c in classes}

    # ── nations → their families (name, class, in-game color) ─────────
    # Same abNation-first rule as build_data.py: family.xml's TeamColor spells
    # Yuezhi "YEUZHI", so TeamColor is only a fallback.
    family_hex: dict[tuple[str, int], str] = {}
    for z, hexv in colors.items():
        m = re.fullmatch(r"COLOR_(NATION_[A-Z_]+)_FAMILY_(\d+)", z)
        if m:
            family_hex[(m.group(1), int(m.group(2)))] = hexv.lower()
            if m.group(1) == "NATION_YEUZHI":
                family_hex[("NATION_YUEZHI", int(m.group(2)))] = hexv.lower()

    by_nation: dict[str, list[dict]] = {}
    for e in parse("family.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        nation = ""
        for p in e.findall("abNation/Pair"):
            if (p.findtext("bValue") or "0") == "1":
                nation = p.findtext("zIndex") or ""
                break
        tc = e.findtext("TeamColor") or ""
        if not nation and tc.startswith("TEAMCOLOR_NATION_"):
            nation = tc.replace("TEAMCOLOR_", "")
        if not nation:
            continue
        cls = e.findtext("FamilyClass") or ""
        cls_info = class_by_id.get(cls, {})
        slot = int(e.findtext("iColorIndex") or "0") + 1  # XML slots are 1-based
        by_nation.setdefault(nation, []).append({
            "id": z,
            "name": text.get(e.findtext("Name") or "", z.replace("FAMILY_", "").title()),
            "classId": cls,
            "className": cls_info.get("name", cls.replace("FAMILYCLASS_", "").title()),
            "classSlug": cls_info.get("slug", ""),
            "icon": cls_info.get("icon", ""),
            "color": family_hex.get((nation, slot), "#7d8590"),
            "mostCities": cls_info.get("mostCities", 0),
            "fewestCities": cls_info.get("fewestCities", 0),
        })

    nations = []
    for e in parse("nation.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z.startswith("NATION_") or z not in by_nation:
            continue
        key = (e.findtext("GenderedName") or "").replace("GENDERED_", "")
        nations.append({
            "id": z,
            "name": text.get(key, z.replace("NATION_", "").title()),
            "slug": z.replace("NATION_", "").lower(),
            "families": by_nation[z],
        })
    nations.sort(key=lambda n: n["name"])

    # ── opinion brackets (thresholds + in-game color) ─────────────────
    brackets = []
    for e in parse("opinionFamily.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        key = z.split("_")[-1]
        if key not in BRACKET_ORDER:
            continue
        raw = e.findtext("iThreshold")
        brackets.append({
            "id": z,
            "bracket": key,
            "label": text.get(e.findtext("Name") or "", key.title()),
            "threshold": int(raw) if raw else None,
            "color": colors.get(e.findtext("Color") or "", "#7d8590"),
        })
    brackets.sort(key=lambda b: BRACKET_ORDER.index(b["bracket"]))
    for i, b in enumerate(brackets):
        lo = brackets[i - 1]["threshold"] + 1 if i > 0 else None
        b["min"] = lo
        b["max"] = b["threshold"]

    out = {
        "brackets": brackets,
        "classes": classes,
        "globals": globals_int,
        "help": {
            "envy": strip_links(text.get("TEXT_HELPTEXT_LINK_HELP_ENVY", ""), forms),
            "envyName": text.get("TEXT_CONCEPT_ENVY", "Envy"),
            "mostCities": text.get("TEXT_HELPTEXT_LINK_MOST_CITIES", "Most Cities"),
            "fewestCities": text.get("TEXT_HELPTEXT_LINK_FEWEST_CITIES", "Fewest Cities"),
        },
        "nations": nations,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    fams = sum(len(n["families"]) for n in nations)
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(nations)} nations, {fams} families, "
          f"{len(brackets)} brackets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
