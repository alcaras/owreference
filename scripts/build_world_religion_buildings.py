#!/usr/bin/env python3
"""
Build src/data/world_religion_buildings.json from improvement.xml.

Each World Religion (Zoroastrianism, Judaism, Christianity, Manichaeism,
Buddhism) has its own four-tier worship building chain:
  Monastery → Temple → Cathedral → Holy Site

Layout for the page: rows = building class (Monastery/Temple/Cathedral/Holy
Site), columns = religion. Each cell shows the religion-specific name, the
yield output, build cost, and (for Cathedrals/Holy Sites) the EffectCity or
EffectPlayer bonus humanized.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_city, load_text, fmt_decimal, yield_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "world_religion_buildings.json"


CLASSES = [
    ("IMPROVEMENTCLASS_MONASTERY",  "Monastery",  "MONASTERY"),
    ("IMPROVEMENTCLASS_TEMPLE",     "Temple",     "TEMPLE"),
    ("IMPROVEMENTCLASS_CATHEDRAL",  "Cathedral",  "CATHEDRAL"),
    ("IMPROVEMENTCLASS_HOLY_SITE",  "Holy Site",  "HOLY_SITE"),
]

WORLD_RELIGIONS = [
    ("RELIGION_ZOROASTRIANISM", "Zoroastrianism"),
    ("RELIGION_JUDAISM",        "Judaism"),
    ("RELIGION_CHRISTIANITY",   "Christianity"),
    ("RELIGION_MANICHAEISM",    "Manichaeism"),
    ("RELIGION_BUDDHISM",       "Buddhism"),
]


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def _clean_name(raw: str) -> str:
    """Strip `icon(RELIGION_X)` prefix and gender forms from text-improvement
    entries like `icon(RELIGION_CHRISTIANITY)Christian Monastery~...`."""
    first = raw.split("~")[0]
    # Drop leading icon(...) marker
    if first.startswith("icon("):
        end = first.find(")")
        if end != -1:
            first = first[end + 1:]
    return first.strip()


def render_outputs(entry: ET.Element) -> list[str]:
    """Render aiYieldOutput pairs as e.g. '+0.5 Culture'."""
    out: list[str] = []
    for pair in entry.findall("aiYieldOutput/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"{fmt_decimal(v)} {y}")
    return out


def render_costs(entry: ET.Element) -> list[str]:
    out: list[str] = []
    for pair in entry.findall("aiYieldCost/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{v} {y}")
    return out


def render_effect_city_extra(ec: ET.Element) -> list[str]:
    """Extra scalar fields on EffectCity that we want for Cathedrals."""
    out: list[str] = []
    leg = ec.findtext("iLegitimacy")
    if leg and leg != "0":
        out.append(f"{fmt_decimal(int(leg))} Legitimacy")
    return out


def render_effect_player_holy_site(ep: ET.Element) -> list[str]:
    """Holy sites mostly grant a VP and an achievement."""
    out: list[str] = []
    vp = ep.findtext("iVP")
    if vp and vp != "0":
        out.append(f"{fmt_decimal(int(vp))} Victory Points")
    return out


def main() -> int:
    text_improvement = load_text(XML_DIR, "text-improvement.xml")
    text_religion = load_text(XML_DIR, "text-religion.xml")
    indexes = load_xml_indexes(XML_DIR)

    # Index improvements by (Class, ReligionPrereq) for quick lookup.
    imp_by_key: dict[tuple[str, str], ET.Element] = {}
    for entry in parse("improvement.xml").findall("Entry"):
        cls = entry.findtext("Class") or ""
        rel = entry.findtext("ReligionPrereq") or ""
        if cls in {c[0] for c in CLASSES} and rel:
            imp_by_key[(cls, rel)] = entry

    religions: list[dict] = []
    for rid, default_name in WORLD_RELIGIONS:
        religions.append({
            "id": rid,
            "slug": rid.replace("RELIGION_", "").lower(),
            "name": text_religion.get(f"TEXT_{rid}", default_name),
        })

    rows: list[dict] = []
    for cls_id, cls_label, cls_short in CLASSES:
        cells: list[dict | None] = []
        for rid, _ in WORLD_RELIGIONS:
            entry = imp_by_key.get((cls_id, rid))
            if entry is None:
                cells.append(None)
                continue
            zt = entry.findtext("zType") or ""
            name_key = entry.findtext("Name") or ""
            raw_name = text_improvement.get(name_key, "")
            name = _clean_name(raw_name) if raw_name else zt.replace("IMPROVEMENT_", "").title()

            outputs = render_outputs(entry)
            costs = render_costs(entry)

            # Effects from referenced EffectCity (Cathedrals) or
            # EffectPlayer (Holy Sites).
            effects: list[str] = []
            ec_id = entry.findtext("EffectCity") or ""
            if ec_id:
                ec = indexes.get("effectCity.xml", {}).get(ec_id)
                if ec is not None:
                    effects.extend(render_effect_city(ec, per_city=True, indexes=indexes))
                    effects.extend(render_effect_city_extra(ec))
            ep_id = entry.findtext("EffectPlayer") or ""
            if ep_id:
                ep = indexes.get("effectPlayer.xml", {}).get(ep_id)
                if ep is not None:
                    effects.extend(render_effect_player_holy_site(ep))

            specialist = entry.findtext("Specialist") or ""
            specialist_label = specialist.replace("SPECIALIST_", "").replace("_", " ").title() if specialist else ""

            culture_prereq = entry.findtext("CulturePrereq") or ""
            culture_label = culture_prereq.replace("CULTURE_", "").title() if culture_prereq else ""

            cells.append({
                "id": zt,
                "name": name,
                "religion": rid.replace("RELIGION_", "").lower(),
                "outputs": outputs,
                "costs": costs,
                "effects": effects,
                "specialist": specialist_label,
                "culturePrereq": culture_label,
            })

        rows.append({
            "class": cls_id,
            "slug": cls_short.lower(),
            "label": cls_label,
            "cells": cells,
        })

    out_obj = {
        "religions": religions,
        "rows": rows,
        "totals": {
            "religions": len(religions),
            "buildings": sum(1 for r in rows for c in r["cells"] if c is not None),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out_obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — "
          f"{out_obj['totals']['buildings']} buildings across "
          f"{len(rows)} classes × {len(religions)} religions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
