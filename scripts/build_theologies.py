#!/usr/bin/env python3
"""
Build src/data/theologies.json from theology.xml + effectCity.xml + religion.xml.

Theologies in Old World are a universal global pool of 8 picks, organised by
tier (0/1/2). All World Religions draw from the same pool — when you found a
theology you must have a World Religion as your State Religion, and its
effect applies globally to followers of that religion (and competing
religions get blocked from the same slot).

Spreadsheet intent: render one section per religion + a shared theology
matrix. Since the XML is religion-agnostic (no per-religion theology link),
we render a single canonical theology table with the 5 World Religions
listed as the audience banner.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_city, load_text, fmt_decimal,
    world_religions,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "theologies.json"


# Religion list is derived from religion.xml — see humanize.world_religions.


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


# NOTE: iRebelProb / aiYieldRateReligion used to be rendered here as local
# extras; render_effect_city covers both (curated + registry backstop), so a
# local copy would duplicate the lines.


def main() -> int:
    text_infos = load_text(XML_DIR, "text-infos.xml")
    text_tech = load_text(XML_DIR, "text-tech.xml")
    text_law = load_text(XML_DIR, "text-law.xml")
    text_religion = load_text(XML_DIR, "text-religion.xml")
    indexes = load_xml_indexes(XML_DIR)

    # Religion meta — names, spread %, cost, requirements (lets the
    # religious-conversion page reuse the same canonical data).
    religion_entries = {e.findtext("zType"): e for e in parse("religion.xml").findall("Entry") if e.findtext("zType")}
    religions: list[dict] = []
    for rid, default_name, quirks in world_religions(XML_DIR):
        nm = text_religion.get(f"TEXT_{rid}", default_name)
        re_e = religion_entries.get(rid)
        spread = int(re_e.findtext("iSpreadPercent") or "0") if re_e is not None else 0
        cost_base = int(re_e.findtext("iCostBase") or "0") if re_e is not None else 0
        cost_per_change = int(re_e.findtext("iCostPerChange") or "0") if re_e is not None else 0
        req_citizens = int(re_e.findtext("iRequiresCitizens") or "0") if re_e is not None else 0
        req_theologies = int(re_e.findtext("iRequiresTheologies") or "0") if re_e is not None else 0
        req_tech = (re_e.findtext("RequiresTech") or "") if re_e is not None else ""
        req_law = (re_e.findtext("RequiresLaw") or "") if re_e is not None else ""
        req_religions: list[dict] = []
        if re_e is not None:
            for pair in re_e.findall("aiRequiresReligion/Pair"):
                req_religions.append({
                    "id": pair.findtext("zIndex") or "",
                    "count": int(pair.findtext("iValue") or "0"),
                })
        req_specialists: list[dict] = []
        if re_e is not None:
            for pair in re_e.findall("aiRequiresSpecialist/Pair"):
                req_specialists.append({
                    "id": pair.findtext("zIndex") or "",
                    "label": (pair.findtext("zIndex") or "").replace("SPECIALIST_", "").replace("_", " ").title(),
                    "count": int(pair.findtext("iValue") or "0"),
                })
            for pair in re_e.findall("aiRequiresSpecialistClass/Pair"):
                req_specialists.append({
                    "id": pair.findtext("zIndex") or "",
                    "label": (pair.findtext("zIndex") or "").replace("SPECIALISTCLASS_", "").replace("_", " ").title(),
                    "count": int(pair.findtext("iValue") or "0"),
                })

        religions.append({
            "id": rid,
            "slug": rid.replace("RELIGION_", "").lower(),
            "name": nm,
            "spreadPercent": spread,
            "costBase": cost_base,
            "costPerChange": cost_per_change,
            "requiresCitizens": req_citizens,
            "requiresTheologies": req_theologies,
            "requiresTech": req_tech,
            "requiresLaw": req_law,
            "requiresReligions": req_religions,
            "requiresSpecialists": req_specialists,
            "dlc": quirks["dlc"],
            "noSpread": quirks["noSpread"],
            "forceTheologies": quirks["forceTheologies"],
            "paganNations": quirks["paganNations"],
        })

    # Theology entries, grouped by iTier (0,1,2).
    theologies_by_tier: dict[int, list[dict]] = {0: [], 1: [], 2: []}

    for e in parse("theology.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        name = text_infos.get(e.findtext("Name") or "", zt.replace("THEOLOGY_", "").title())
        tier = int(e.findtext("iTier") or "0")
        cost = int(e.findtext("iCost") or "0")
        spread = int(e.findtext("iSpreadChange") or "0")
        tech_prereq = e.findtext("TechPrereq") or ""
        tech_label = ""
        if tech_prereq:
            tech_entry = indexes.get("tech.xml", {}).get(tech_prereq)
            if tech_entry is not None:
                tech_label = text_tech.get(tech_entry.findtext("Name") or "",
                                            tech_prereq.replace("TECH_", "").title())

        # Per-city effects from EffectCity (apply in every city following
        # the religion once the theology is adopted).
        effects: list[str] = []
        ec_id = e.findtext("EffectCity") or ""
        if ec_id:
            ec = indexes.get("effectCity.xml", {}).get(ec_id)
            if ec is not None:
                effects.extend(render_effect_city(ec, per_city=True, indexes=indexes))

        # Building-conditional effects: improvementClass.xml
        # aeTheologyCityEffect wires a theology to an extra EffectCity that
        # only applies in cities with that worship building (e.g. Redemption
        # → Cathedral can hurry Specialists/Projects with Training).
        building_effects: list[dict] = []
        for ic_entry in parse("improvementClass.xml").findall("Entry"):
            for pair in ic_entry.findall("aeTheologyCityEffect/Pair"):
                if (pair.findtext("zIndex") or "") != zt:
                    continue
                bec_id = pair.findtext("zValue") or ""
                bec = indexes.get("effectCity.xml", {}).get(bec_id)
                if bec is None:
                    continue
                ic_id = ic_entry.findtext("zType") or ""
                bec_lines = render_effect_city(bec, per_city=True, indexes=indexes)
                if not bec_lines:
                    # Empty marker (Enlightenment's cathedral hook carries no
                    # XML payload anywhere) — nothing honest to show.
                    continue
                building_effects.append({
                    "building": ic_id.replace("IMPROVEMENTCLASS_", "").title(),
                    "effects": bec_lines,
                })

        # Per-theology law opinion bonus (e.g., Mythology favors Polytheism).
        law_op: list[dict] = []
        for pair in e.findall("aiLawOpinion/Pair"):
            law_id = pair.findtext("zIndex") or ""
            iv = int(pair.findtext("iValue") or "0")
            label = text_law.get(
                f"TEXT_{law_id}",
                law_id.replace("LAW_", "").replace("_", " ").title(),
            )
            law_op.append({"id": law_id, "label": label, "value": iv})

        theologies_by_tier.setdefault(tier, []).append({
            "id": zt,
            "slug": zt.replace("THEOLOGY_", "").lower(),
            "name": name,
            "tier": tier,
            "cost": cost,
            "spreadChange": spread,
            "techPrereq": tech_prereq,
            "techLabel": tech_label,
            "effects": effects,
            "buildingEffects": building_effects,
            "lawOpinion": law_op,
        })

    # Sort each tier by name for stable output.
    tiers: list[dict] = []
    for tier in sorted(theologies_by_tier.keys()):
        items = sorted(theologies_by_tier[tier], key=lambda x: x["name"])
        tiers.append({
            "tier": tier,
            "label": f"Tier {tier + 1}",  # display 1-indexed
            "theologies": items,
        })

    out_obj = {
        "religions": religions,
        "tiers": tiers,
        "totals": {
            "theologies": sum(len(t["theologies"]) for t in tiers),
            "religions": len(religions),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out_obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — "
          f"{out_obj['totals']['theologies']} theologies across "
          f"{len(tiers)} tiers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
