#!/usr/bin/env python3
"""
Build src/data/traits.json from trait.xml — the full character-trait catalog.

Every TRAIT_* entry in trait.xml, grouped into XML-native categories:

  • archetype  — bArchetype (the 10 leader archetypes; detailed on /archetypes)
  • strength   — bStrength  (personality strengths)
  • weakness   — bWeakness  (personality weaknesses)
  • item       — bItem      (event-granted heirlooms/artifacts)
  • affliction — iInjuryDie > 0 or aiMortalityDieProb present (wounds/illnesses)
  • status     — everything else (roles, clergy, story traits, pets, …)

Per trait we render what the XML expresses directly:
  • Rating deltas (aiRating, aiRatingFallback — fallback flagged as such)
  • Leader / Governor / General effects, humanized via scripts/humanize.py
    (LeaderEffectPlayer → effectPlayer tree, GovernorEffectCity, *EffectUnit)
  • Opinion effects (iOpinion* scalars, aiTraitOpinion, aiReligionOpinion,
    aiLawOpinion, aiJobOpinion, aiFamilyClassOpinion)
  • Trait relations: aeTraitReplaces (overwrites), aeTraitInvalid (blocked by),
    aiTraitProb (may progress to, e.g. Ill → 20% Severely Ill)
  • Probability/cost modifiers (war/peace/alliance, family-head odds, …)
  • Boolean restrictions (can't marry, removed-from-succession, leader-only …)
  • XML-native acquisition hints (min age, adjective/injury/barb dice,
    recovery odds, mortality risk). Most traits are granted by events —
    we deliberately do not enumerate eventStory.xml here.

Inheritance odds live on /trait-inheritance (build_trait_inheritance.py);
this page is the catalog and cross-links there.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_player, render_effect_city,
    render_effect_unit, render_bonus, fmt_decimal, yield_name, _lookup_name,
)
from build_promotions import render_promotion_effect  # noqa: E402  (full EffectUnit coverage)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "traits.json"


RATING_LABELS: dict[str, str] = {
    "RATING_WISDOM":     "Wisdom",
    "RATING_CHARISMA":   "Charisma",
    "RATING_COURAGE":    "Courage",
    "RATING_DISCIPLINE": "Discipline",
}

# UI placeholders in the archetype-picker, not real character traits.
SKIP_IDS = {
    "TRAIT_PRESET_ARCHETYPE",
    "TRAIT_RANDOM_ARCHETYPE",
    "TRAIT_PICK_LATER_ARCHETYPE",
    "TRAIT_CUSTOMIZE_LEADER_ARCHETYPE",
}

# iOpinion* scalars → label shown in the Opinions column.
OPINION_SCALARS: list[tuple[str, str]] = [
    ("iOpinion",              "Opinion of this character"),
    ("iOpinionSame",          "Same trait"),
    ("iOpinionFamily",        "Own family"),
    ("iOpinionReligion",      "Same religion"),
    ("iOpinionReligionWorld", "World religions"),
    ("iOpinionReligionPagan", "Pagan religions"),
    ("iOpinionProximity",     "Per proximity"),
    ("iOpinionStrength",      "Per military strength"),
    ("iOpinionKnowledge",     "Per tech known"),
    ("iOpinionGenerals",      "Per general"),
    ("iOpinionExplorers",     "Per explorer"),
    ("iOpinionGovernors",     "Per governor"),
    ("iOpinionWonders",       "Per wonder"),
    ("iOpinionLaws",          "Per law"),
    ("iOpinionCognomen",      "Per cognomen"),
    ("iOpinionTrades",        "Per trade"),
]

# Probability / cost % modifiers → Modifiers column.
MODIFIER_SCALARS: list[tuple[str, str]] = [
    ("iFamilyHeadModifier",    "Family Head chance"),
    ("iReligionHeadModifier",  "Religion Head chance"),
    ("iAgentModifier",         "Agent chance"),
    ("iBirthModifier",         "Birth chance"),
    ("iUnitBuildModifier",     "Unit build cost"),
    ("iWarModifier",           "War chance"),
    ("iPeaceModifier",         "Peace chance"),
    ("iTruceModifier",         "Truce chance"),
    ("iAllianceModifier",      "Alliance chance"),
    ("iTribeAllianceModifier", "Tribe alliance chance"),
    ("iStrengthLimitModifier", "Strength limit"),
    ("iWeaknessLimitModifier", "Weakness limit"),
]

# Boolean restriction / behavior flags → Flags column.
BOOL_FLAGS: list[tuple[str, str]] = [
    ("bAgeless",              "Ageless"),
    ("bNoEvents",             "No events"),
    ("bNoMissions",           "No missions"),
    ("bNoMarry",              "Cannot marry"),
    ("bNoSpouse",             "No spouse"),
    ("bNoBirth",              "No children"),
    ("bRegent",               "Regent"),
    ("bSuccessionReturn",     "Returns to succession"),
    ("bSuccessionBypass",     "Bypassed in succession"),
    ("bNoSuccession",         "Out of succession"),
    ("bNoSuccessionChildren", "Children out of succession"),
    ("bNoJob",                "Cannot hold a job"),
    ("bNoCouncil",            "No council seat"),
    ("bNoGeneral",            "Cannot be General"),
    ("bNoExplorer",           "Cannot be Explorer"),
    ("bNoGovernor",           "Cannot be Governor"),
    ("bNoCourtier",           "Cannot be Courtier"),
    ("bNoFamilyHead",         "Cannot be Family Head"),
    ("bNoReligionHeadNew",    "Cannot become Religion Head"),
    ("bNoReligion",           "Cannot adopt a religion"),
    ("bGeneralPrereq",        "Required for General"),
    ("bGeneralAll",           "All Generals have it"),
    ("bExplorerPrereq",       "Required for Explorer"),
    ("bExplorerAll",          "All Explorers have it"),
    ("bGovernorPrereq",       "Required for Governor"),
    ("bGovernorAll",          "All Governors have it"),
    ("bAgentPrereq",          "Required for Agent"),
    ("bRemoveAlways",         "Always removed"),
    ("bRemoveLeader",         "Removed on becoming Leader"),
    ("bRemoveNonLeader",      "Leader only"),
    ("bRemoveDeath",          "Removed on death"),
    ("bDoomed",               "Doomed"),
    ("bClergy",               "Clergy"),
    ("bNotable",              "Starred character"),
    ("bForceNickname",        "Forces nickname"),
]

# Trait-only EffectPlayer scalars the generic humanizer doesn't cover.
# (iReligionOpinionChange / iWonderModifier / iStateReligionSpread ARE
# covered by humanize.SCALAR_LABELS — keep them out of this list.)
TRAIT_EP_SCALARS: list[tuple[str, str, str]] = [
    ("iXPAllTurn",                   "XP/Turn for all Units",         "int"),
    ("iVisionChange",                "Vision Range",                  "int"),
    ("iLeaderReligionOpinionChange", "Opinion for Leader's Religion", "int"),
    ("iLeaderOpinionChange",         "Foreign Leader Opinion",        "int"),
    ("iTribeLeaderOpinionChange",    "Tribal Leader Opinion",         "int"),
    ("iFamilyOpinionChange",         "Family Opinion",                "int"),
    ("iLegitimacy",                  "Legitimacy",                    "int"),
    ("iSwitchLawMaximum",            "Civics to Switch Laws",         "int"),
    ("iGovernorCostModifier",        "Governor Cost",                 "pct"),
    ("bRecruitMercenaries",          "Recruit Tribal Mercs",          "bool"),
    ("bRedrawTechs",                 "Redraw Techs",                  "bool"),
    ("bAddUrban",                    "Add Urban Tile for Stone",      "bool"),
    ("bMultipleWorkers",             "Multiple Workers per Construction", "bool"),
    ("bLegitimacyOrders",            "Spend Legitimacy for Orders",   "bool"),
    ("bMoveAlliedUnits",             "Can Move Allied Units",         "bool"),
    ("bUpgradeImprovement",          "Can Upgrade Improvements",      "bool"),
]

# Extra EffectUnit fields seen on trait-attached effectUnit entries that
# neither humanize.render_effect_unit nor build_promotions covers.
UNIT_EXTRA_SCALARS: list[tuple[str, str, str]] = [
    ("iStrengthModifier",      "Strength",                       "pct"),
    ("iDefenseModifier",       "Defense",                        "pct"),
    ("iVisionExtra",           "Vision",                         "int"),
    ("iMovementExtra",         "Movement",                       "int"),
    ("iRangeExtra",            "Range",                          "int"),
    ("iRevealExtra",           "Reveal Range",                   "int"),
    ("iActionsExtra",          "Actions",                        "int"),
    ("iHealExtra",             "Healing",                        "int"),
    ("iCriticalChance",        "Critical Chance",                "pct"),
    ("iVsGeneralModifier",     "vs Units with a General",        "pct"),
    ("iHasGeneralModifier",    "Strength to Units with a General", "pct"),
    ("iUrbanAttackModifier",   "Attack vs Urban tiles",          "pct"),
    ("iDamagedThemModifier",   "vs damaged targets",             "pct"),
    ("iDamagedUsModifier",     "when damaged",                   "pct"),
    ("iHomeModifier",          "in own territory",               "pct"),
    ("iAdjacentSameModifier",  "adjacent to same unit",          "pct"),
    ("iPerLevelAttackModifier","Attack per Level",               "pct"),
    ("iFlankingAttackModifier","Flanking Attack",                "pct"),
    ("iMeleeCounterPercent",   "Melee Counter",                  "pct"),
    ("bHealNeutral",           "Heals in neutral territory",     "bool"),
    ("bHealPillage",           "Heals while pillaging",          "bool"),
    ("bHealKill",              "Heals on kill",                  "bool"),
    ("bLaunchOffensive",       "Can Launch Offensive",           "bool"),
    ("bHiddenForest",          "Hidden in forest",               "bool"),
    ("bStunTarget",            "Stuns target on attack",         "bool"),
    ("bFullMeleeCounter",      "Full melee counterattack",       "bool"),
    ("bSurviveDeath",          "Cannot die with >1 HP",          "bool"),
    ("bLastStand",             "Last Stand",                     "bool"),
    ("bCriticalImmune",        "Immune to criticals",            "bool"),
    ("bRout",                  "Can Rout",                       "bool"),
    ("bZOC",                   "Exerts Zone of Control",         "bool"),
    ("bGeneralHopping",        "General can swap units",         "bool"),
    ("bBuildRoad",             "Can build Roads",                "bool"),
    ("bHarvest",               "Can Harvest",                    "bool"),
    ("bMultiTeams",            "Stacks with allied units",       "bool"),
]


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


def load_gendered_text() -> dict[str, str]:
    """Map GENDERED_TEXT_* → masculine TEXT_* key, across base + DLC files."""
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("genderedText*.xml")):
        for entry in ET.parse(p).getroot().findall("Entry"):
            zid = entry.findtext("zType") or ""
            if not zid:
                continue
            for pair in entry.findall("Texts/Pair"):
                if (pair.findtext("zIndex") or "").endswith("MASCULINE"):
                    out[zid] = pair.findtext("zValue") or ""
                    break
    return out


SMALL_WORDS = {"Of", "The", "And", "A", "An", "In", "On", "For", "To"}


def nice_token(token: str, *prefixes: str) -> str:
    s = token
    for pre in prefixes:
        if s.startswith(pre):
            s = s[len(pre):]
    words = s.replace("_", " ").title().split()
    return " ".join(w.lower() if i > 0 and w in SMALL_WORDS else w
                    for i, w in enumerate(words))


def sgn(v: int) -> str:
    return f"+{v}" if v > 0 else str(v)


def render_bonus_full(b: ET.Element, indexes: dict) -> list[str]:
    """render_bonus + bonus fields trait rewards use that it doesn't cover."""
    out = list(render_bonus(b, indexes))
    # Flat global yields, value as-is (BONUS_CIVICS_GAIN_40_FLAT → +40 Civics)
    for pair in b.findall("aiGlobalYieldsBase/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)} {y}")
    leg = int(b.findtext("iLegitimacy") or "0")
    if leg:
        out.append(f"{sgn(leg)} Legitimacy")
    xp = int(b.findtext("iXPCharacter") or "0")
    if xp:
        out.append(f"{sgn(xp)} XP")
    # Free techs
    for t in b.findall("aeTechs/zValue"):
        if t.text:
            tech = indexes.get("tech.xml", {}).get(t.text)
            nice = _lookup_name(indexes, tech.findtext("Name") or "") if tech is not None else ""
            out.append(f"Grants {nice or nice_token(t.text, 'TECH_')}")
    # Nested per-city bonuses (BONUS_CULTURE_GAIN_5_FLAT_ALL)
    for v in b.findall("aeAllCityBonuses/zValue"):
        sub = indexes.get("bonus.xml", {}).get(v.text or "")
        if sub is not None:
            for line in render_bonus_full(sub, indexes):
                out.append(line if line.endswith("in every City") else f"{line} in every City")
    # Culture-level-indexed yields (BONUS_KUSH_CULTURE)
    for pair in b.findall("aaiCultureYield/Pair"):
        lvl = nice_token(pair.findtext("zIndex") or "", "CULTURE_")
        for sub in pair.findall("SubPair"):
            y = yield_name(sub.findtext("zSubIndex"))
            v = int(sub.findtext("iValue") or "0")
            out.append(f"{fmt_decimal(v)} {y} per {lvl}-Culture City")
    return out


