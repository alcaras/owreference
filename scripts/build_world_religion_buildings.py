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
    world_religions,
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

# World-religion list comes from humanize.world_religions(XML_DIR) — derived
# from religion.xml (SpreadUnit present), never hardcoded.


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


# NOTE: iLegitimacy used to be rendered here as a local extra; it now comes
# from the registry backstop inside render_effect_city — a local copy would
# duplicate the line.


def render_effect_player_holy_site(ep: ET.Element) -> list[str]:
    """Holy sites mostly grant a VP and an achievement."""
    out: list[str] = []
    vp = ep.findtext("iVP")
    if vp and vp != "0":
        out.append(f"{fmt_decimal(int(vp))} Victory Points")
    return out


def main() -> int:
    # text-eoti.xml carries the Empires of the Indus names (Hindu Matha /
    # Mandir / Shikhara); text-new.xml is a later-additions overflow file.
    text_improvement = load_text(XML_DIR, "text-improvement.xml", "text-eoti.xml", "text-new.xml")
    text_religion = load_text(XML_DIR, "text-religion.xml")
    indexes = load_xml_indexes(XML_DIR)

    # Index improvements by (Class, ReligionPrereq) for quick lookup.
    imp_by_key: dict[tuple[str, str], ET.Element] = {}
    for entry in parse("improvement.xml").findall("Entry"):
        cls = entry.findtext("Class") or ""
        rel = entry.findtext("ReligionPrereq") or ""
        if cls in {c[0] for c in CLASSES} and rel:
            imp_by_key[(cls, rel)] = entry

    wr = world_religions(XML_DIR)

    religions: list[dict] = []
    for rid, default_name, quirks in wr:
        religions.append({
            "id": rid,
            "slug": rid.replace("RELIGION_", "").lower(),
            "name": text_religion.get(f"TEXT_{rid}", default_name),
            "dlc": quirks["dlc"],
            "noSpread": quirks["noSpread"],
            "forceTheologies": quirks["forceTheologies"],
            "paganNations": quirks["paganNations"],
        })

    rows: list[dict] = []
    for cls_id, cls_label, cls_short in CLASSES:
        cells: list[dict | None] = []
        for rid, _, _quirks in wr:
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
