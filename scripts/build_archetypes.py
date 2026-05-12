#!/usr/bin/env python3
"""
Build src/data/archetypes.json from trait.xml (TRAIT_*_ARCHETYPE entries) +
text-trait.xml + effectPlayer/effectCity/effectUnit (for the per-leader and
per-general bonuses).

The 10 character archetypes — Hero, Commander, Tactician, Zealot, Schemer,
Orator, Diplomat, Judge, Builder, Scholar — are modeled in trait.xml as
TRAIT_<NAME>_ARCHETYPE entries with `bArchetype>1`. For each we collect:

  • Name and signature character rating contribution (aiRating: e.g. +3 Courage)
  • Favored law (aiLawOpinion: +20 opinion to that law)
  • The "opposite" archetype that gets -60 opinion (aiTraitOpinion)
  • Job-prereq flags (bGeneralPrereq, bGovernorPrereq, bAgentPrereq)
  • Leader effects (humanized from LeaderEffectPlayer)
  • General/Governor effects when filling those slots (EffectUnit / EffectCity)
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_city, render_effect_unit,
    render_effect_player_scalars, render_nation_effects,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "archetypes.json"


RATING_LABELS: dict[str, str] = {
    "RATING_WISDOM":     "Wisdom",
    "RATING_CHARISMA":   "Charisma",
    "RATING_COURAGE":    "Courage",
    "RATING_DISCIPLINE": "Discipline",
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


# Canonical archetype order matching the spreadsheet (generals first, then governors,
# with the lone Schemer at the end).
ARCHETYPE_ORDER = [
    "TRAIT_COMMANDER_ARCHETYPE",
    "TRAIT_HERO_ARCHETYPE",
    "TRAIT_TACTICIAN_ARCHETYPE",
    "TRAIT_ZEALOT_ARCHETYPE",
    "TRAIT_BUILDER_ARCHETYPE",
    "TRAIT_DIPLOMAT_ARCHETYPE",
    "TRAIT_JUDGE_ARCHETYPE",
    "TRAIT_ORATOR_ARCHETYPE",
    "TRAIT_SCHOLAR_ARCHETYPE",
    "TRAIT_SCHEMER_ARCHETYPE",
]


# Archetype-specific EffectPlayer scalar fields not yet covered by the general
# humanizer. Captioned for the page.
ARCHETYPE_SCALAR_LABELS: list[tuple[str, str, str]] = [
    ("iXPAllTurn",                  "XP/Turn for all Units",          "int"),
    ("iVisionChange",               "Vision Range",                    "int"),
    ("iLeaderReligionOpinionChange","Opinion for Leader's Religion",   "pct"),
    ("iReligionOpinionChange",      "All Religion Opinion",            "pct"),
    ("iLeaderOpinionChange",        "Foreign/Tribal Leader Opinion",   "pct"),
    ("bRecruitMercenaries",         "Recruit Tribal Mercs",            "bool"),
    ("bRedrawTechs",                "Redraw Techs",                    "bool"),
    ("bAddUrban",                   "Add Urban Tile for Stone",        "bool"),
    ("bMultipleWorkers",            "Multiple Workers per Construction", "bool"),
    ("bLegitimacyOrders",           "Spend Legitimacy for Orders",     "bool"),
    ("bMoveAlliedUnits",            "Can Move Allied Units",           "bool"),
    ("iSwitchLawMaximum",           "Civics to Switch Laws",           "int"),
    ("bUpgradeImprovement",         "Can Upgrade Improvements",        "bool"),
]


def render_archetype_effect_player(ep: ET.Element | None, indexes: dict) -> list[str]:
    """Render an EFFECTPLAYER_TRAIT_*_ARCHETYPE entry, including fields the
    standard humanizer doesn't cover yet."""
    if ep is None:
        return []
    out: list[str] = []

    # Pull in the standard renderer's coverage first
    out.extend(render_effect_player_scalars(ep))

    # Archetype-specific scalars
    for tag, label, kind in ARCHETYPE_SCALAR_LABELS:
        v = ep.findtext(tag)
        if v is None or v == "" or v == "0":
            continue
        if kind == "bool" and v == "1":
            out.append(label)
        elif kind == "pct":
            iv = int(v)
            sign = "+" if iv > 0 else ""
            out.append(f"{sign}{iv}% {label}")
        elif kind == "int":
            iv = int(v)
            sign = "+" if iv > 0 else ""
            out.append(f"{sign}{iv} {label}")

    # War yields (Schemer: +1 Orders/War/Year)
    for pair in ep.findall("aiWarYield/Pair"):
        y = (pair.findtext("zIndex") or "").replace("YIELD_", "").title()
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"+{v} {y}/Year per War")

    # Invisible units (Schemer: Scouts invisible)
    for u in ep.findall("aeInvisibleUnit/zValue"):
        if u.text:
            name = u.text.replace("UNIT_", "").title()
            out.append(f"{name}s are Invisible")

    # Per-unit-trait effect bundles (Commander: +x to Infantry; Tactician: +x to Ranged)
    for pair in ep.findall("aeEffectUnitTrait/Pair"):
        ut = (pair.findtext("zIndex") or "").replace("UNITTRAIT_", "").title()
        eu_id = pair.findtext("zValue") or ""
        eu = indexes.get("effectUnit.xml", {}).get(eu_id)
        if eu is None:
            continue
        sm = eu.findtext("iStrengthModifier") or "0"
        if sm and sm != "0":
            sign = "+" if int(sm) > 0 else ""
            out.append(f"{ut} units {sign}{sm}% Strength")
        am = eu.findtext("iAdjacentModifier") or "0"
        if am and am != "0":
            sign = "+" if int(am) > 0 else ""
            out.append(f"{ut} units {sign}{am}% with adjacent ally")
        # Heal / hidden flags
        if (eu.findtext("bHealNeutral") or "0") == "1":
            out.append(f"{ut} units heal in neutral territory")
        if (eu.findtext("bHiddenForest") or "0") == "1":
            out.append(f"{ut} units hidden in forest")

    # The EffectCity attached to a leader-only EffectPlayer (Builder, Orator, Scholar)
    ec_id = ep.findtext("EffectCity") or ""
    if ec_id:
        ec = indexes.get("effectCity.xml", {}).get(ec_id)
        if ec is not None:
            out.extend(render_effect_city(ec, per_city=False, indexes=indexes))

    # State-religion effect (Zealot)
    sec_id = ep.findtext("StateReligionEffectCity") or ""
    if sec_id:
        ec = indexes.get("effectCity.xml", {}).get(sec_id)
        if ec is not None:
            for line in render_effect_city(ec, per_city=False, indexes=indexes):
                out.append(f"State Religion: {line}")

    # EffectUnit attached at leader level (Hero, Zealot — applies to all owned units)
    eu_id = ep.findtext("EffectUnit") or ""
    if eu_id:
        eu = indexes.get("effectUnit.xml", {}).get(eu_id)
        if eu is not None:
            out.extend(render_effect_unit(eu))

    # Deduplicate while preserving order
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def main() -> int:
    text_trait = load_text("text-trait.xml", "text-trait-btt.xml", "text-trait-sap.xml")
    text_law   = load_text("text-law.xml")
    text_infos = load_text("text-infos.xml")
    indexes = load_xml_indexes(XML_DIR)

    trait_idx = {e.findtext("zType"): e for e in parse("trait.xml").findall("Entry") if e.findtext("zType")}

    def name_of_trait(tid: str) -> str:
        return text_trait.get(f"TEXT_{tid}", tid.replace("TRAIT_", "").replace("_ARCHETYPE", "").title())

    archetypes: list[dict] = []

    for tid in ARCHETYPE_ORDER:
        e = trait_idx.get(tid)
        if e is None:
            continue

        name_short = tid.replace("TRAIT_", "").replace("_ARCHETYPE", "").title()
        full = name_of_trait(tid)

        # Rating contributions — e.g., Hero +3 Courage
        ratings: list[dict] = []
        for pair in e.findall("aiRating/Pair"):
            r = RATING_LABELS.get(pair.findtext("zIndex") or "", "")
            v = int(pair.findtext("iValue") or "0")
            ratings.append({"label": r, "value": v})

        # Favored laws (+20)
        favored_laws: list[dict] = []
        for pair in e.findall("aiLawOpinion/Pair"):
            law_id = pair.findtext("zIndex") or ""
            iv = int(pair.findtext("iValue") or "0")
            label = text_law.get(
                (indexes.get("law.xml", {}).get(law_id) or ET.Element("x")).findtext("Name") or "",
                law_id.replace("LAW_", "").replace("_", " ").title(),
            )
            favored_laws.append({"id": law_id, "label": label, "value": iv})

        # Opposite archetype (-60)
        opposite: dict | None = None
        for pair in e.findall("aiTraitOpinion/Pair"):
            iv = int(pair.findtext("iValue") or "0")
            tref = pair.findtext("zIndex") or ""
            if iv <= -50 and "_ARCHETYPE" in tref:
                opp_name = tref.replace("TRAIT_", "").replace("_ARCHETYPE", "").title()
                opposite = {"id": tref, "name": opp_name, "value": iv}
                break

        # Job slot eligibility flags
        slots: list[str] = []
        if (e.findtext("bGeneralPrereq") or "0") == "1":
            slots.append("General")
        if (e.findtext("bGovernorPrereq") or "0") == "1":
            slots.append("Governor")
        if (e.findtext("bAgentPrereq") or "0") == "1":
            slots.append("Agent")
        if not slots:
            slots.append("Leader")

        # Leader bonus — humanize the EffectPlayer attached to this archetype.
        # The archetype-specific renderer covers fields the general humanizer
        # doesn't (iXPAllTurn, iVisionChange, aeEffectUnitTrait, …).
        leader_effects: list[str] = []
        lep = e.findtext("LeaderEffectPlayer") or ""
        if lep:
            leader_effects = render_archetype_effect_player(
                indexes.get("effectPlayer.xml", {}).get(lep), indexes
            )

        # Governor bonus — humanize the GovernorEffectCity
        governor_effects: list[str] = []
        gec = e.findtext("GovernorEffectCity") or ""
        if gec:
            ec = indexes.get("effectCity.xml", {}).get(gec)
            if ec is not None:
                governor_effects = render_effect_city(ec, per_city=False, indexes=indexes)

        # General bonus — GeneralEffectUnit + LeaderEffectUnit. The general
        # humanizer covers pillage/kill/fatigue; below we also handle the
        # bool flags specific to archetype generals (bHealNeutral, etc.).
        general_effects: list[str] = []
        for tag in ("GeneralEffectUnit", "LeaderEffectUnit"):
            eu_id = e.findtext(tag) or ""
            if not eu_id:
                continue
            eu = indexes.get("effectUnit.xml", {}).get(eu_id)
            if eu is None:
                continue
            general_effects.extend(render_effect_unit(eu))
            if (eu.findtext("bHealNeutral") or "0") == "1":
                general_effects.append("Heals in Neutral Territory")
            if (eu.findtext("bHealPillage") or "0") == "1":
                general_effects.append("Heals while Pillaging")
            if (eu.findtext("bLaunchOffensive") or "0") == "1":
                general_effects.append("Can Launch Offensive")
            if (eu.findtext("bHiddenForest") or "0") == "1":
                general_effects.append("Hidden in Forest")
            asm = eu.findtext("iAdjacentSameModifier") or "0"
            if asm and asm != "0":
                sign = "+" if int(asm) > 0 else ""
                general_effects.append(f"{sign}{asm}% Strength when adjacent to same unit")
            stun = eu.findtext("bStunTarget") or "0"
            if stun == "1":
                general_effects.append("Stuns target on attack")
            ftc = eu.findtext("bFullMeleeCounter") or "0"
            if ftc == "1":
                general_effects.append("Full Melee Counterattack")
            survive = eu.findtext("bSurviveDeath") or "0"
            if survive == "1":
                general_effects.append("Cannot die with >1 HP")
        # Deduplicate
        seen_g: set[str] = set()
        general_effects = [x for x in general_effects if not (x in seen_g or seen_g.add(x))]

        # Misc scalar modifiers visible on the archetype
        misc: list[str] = []
        for tag, label in [
            ("iUnitBuildModifier",      "Unit Build Cost"),
            ("iWarModifier",            "War Probability"),
            ("iPeaceModifier",          "Peace Probability"),
            ("iTruceModifier",          "Truce Probability"),
            ("iAllianceModifier",       "Alliance Probability"),
            ("iTribeAllianceModifier",  "Tribe Alliance Probability"),
            ("iOpinionSame",            "Opinion to Same"),
        ]:
            v = e.findtext(tag) or "0"
            if v and v != "0":
                iv = int(v)
                sign = "+" if iv > 0 else ""
                misc.append(f"{label} {sign}{iv}%")

        archetypes.append({
            "id": tid,
            "slug": name_short.lower(),
            "name": name_short,
            "fullName": full,
            "ratings": ratings,
            "favoredLaws": favored_laws,
            "opposite": opposite,
            "slots": slots,
            "leaderEffects": leader_effects,
            "governorEffects": governor_effects,
            "generalEffects": general_effects,
            "misc": misc,
            "iconName": e.findtext("zIconName") or "",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(archetypes, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(archetypes)} archetypes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