def render_trait_effect_unit(eu: ET.Element, indexes: dict) -> list[str]:
    """Full EffectUnit rendering: humanize + promotions renderer + trait extras."""
    out: list[str] = []
    out.extend(render_effect_unit(eu))
    out.extend(render_promotion_effect(eu))
    for tag, label, kind in UNIT_EXTRA_SCALARS:
        v = eu.findtext(tag)
        if v is None or v == "" or v == "0":
            continue
        if kind == "bool":
            if v == "1":
                out.append(label)
        elif kind == "pct":
            out.append(f"{sgn(int(v))}% {label}")
        else:
            out.append(f"{sgn(int(v))} {label}")
    # Nation/tribe kill yields (e.g. +X Orders per Barbarian kill)
    for tag, scope in (("aiMilitaryNationKillYield", "Nation"), ("aiMilitaryTribeKillYield", "Tribe")):
        for pair in eu.findall(f"{tag}/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0")
            out.append(f"{fmt_decimal(v)} {y} per {scope} kill")
    # Unit-trait gates: which units this applies to
    gates = [nice_token(p.findtext("zIndex") or "", "UNITTRAIT_")
             for p in eu.findall("abUnitTraitValid/Pair")
             if (p.findtext("bValue") or "0") == "1"]
    if gates:
        out.append(f"Applies to {', '.join(gates)} units")
    not_gates = [nice_token(p.findtext("zIndex") or "", "UNITTRAIT_")
                 for p in eu.findall("abUnitTraitInvalid/Pair")
                 if (p.findtext("bValue") or "0") == "1"]
    if not_gates:
        out.append(f"Not for {', '.join(not_gates)} units")
    # Deduplicate, preserve order
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def render_trait_effect_player(ep_id: str, indexes: dict) -> list[str]:
    """Generic EffectPlayer tree + the trait-specific fields it misses."""
    out = list(render_effect_player(ep_id, indexes))
    ep = indexes.get("effectPlayer.xml", {}).get(ep_id)
    if ep is None:
        return out

    for tag, label, kind in TRAIT_EP_SCALARS:
        v = ep.findtext(tag)
        if v is None or v == "" or v == "0":
            continue
        if kind == "bool":
            if v == "1":
                out.append(label)
        elif kind == "pct":
            out.append(f"{sgn(int(v))}% {label}")
        else:
            out.append(f"{sgn(int(v))} {label}")

    # Stat-triggered bonuses (Diligent: Orders on Improvement Finished)
    for pair in ep.findall("StatBonus/Pair"):
        stat = nice_token(pair.findtext("First") or "", "STAT_")
        b = indexes.get("bonus.xml", {}).get(pair.findtext("Second") or "")
        if b is not None:
            for line in render_bonus_full(b, indexes):
                out.append(f"On {stat}: {line.lstrip('+')}")

    # Mission-result bonuses (Silvered Clasp: Civics after Influence mission)
    for pair in ep.findall("MissionPlayerBonus/Pair"):
        mr = nice_token(pair.findtext("First") or "", "MISSIONRESULT_")
        b = indexes.get("bonus.xml", {}).get(pair.findtext("Second") or "")
        if b is not None:
            for line in render_bonus_full(b, indexes):
                out.append(f"After {mr} mission: {line.lstrip('+')}")

    # Re-render Start/Found bonuses with the fuller bonus renderer; exact
    # duplicates of what render_effect_player already emitted are deduped below.
    for tag, prefix in (("StartBonus", "Start: "), ("FoundBonus", "Found: "), ("Bonus", "On completion: ")):
        b_id = ep.findtext(tag) or ""
        if not b_id:
            continue
        b = indexes.get("bonus.xml", {}).get(b_id)
        if b is not None:
            for line in render_bonus_full(b, indexes):
                if line.startswith("Unlocks ") or line.startswith("Grants "):
                    out.append(line)
                else:
                    out.append(prefix + line.lstrip("+"))

    # Per-general yield rate (Trusted: +1 Orders/Turn per General)
    for pair in ep.findall("aiYieldRateGenerals/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"{fmt_decimal(v)} {y}/Turn per General")

    # Per-job opinion rate
    for pair in ep.findall("aiJobOpinionRate/Pair"):
        job = nice_token(pair.findtext("zIndex") or "", "JOB_")
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{sgn(v)} Opinion/Turn for {job}s")

    # Per-unit effect bundles (aeEffectUnit: unit → effectUnit)
    for pair in ep.findall("aeEffectUnit/Pair"):
        unit = nice_token(pair.findtext("zIndex") or "", "UNIT_")
        eu = indexes.get("effectUnit.xml", {}).get(pair.findtext("zValue") or "")
        if eu is not None:
            for line in render_trait_effect_unit(eu, indexes):
                out.append(f"{unit}s: {line}")

    # Per-unit-trait effect bundles (Commander: Infantry bonuses)
    for pair in ep.findall("aeEffectUnitTrait/Pair"):
        ut = nice_token(pair.findtext("zIndex") or "", "UNITTRAIT_")
        eu = indexes.get("effectUnit.xml", {}).get(pair.findtext("zValue") or "")
        if eu is not None:
            for line in render_trait_effect_unit(eu, indexes):
                out.append(f"{ut} units: {line}")

    # Invisible units (Schemer: Scouts invisible)
    for u in ep.findall("aeInvisibleUnit/zValue"):
        if u.text:
            out.append(f"{nice_token(u.text, 'UNIT_')}s are Invisible")

    # Improvements that spread borders (Harvest Crown: Granaries)
    for v in ep.findall("aeImprovementSpreadBorders/zValue"):
        if v.text:
            out.append(f"{nice_token(v.text, 'IMPROVEMENT_')} spreads borders")

    # Forced family membership (Amarna Reformer)
    for v in ep.findall("aeForceFamily/zValue"):
        if v.text:
            out.append(f"Belongs to the {nice_token(v.text, 'FAMILY_')} family")

    # Jobs free of family restriction
    for v in ep.findall("aeNoFamilyRestrictionJob/zValue"):
        if v.text:
            out.append(f"{nice_token(v.text, 'JOB_')} ignores family restriction")

    # Connected-city effect
    cec_id = ep.findtext("ConnectedEffectCity") or ""
    if cec_id:
        ec = indexes.get("effectCity.xml", {}).get(cec_id)
        if ec is not None:
            for line in render_effect_city(ec, per_city=False, indexes=indexes):
                out.append(f"Connected Cities: {line}")

    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def categorize(e: ET.Element) -> str:
    if (e.findtext("bArchetype") or "0") == "1":
        return "archetype"
    if (e.findtext("bStrength") or "0") == "1":
        return "strength"
    if (e.findtext("bWeakness") or "0") == "1":
        return "weakness"
    if (e.findtext("bItem") or "0") == "1":
        return "item"
    inj = int(e.findtext("iInjuryDie") or "0")
    if inj > 0 or e.find("aiMortalityDieProb/Pair") is not None:
        return "affliction"
    return "status"


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    # load_xml_indexes merges bonus-event-*.xml but misses the base
    # bonus-event.xml (no DLC suffix) — several trait StatBonus rewards
    # (BONUS_CIVICS_GAIN_40_FLAT, BONUS_UNIT_WORKER_NO_FAMILY, …) live there.
    base_events = XML_DIR / "bonus-event.xml"
    if base_events.exists():
        for entry in ET.parse(base_events).getroot().findall("Entry"):
            k = entry.findtext("zType") or ""
            if k:
                indexes["bonus.xml"].setdefault(k, entry)
    text = load_text(
        "text-trait.xml", "text-trait-btt.xml", "text-trait-sap.xml",
        "text-trait-wog.xml", "text-infos.xml",
    )
    gendered = load_gendered_text()

    root = parse("trait.xml")
    entries = [e for e in root.findall("Entry")
               if e.findtext("zType") and e.findtext("zType") not in SKIP_IDS]
    by_id = {e.findtext("zType"): e for e in entries}

    def name_of(tid: str) -> str:
        e = by_id.get(tid)
        gkey = (e.findtext("GenderedName") if e is not None else "") or f"GENDERED_TEXT_{tid}"
        tkey = gendered.get(gkey, "")
        if tkey and tkey in text:
            return text[tkey]
        return nice_token(tid, "TRAIT_")

    categories: dict[str, list[dict]] = {
        "archetype": [], "strength": [], "weakness": [],
        "affliction": [], "item": [], "status": [],
    }

    for e in entries:
        tid = e.findtext("zType") or ""
        cat = categorize(e)

        # Ratings — aiRating is a hard delta; aiRatingFallback only applies
        # when the rating wasn't set another way. Both are the trait's signed
        # contribution, so we merge and flag the fallback ones.
        ratings: list[dict] = []
        for tag, fallback in (("aiRating", False), ("aiPermanentRating", False), ("aiRatingFallback", True)):
            for pair in e.findall(f"{tag}/Pair"):
                r = RATING_LABELS.get(pair.findtext("zIndex") or "")
                v = int(pair.findtext("iValue") or "0")
                if r and v:
                    ratings.append({"rating": r, "value": v, "fallback": fallback})

        # Opinions
        opinions: list[dict] = []
        for tag, label in OPINION_SCALARS:
            v = int(e.findtext(tag) or "0")
            if v:
                opinions.append({"label": label, "value": v})
        for pair in e.findall("aiTraitOpinion/Pair"):
            v = int(pair.findtext("iValue") or "0")
            t = pair.findtext("zIndex") or ""
            if t and v:
                opinions.append({"label": name_of(t), "value": v})
        for tag, suffix in (("aiReligionOpinion", ""), ("aiReligionOpinionWeighted", " (weighted)")):
            for pair in e.findall(f"{tag}/Pair"):
                v = int(pair.findtext("iValue") or "0")
                t = pair.findtext("zIndex") or ""
                if t and v:
                    opinions.append({"label": nice_token(t, "RELIGION_") + suffix, "value": v})
        for pair in e.findall("aiLawOpinion/Pair"):
            v = int(pair.findtext("iValue") or "0")
            t = pair.findtext("zIndex") or ""
            if t and v:
                opinions.append({"label": f"{nice_token(t, 'LAW_')} (law)", "value": v})
        for pair in e.findall("aiJobOpinion/Pair"):
            v = int(pair.findtext("iValue") or "0")
            t = pair.findtext("zIndex") or ""
            if t and v:
                opinions.append({"label": f"as {nice_token(t, 'JOB_')}", "value": v})
        for pair in e.findall("aiFamilyClassOpinion/Pair"):
            v = int(pair.findtext("iValue") or "0")
            t = pair.findtext("zIndex") or ""
            if t and v:
                opinions.append({"label": f"{nice_token(t, 'FAMILYCLASS_')} families", "value": v})

        # Relations
        replaces = [name_of(v.text) for v in e.findall("aeTraitReplaces/zValue") if v.text]
        blocks = [name_of(v.text) for v in e.findall("aeTraitInvalid/zValue") if v.text]
        leads_to = []
        for pair in e.findall("aiTraitProb/Pair"):
            t = pair.findtext("zIndex") or ""
            v = int(pair.findtext("iValue") or "0")
            if t and v:
                leads_to.append({"name": name_of(t), "prob": v})

        # Effects
        leader_effects: list[str] = []
        lep = e.findtext("LeaderEffectPlayer") or ""
        if lep:
            leader_effects = render_trait_effect_player(lep, indexes)
        leu = e.findtext("LeaderEffectUnit") or ""
        if leu:
            eu = indexes.get("effectUnit.xml", {}).get(leu)
            if eu is not None:
                for line in render_trait_effect_unit(eu, indexes):
                    leader_effects.append(f"All units: {line}")

        governor_effects: list[str] = []
        gec = e.findtext("GovernorEffectCity") or ""
        if gec:
            ec = indexes.get("effectCity.xml", {}).get(gec)
            if ec is not None:
                governor_effects = render_effect_city(ec, per_city=False, indexes=indexes)
        srec = e.findtext("StateReligionEffectCity") or ""
        if srec:
            ec = indexes.get("effectCity.xml", {}).get(srec)
            if ec is not None:
                for line in render_effect_city(ec, per_city=False, indexes=indexes):
                    governor_effects.append(f"State Religion: {line}")

        general_effects: list[str] = []
        for tag, prefix in (("GeneralEffectUnit", ""), ("ExplorerEffectUnit", "Explorer: ")):
            eu_id = e.findtext(tag) or ""
            if not eu_id:
                continue
            eu = indexes.get("effectUnit.xml", {}).get(eu_id)
            if eu is not None:
                general_effects.extend(prefix + line for line in render_trait_effect_unit(eu, indexes))

        # Modifiers
        modifiers: list[dict] = []
        for tag, label in MODIFIER_SCALARS:
            v = int(e.findtext(tag) or "0")
            if v:
                modifiers.append({"label": label, "value": v})
        xp = int(e.findtext("iXPTurn") or "0")
        if xp:
            modifiers.append({"label": "XP/Turn (as General)", "value": xp})

        # Flags
        flags = [label for tag, label in BOOL_FLAGS if (e.findtext(tag) or "0") == "1"]

        # Acquisition hints — XML-native only (events grant most traits).
        acquisition: list[str] = []
        min_age = int(e.findtext("iMinAge") or "0")
        if min_age:
            acquisition.append(f"Min age {min_age}")
        for tag, label in (
            ("iAdjectiveDie", "On the childhood adjective roll"),
            ("iNoFamilyDie",  "Rolled for characters without a family"),
            ("iBarbDie",      "Rolled for tribal characters"),
            ("iInjuryDie",    "On the injury roll"),
        ):
            if int(e.findtext(tag) or "0") > 0:
                acquisition.append(label)
        adult = int(e.findtext("iAdultProb") or "0")
        if adult:
            acquisition.append(f"{adult}% chance at adulthood")
        rem_prob = int(e.findtext("iRemoveProb") or "0")
        rem_turns = int(e.findtext("iRemoveTurns") or "0")
        if rem_prob:
            acquisition.append(f"{rem_prob}% chance to recover" + (f" after {rem_turns} turns" if rem_turns else ""))
        elif rem_turns:
            acquisition.append(f"Removed after {rem_turns} turns")
        mort = []
        for pair in e.findall("aiMortalityDieProb/Pair"):
            mode = nice_token(pair.findtext("zIndex") or "", "MORTALITY_")
            v = int(pair.findtext("iValue") or "0")
            if v:
                mort.append(f"{v}% ({mode})")
        if mort:
            acquisition.append("Death risk " + ", ".join(mort))

        religion = e.findtext("Religion") or ""

        # Description / flavor text if the key resolves
        desc_key = e.findtext("Description") or ""
        description = text.get(desc_key, "")

        dlc = e.findtext("GameContentRequired") or ""

        nick_key = gendered.get(e.findtext("GenderedNickname") or "", "")
        nickname = text.get(nick_key, "")

        # Character-kit traits: EncyclopediaCharacter ties a trait to one
        # specific historical character (the W&D dynasty-leader kits and the
        # scenario leaders — "Darius Leader", Caesar's "Expansionist", …).
        # The page uses this to offer a "hide dynasty traits" toggle.
        enc_char = e.findtext("EncyclopediaCharacter") or ""
        dynasty_of = ""
        if enc_char:
            dynasty_of = (enc_char.replace("CHARACTER_", "")
                          .removesuffix("_LEADER").replace("_", " ").title())
            dynasty_of = re.sub(r"\b(I[ixv]|Vi{0,3}|Xi{0,3}|Iii?)\b",
                                lambda m: m.group(1).upper(), dynasty_of)

        categories[cat].append({
            "acquisition": acquisition,
            "blocks": blocks,
            "category": cat,
            "description": description,
            "dlc": nice_token(dlc) if dlc else "",
            "dynastyOf": dynasty_of,
            "flags": flags,
            "generalEffects": general_effects,
            "governorEffects": governor_effects,
            "id": tid,
            "leaderEffects": leader_effects,
            "leadsTo": leads_to,
            "modifiers": modifiers,
            "name": name_of(tid),
            "nickname": nickname,
            "opinions": opinions,
            "ratings": ratings,
            "religion": nice_token(religion, "RELIGION_") if religion else "",
            "replaces": replaces,
            "slug": tid.replace("TRAIT_", "").lower(),
        })

    for arr in categories.values():
        arr.sort(key=lambda t: t["name"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(categories, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    total = sum(len(v) for v in categories.values())
    counts = ", ".join(f"{k} {len(v)}" for k, v in categories.items())
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {total} traits ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
