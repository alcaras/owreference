#!/usr/bin/env python3
"""
Build src/data/specialists.json from specialist.xml + specialistClass.xml
+ effectCity.xml. Each entry: name, tier (1/2/3 or just '—' for rural),
yield output from EffectCity (humanized), what kind of improvement they
slot into, civics cost, and food cost.

The 'apprentice / master / elder' family progression is encoded via
EffectCityExtra (APPRENTICE→MASTER→ELDER); together with EffectCity it
fully determines tier output.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, fmt_decimal, yield_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "specialists.json"


def load_text(*filenames: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for entry in ET.parse(p).getroot().findall("Entry"):
            k = entry.findtext("zType") or ""
            en = (entry.findtext("en-US") or "").split("~")[0].strip()
            if k:
                out[k] = en
    return out


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def render_yields(e: ET.Element) -> list[str]:
    """Render all yield-bearing fields on an effectCity entry."""
    out: list[str] = []
    if e is None:
        return out
    for pair in e.findall("aiYieldRate/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"{fmt_decimal(v)} {y}")
    for pair in e.findall("aiYieldModifier/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% {y}")
    return out


def main() -> int:
    text_idx = load_text("text-infos.xml")
    indexes = load_xml_indexes(XML_DIR)

    spec_root = parse("specialist.xml")
    # Map improvement classes that grant which specialist (built from improvement.xml).
    imp_root = parse("improvement.xml")
    spec_to_imp_classes: dict[str, list[str]] = {}
    for ie in imp_root.findall("Entry"):
        s = ie.findtext("Specialist") or ""
        cls = ie.findtext("Class") or ""
        if s and cls:
            spec_to_imp_classes.setdefault(s, [])
            if cls not in spec_to_imp_classes[s]:
                spec_to_imp_classes[s].append(cls)

    items: list[dict] = []
    for e in spec_root.findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue

        name = text_idx.get(e.findtext("Name") or "", zt.replace("SPECIALIST_", "").replace("_", " ").title())
        cls = e.findtext("Class") or ""
        class_token = cls.replace("SPECIALISTCLASS_", "").title()

        # Tier: 1/2/3 if name ends with _1/_2/_3, else 'rural' tier 0
        tier = 0
        for n in (1, 2, 3):
            if zt.endswith(f"_{n}"):
                tier = n
                break

        # Base icon (class-level)
        icon_token = (e.findtext("zIconName") or "").lower()
        if not icon_token:
            icon_token = class_token.lower()

        # EffectCity (per-tier flat yield)
        ec_id = e.findtext("EffectCity") or ""
        ec = indexes.get("effectCity.xml", {}).get(ec_id) if ec_id else None
        ec_extra_id = e.findtext("EffectCityExtra") or ""
        ec_extra = indexes.get("effectCity.xml", {}).get(ec_extra_id) if ec_extra_id else None

        yields_main = render_yields(ec) if ec is not None else []
        yields_extra = render_yields(ec_extra) if ec_extra is not None else []

        # Class-wide modifier (e.g., SPECIALIST_FARMER: +50% Farms)
        cls_mods: list[str] = []
        for pair in e.findall("aiImprovementClassModifier/Pair"):
            imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENTCLASS_", "").title()
            v = int(pair.findtext("iValue") or "0")
            cls_mods.append(f"{fmt_decimal(v)}% {imp}")

        # Cost
        civics = e.findtext("iCivics") or "0"
        food_cost = 0
        for pair in e.findall("aiYieldCost/Pair"):
            if (pair.findtext("zIndex") or "") == "YIELD_FOOD":
                food_cost = int(pair.findtext("iValue") or "0") / 10

        # Which improvement classes accept this specialist?
        slot_classes = spec_to_imp_classes.get(zt, [])
        # For tier-2/3 specialists, the upstream slot classes come from the
        # whole class chain (the improvement just lists tier_1) — but the
        # game allows any tier into the slot it qualifies for. Reuse tier 1's.
        if tier > 1:
            base_id = zt.rsplit("_", 1)[0] + "_1"
            slot_classes = spec_to_imp_classes.get(base_id, slot_classes)

        # Religion opinion bonus (priests, monks, acolytes get bonus per tier)
        opinion_rel = e.findtext("iOpinionReligion") or "0"

        slug = zt.replace("SPECIALIST_", "").lower()
        # Class-level slug (icon, page)
        class_slug = class_token.lower()
        items.append({
            "id": zt,
            "slug": slug,
            "name": name,
            "class": class_token,
            "classId": cls,
            "classSlug": class_slug,
            "tier": tier,
            "icon": f"img/icons/specialists/{class_slug}.png",
            "yieldsMain": yields_main,
            "yieldsExtra": yields_extra,
            "classModifiers": cls_mods,
            "civicsCost": int(civics) if civics.lstrip("-").isdigit() else 0,
            "foodCost": int(food_cost) if food_cost == int(food_cost) else food_cost,
            "religionOpinion": int(opinion_rel) if opinion_rel.lstrip("-").isdigit() else 0,
            "slotImprovementClasses": [c.replace("IMPROVEMENTCLASS_", "").title() for c in slot_classes],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(items)} specialists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
