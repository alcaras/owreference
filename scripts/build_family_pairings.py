#!/usr/bin/env python3
"""
Build src/data/family_pairings.json — which nations can field which family
CLASSES together.

Answers "which nations have classes X and Y (and Z)?" for every unordered
pair (C(10,2) = 45) and trio (C(10,3) = 120) of family classes, including the
combos no nation has. Trios matter because a player can only ever start
MAX_FAMILIES = 3 families (globalsInt.xml; enforced in
Player.canFoundCityFamily, surfaced in-game as
TEXT_HELPTEXT_WIDGET_FOUND_CITY_MAX_FAMILIES "Max Families: {0}/{1}").

A nation "has" a combo iff its family roster (family.xml) contains at least
one family of each class in the combo. Nothing here is hand-typed: classes
come from familyClass.xml (in file order), rosters from family.xml, playable
nations from nation.xml, names from the text XML, DLC labels from
additionalContent.xml.

Assumes default setup — the Randomize Families game option
(GAMEOPTION_RANDOMIZE_FAMILIES, Game.setupNew) reassigns each family's class
at random.
"""
from __future__ import annotations

import itertools
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import load_xml_indexes, _lookup_name  # noqa: E402
from build_families import parse, XML_DIR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "family_pairings.json"


def family_nation(entry: ET.Element) -> str:
    """Nation id a family.xml entry belongs to.

    Same rule as build_families.families_by_nation_class: abNation is
    canonical; TeamColor is only a fallback because family.xml spells
    Yuezhi's team colour TEAMCOLOR_NATION_YEUZHI (typo) while the nation is
    NATION_YUEZHI.
    """
    for p in entry.findall("abNation/Pair"):
        if (p.findtext("bValue") or "0") == "1":
            return p.findtext("zIndex") or ""
    tc = entry.findtext("TeamColor") or ""
    if tc.startswith("TEAMCOLOR_NATION_"):
        return tc.replace("TEAMCOLOR_", "")
    return ""


def dlc_labels(indexes: dict) -> dict[str, str]:
    """GameContentRequired token → DLC display name, from additionalContent.xml
    (each DLC lists the content tokens it enables under aeGameContent)."""
    out: dict[str, str] = {}
    for e in parse("additionalContent.xml").findall("Entry"):
        name = _lookup_name(indexes, e.findtext("Name") or "")
        if not name:
            continue
        for v in e.findall("aeGameContent/zValue"):
            if v.text:
                out.setdefault(v.text, name)
    return out


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    dlc = dlc_labels(indexes)

    # MAX_FAMILIES — the cap on families a player can start (Player.cs).
    max_families = 0
    for e in parse("globalsInt.xml").findall("Entry"):
        if (e.findtext("zType") or "") == "MAX_FAMILIES":
            max_families = int(e.findtext("iValue") or "0")
    if max_families <= 0:
        print("✗ globalsInt.xml has no MAX_FAMILIES", file=sys.stderr)
        return 1

    # Classes, in familyClass.xml order (canonical order for every combo).
    classes: list[dict] = []
    for e in parse("familyClass.xml").findall("Entry"):
        cid = e.findtext("zType") or ""
        if not cid:
            continue
        slug = cid.replace("FAMILYCLASS_", "").lower()
        classes.append({
            "id": cid,
            "slug": slug,
            "name": _lookup_name(indexes, e.findtext("Name") or "") or slug.title(),
            "icon": f"img/archetypes/{slug}.png",
        })
    class_slug = {c["id"]: c["slug"] for c in classes}
    class_order = [c["slug"] for c in classes]

    # Playable nations — same rule build_data.py applies to nations.json.
    nations: list[dict] = []
    roster: dict[str, set[str]] = {}
    for e in parse("nation.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt.startswith("NATION_"):
            continue
        playable = e.findtext("bPlayable")
        if not (playable == "1" or playable is None):
            continue
        text_key = (e.findtext("GenderedName") or "").replace("GENDERED_", "")
        gc = e.findtext("GameContentRequired") or ""
        nations.append({
            "id": zt,
            "slug": zt.replace("NATION_", "").lower(),
            "name": _lookup_name(indexes, text_key) or zt.replace("NATION_", "").title(),
            "gameContent": gc,
            "gameContentName": dlc.get(gc, gc.replace("_", " ").title()) if gc else "",
        })
        roster[zt] = set()

    # Rosters from family.xml. The file has one blank template entry (no
    # zType / FamilyClass) — skip it.
    for e in parse("family.xml").findall("Entry"):
        cid = e.findtext("FamilyClass") or ""
        if not (e.findtext("zType") or "") or cid not in class_slug:
            continue
        nation = family_nation(e)
        if nation in roster:
            roster[nation].add(class_slug[cid])

    nations.sort(key=lambda n: n["name"])
    for n in nations:
        n["classSlugs"] = [s for s in class_order if s in roster[n["id"]]]
    slug_by_name = [n["slug"] for n in nations]  # already name-sorted

    def combos(k: int) -> list[dict]:
        out: list[dict] = []
        for combo in itertools.combinations(class_order, k):
            need = set(combo)
            have = [n["slug"] for n in nations if need <= roster[n["id"]]]
            have.sort(key=slug_by_name.index)
            out.append({"classes": list(combo), "nations": have})
        return out

    pairs = combos(2)
    trios = combos(3)

    data = {
        "classes": classes,
        "maxFamilies": max_families,
        "nations": nations,
        "pairs": pairs,
        "trios": trios,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    fielded_p = sum(1 for p in pairs if p["nations"])
    fielded_t = sum(1 for t in trios if t["nations"])
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(classes)} classes, {len(nations)} nations, "
          f"{len(pairs)} pairs ({fielded_p} fielded), {len(trios)} trios ({fielded_t} fielded), "
          f"max families {max_families}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
