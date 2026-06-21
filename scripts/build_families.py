#!/usr/bin/env python3
"""
Build src/data/families.json from familyClass.xml, effectCity.xml, bonus.xml,
family.xml. Mirrors the spreadsheet's Families tab columns (10 family classes)
with rows: city bonus, seat bonus, seat founding, opinions, preferred laws,
favored improvements, luxuries, archetype tendencies (aiTraitDie weights),
and which nations have each class.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_city, render_effect_unit, render_bonus,
    _lookup_name, fmt_decimal, _strip_link_templates,
)


def granted_traits(ec: ET.Element | None, indexes: dict) -> list[dict]:
    """Unit traits a family's cities confer on units trained there.

    Pulls aeFreeEffectUnit (all units, e.g. Champions → Steadfast) and
    aeTraitEffectUnit (a unit-trait gated grant, e.g. Hunters: Ranged →
    Sentinel), resolving each EffectUnit to its humanized effect lines so the
    detail page can explain what the trait actually does.
    """
    if ec is None:
        return []
    eu_idx = indexes.get("effectUnit.xml", {})
    out: list[dict] = []

    def add(eu_id: str, applies_to: str) -> None:
        eu = eu_idx.get(eu_id)
        if eu is None:
            return
        out.append({
            "name": eu_id.replace("EFFECTUNIT_", "").replace("_", " ").title(),
            "appliesTo": applies_to,
            "effects": render_effect_unit(eu),
        })

    for z in ec.findall("aeFreeEffectUnit/zValue"):
        if z.text:
            add(z.text, "All units")
    for pair in ec.findall("aeTraitEffectUnit/Pair"):
        trait = (pair.findtext("zIndex") or "").replace("UNITTRAIT_", "").replace("_", " ").title()
        add(pair.findtext("zValue") or "", f"{trait} units")
    return out

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "families.json"


# Scalar opinion fields → human label. Sign comes from the value itself.
OPINION_LABELS: dict[str, str] = {
    "iLargestMilitaryOpinion":     "Largest Military",
    "iSmallestMilitaryOpinion":    "Smallest Military",
    "iMostCitiesOpinion":          "Most Cities",
    "iFewestCitiesOpinion":        "Fewest Cities",
    "iSpecialistsOpinion":         "Most Specialists",
    "iLeaderNotAdultOpinion":      "Leader under 18 yo",
    "iLeaderUnmarriedOpinion":     "Unmarried Leader",
    "iLeaderForeignSpouseOpinion": "Foreign Spouse",
    "iLeaderTribeSpouseOpinion":   "Tribal Spouse",
    "iLeaderHeirOpinion":          "Patron Leader or Heir",
    "iNoCouncilOpinion":           "Not on Council",
    "iNoReligionOpinion":          "City w/o Religion",
    "iHolyCityOpinion":            "Holy Cities",
    "iWonderOpinion":              "Each Wonder",
    "iConnectedOpinion":           "Connected Cities",
    "iCityDamagedOpinion":         "Damaged Cities",
    "iCityDefendedOpinion":        "Defended Cities",
    "iGeneralOpinion":             "Each General",
    "iGovernorOpinion":            "Each Governor",
    "iHostileTribeUnitOpinion":    "Hostile Tribal Units in Territory",
    "iPillagedOpinion":            "Pillaged",
    "iLuxuryOpinion":              "Each Luxury",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text(*filenames: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").split("~")[0].strip()
            if k:
                out[k] = en
    return out


def families_by_nation_class() -> dict[str, list[str]]:
    """Reverse map: family class id → list of nation ids that have it."""
    out: defaultdict[str, set[str]] = defaultdict(set)
    for entry in parse("family.xml").findall("Entry"):
        cls = entry.findtext("FamilyClass") or ""
        # Use abNation (canonical) over TeamColor (Yuezhi typo workaround)
        nation = ""
        for p in entry.findall("abNation/Pair"):
            if (p.findtext("bValue") or "0") == "1":
                nation = p.findtext("zIndex") or ""
                break
        if not nation:
            tc = entry.findtext("TeamColor") or ""
            if tc.startswith("TEAMCOLOR_NATION_"):
                nation = tc.replace("TEAMCOLOR_", "")
        if cls and nation:
            out[cls].add(nation)
    return {k: sorted(v) for k, v in out.items()}


def main() -> int:
    text_infos = load_text("text-infos.xml")
    text_nation = load_text("text-nation.xml")
    text_law = load_text("text-law.xml")
    text_impclass = load_text("text-improvementClass.xml")
    indexes = load_xml_indexes(XML_DIR)
    nations_by_class = families_by_nation_class()

    families: list[dict] = []

    # Canonical order matching the spreadsheet (military → civic → spiritual)
    CLASS_ORDER = [
        "FAMILYCLASS_CHAMPIONS",
        "FAMILYCLASS_HUNTERS",
        "FAMILYCLASS_RIDERS",
        "FAMILYCLASS_STATESMEN",
        "FAMILYCLASS_SAGES",
        "FAMILYCLASS_PATRONS",
        "FAMILYCLASS_ARTISANS",
        "FAMILYCLASS_LANDOWNERS",
        "FAMILYCLASS_CLERICS",
        "FAMILYCLASS_TRADERS",
    ]

    fc_entries = {e.findtext("zType"): e for e in parse("familyClass.xml").findall("Entry") if e.findtext("zType")}

    for cls_id in CLASS_ORDER:
        e = fc_entries.get(cls_id)
        if e is None:
            continue
        slug = cls_id.replace("FAMILYCLASS_", "").lower()
        name = text_infos.get(e.findtext("Name") or "", slug.title())

        # City Bonus — from EffectCity
        city_bonus: list[str] = []
        ec_id = e.findtext("EffectCity")
        ec = indexes.get("effectCity.xml", {}).get(ec_id or "")
        if ec is not None:
            # Effect city for family class is applied where the family lives.
            # Render without the "/City" suffix (the class isn't per-city).
            city_bonus = render_effect_city(ec, per_city=False, indexes=indexes)
            # Scalar fields that aren't yields but matter for class identity
            sm = ec.findtext("iStrengthModifier")
            if sm and sm != "0":
                city_bonus.insert(0, f"{fmt_decimal(int(sm))}% City Defense")
            scm = ec.findtext("iSpecialistCostModifier")
            if scm and scm != "0":
                city_bonus.append(f"{fmt_decimal(int(scm))}% Specialist Cost")

        # Seat Bonus
        seat_bonus: list[str] = []
        seb_id = e.findtext("SeatEffectCity")
        seb = indexes.get("effectCity.xml", {}).get(seb_id or "")
        if seb is not None:
            seat_bonus = render_effect_city(seb, per_city=False, indexes=indexes)
            unlock = seb.findtext("EffectCityUnlock")
            if unlock:
                nice = _lookup_name(indexes, indexes.get("effectCity.xml", {}).get(unlock).findtext("Name") or "") if unlock in indexes.get("effectCity.xml", {}) else ""
                seat_bonus.append(f"Unlocks {nice or unlock.replace('EFFECTCITY_', '').replace('_', ' ').title()}")

        # Seat Founding bonus (granted when the seat city is founded)
        seat_found: list[str] = []
        sfb_id = e.findtext("SeatFoundBonus")
        sfb = indexes.get("bonus.xml", {}).get(sfb_id or "")
        if sfb is not None:
            seat_found = render_bonus(sfb, indexes)

        # Found bonus — granted each time a city of this family is founded
        # (Player.cs:16083 doBonus per city; game labels it "On City Founded").
        # Distinct from the seat-found bonus above. Only Sages has one: Archive I.
        found_bonus: list[str] = []
        fb_id = e.findtext("FoundBonus")
        fb = indexes.get("bonus.xml", {}).get(fb_id or "")
        if fb is not None:
            found_bonus = render_bonus(fb, indexes)

        # Advice / flavour blurb (the game's own family-class summary text).
        advice = ""
        adv_key = e.findtext("AdviceFound") or ""
        if adv_key and adv_key in text_infos:
            advice = _strip_link_templates(text_infos[adv_key]).strip()

        # Luxury affinities — specific luxuries that grant this family's cities an
        # extra effect when connected (aeLuxuryEffectCity, e.g. Sages: Lavender &
        # Salt → +1 Culture, +1 Happiness).
        luxury_bonuses: list[dict] = []
        for pair in e.findall("aeLuxuryEffectCity/Pair"):
            res = (pair.findtext("zIndex") or "").replace("RESOURCE_", "")
            eff_id = pair.findtext("zValue") or ""
            eff = indexes.get("effectCity.xml", {}).get(eff_id)
            effects = render_effect_city(eff, per_city=False, indexes=indexes) if eff is not None else []
            luxury_bonuses.append({
                "resource": res.lower(),
                "label": res.replace("_", " ").title(),
                "effects": effects,
            })

        # Opinion modifiers (scalar fields with known labels)
        opinions: list[dict] = []
        for tag, label in OPINION_LABELS.items():
            v = e.findtext(tag)
            if v and v != "0":
                opinions.append({"label": label, "value": int(v)})

        # Luxuries missing (negative opinion if not present in nation)
        luxuries: list[dict] = []
        for pair in e.findall("aiLuxuryMissingOpinion/Pair"):
            resource = (pair.findtext("zIndex") or "").replace("RESOURCE_", "")
            iv = int(pair.findtext("iValue") or "0")
            luxuries.append({
                "resource": resource.lower(),
                "label": resource.replace("_", " ").title(),
                "value": iv,
            })

        # Favored buildings — specific improvements (aiImprovementOpinion) plus
        # whole improvement *classes* (aiImprovementClassOpinion, e.g. Clerics
        # like the Cathedral class). The game renders both in family help text.
        favored: list[dict] = []
        for pair in e.findall("aiImprovementOpinion/Pair"):
            imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENT_", "")
            iv = int(pair.findtext("iValue") or "0")
            favored.append({
                "label": imp.replace("_", " ").title(),
                "value": iv,
            })
        for pair in e.findall("aiImprovementClassOpinion/Pair"):
            cls = pair.findtext("zIndex") or ""
            iv = int(pair.findtext("iValue") or "0")
            label = text_impclass.get(
                (indexes.get("improvementClass.xml", {}).get(cls) or ET.Element("x")).findtext("Name") or "",
                cls.replace("IMPROVEMENTCLASS_", "").replace("_", " ").title(),
            )
            favored.append({"label": label, "value": iv, "isClass": True})

        # Preferred laws (positive opinion when adopted)
        laws: list[dict] = []
        for pair in e.findall("aiLawOpinion/Pair"):
            law_id = pair.findtext("zIndex") or ""
            iv = int(pair.findtext("iValue") or "0")
            label = text_law.get(
                (indexes.get("law.xml", {}).get(law_id) or ET.Element("x")).findtext("Name") or "",
                law_id.replace("LAW_", "").replace("_", " ").title(),
            )
            laws.append({"id": law_id, "label": label, "value": iv})

        # Archetype tendencies — aiTraitDie: TRAIT_*_ARCHETYPE → die weight
        # (10 = signature, 5 = secondary, 1 = baseline). Characters born into
        # a family of this class roll their archetype on this weighted die.
        archetype_weights: dict[str, int] = {}
        for pair in e.findall("aiTraitDie/Pair"):
            trait = pair.findtext("zIndex") or ""
            weight = int(pair.findtext("iValue") or "0")
            if trait and weight:
                archetype_weights[trait] = weight

        # Nations that have this class (via family.xml mapping)
        nations = []
        for nid in nations_by_class.get(cls_id, []):
            nations.append({
                "id": nid,
                "slug": nid.replace("NATION_", "").lower(),
                "name": text_nation.get(f"TEXT_{nid}", nid.replace("NATION_", "").title()),
            })

        families.append({
            "id": cls_id,
            "slug": slug,
            "name": name,
            "widget": e.findtext("zUnitWidget") or "",
            "icon": f"img/archetypes/{slug}.png",
            "archetypeWeights": archetype_weights,
            "advice": advice,
            "cityBonus": city_bonus,
            "grantedTraits": granted_traits(ec, indexes),
            "seatBonus": seat_bonus,
            "seatFounding": seat_found,
            "foundBonus": found_bonus,
            "opinions": opinions,
            "luxuries": luxuries,
            "luxuryBonuses": luxury_bonuses,
            "favored": favored,
            "preferredLaws": laws,
            "nations": nations,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(families, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(families)} family classes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
