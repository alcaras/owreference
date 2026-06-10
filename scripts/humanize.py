#!/usr/bin/env python3
"""
Turn Old World's structured effect XML into human-readable strings.

The game describes a nation/family/wonder/shrine effect as a tree of typed
modifiers — `<aiYieldRate><Pair>YIELD_SCIENCE +10</Pair></aiYieldRate>`,
`<bHireMercenaries>1</bHireMercenaries>`, and so on. This module renders
each such modifier into a one-line string like "+1 Science/City".

Used by build_data.py (and later the Families builder) so bonus/shrine
text becomes XML-canonical and updates with each patch.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

# Registry-driven completeness backstop: fields the game's own help system
# renders but the curated renderers below don't cover yet get a generic
# line appended via effects.extra_lines(). See scripts/effects.py.
try:
    import effects as _effects
except ImportError:  # registry not extracted yet — curated coverage only
    _effects = None

# ────────────────────────────────────────────────────────────────────────────
# Loaders + label helpers
# ────────────────────────────────────────────────────────────────────────────

def _index_entries(root: ET.Element, key: str = "zType") -> dict[str, ET.Element]:
    return {e.findtext(key) or "": e for e in root.findall("Entry") if e.findtext(key)}


def load_xml_indexes(xml_dir: Path) -> dict[str, dict[str, ET.Element]]:
    """Pre-load every XML file the humanizer might consult, indexed by zType.
    For bonus.xml we merge in the *-event-*.xml variants since they share
    the same shape and effects reference both freely."""
    files = [
        "effectCity.xml", "effectPlayer.xml", "effectUnit.xml",
        "bonus.xml", "improvement.xml", "promotion.xml",
        "project.xml", "tech.xml", "law.xml", "religion.xml",
        "trait.xml", "specialist.xml", "resource.xml",
    ]
    out: dict[str, dict[str, ET.Element]] = {}
    for f in files:
        p = xml_dir / f
        if p.exists():
            out[f] = _index_entries(ET.parse(p).getroot())

    # Merge bonus-event*.xml entries into bonus.xml lookup (the glob must
    # catch the suffix-less base file too — bonus-event.xml holds e.g.
    # BONUS_CIVICS_GAIN_40_FLAT used by trait rewards)
    bonus_idx = out.setdefault("bonus.xml", {})
    for p in xml_dir.glob("bonus-event*.xml"):
        for k, v in _index_entries(ET.parse(p).getroot()).items():
            bonus_idx.setdefault(k, v)

    # Build a flat text lookup for Name fields across all text-*.xml files
    text_idx: dict[str, str] = {}
    for p in xml_dir.glob("text-*.xml"):
        try:
            for entry in ET.parse(p).getroot().findall("Entry"):
                k = entry.findtext("zType") or ""
                en = _first_form(entry.findtext("en-US"))
                if k and en:
                    text_idx.setdefault(k, en)
        except ET.ParseError:
            continue
    out["__text__"] = text_idx  # type: ignore[assignment]
    return out


def _lookup_name(indexes: dict, name_key: str) -> str:
    """Resolve TEXT_PROJECT_OLYMPICS → 'Olympics' via the merged text index."""
    if not name_key:
        return ""
    text = indexes.get("__text__", {})
    return text.get(name_key, "")


# Token class includes digits — IMPROVEMENT_GARRISON_1, FOCUS2, etc.
_LINK_RE = re.compile(r"\{?lowercase:link\(([A-Z0-9_]+)(?:,\d+)?\)\}?|link\(([A-Z0-9_]+)(?:,\d+)?\)")


def _strip_link_templates(s: str) -> str:
    """The game's strings use {lowercase:link(TOKEN,2)} markup. Replace with
    a title-cased rendering of the final word in TOKEN — e.g.
    link(RELIGION_BUDDHISM) → Buddhism."""
    def repl(m: "re.Match[str]") -> str:
        token = m.group(1) or m.group(2) or ""
        # Drop leading category (RELIGION_, CONCEPT_, etc.) — keep the rest
        parts = token.split("_")
        if len(parts) > 1:
            parts = parts[1:]
        return " ".join(p.title() for p in parts)
    return _LINK_RE.sub(repl, s)


def _first_form(s: str | None) -> str:
    raw = (s or "").split("~")[0].strip()
    return _strip_link_templates(raw)


def load_text(xml_dir: Path, *filenames: str) -> dict[str, str]:
    """Build a {TEXT_KEY: en-US first form} map from any text-*.xml files."""
    out: dict[str, str] = {}
    for fn in filenames:
        p = xml_dir / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = _first_form(e.findtext("en-US"))
            if k:
                out[k] = en
    return out


def world_religions(xml_dir: Path) -> list[tuple[str, str, dict]]:
    """Derive the world-religion list from religion.xml: a world religion is
    any entry with a SpreadUnit (pagan religions and Atenism have none).
    Hinduism qualifies despite bHidden/bNoSpread — it's a hybrid: the pagan
    religion of the Indus nations that builds worship buildings and is
    FORCED to adopt theologies (bForceTheologies). Never hardcode this list;
    DLC adds members (Hinduism ships with Empires of the Indus).

    Returns (id, display name, quirks) in religion.xml order."""
    text = load_text(xml_dir, "text-religion.xml", "text-religion-hittite.xml")
    out: list[tuple[str, str, dict]] = []
    for e in ET.parse(xml_dir / "religion.xml").getroot().findall("Entry"):
        rid = e.findtext("zType") or ""
        if not rid or not e.findtext("SpreadUnit"):
            continue
        name = text.get(f"TEXT_{rid}", rid.replace("RELIGION_", "").title())
        quirks = {
            "dlc": e.findtext("GameContentRequired") or None,
            "noSpread": e.findtext("bNoSpread") == "1",
            "forceTheologies": e.findtext("bForceTheologies") == "1",
            "paganNations": [
                (v.text or "").replace("NATION_", "").title()
                for v in e.findall("PaganNations/zValue")
            ],
        }
        out.append((rid, name, quirks))
    return out


def fmt_decimal(v: float) -> str:
    """Format an integer-or-decimal nicely. 1 → '+1', 0.5 → '+0.5', -2 → '-2'."""
    if v == int(v):
        v = int(v)
    sign = "+" if v >= 0 else ""
    return f"{sign}{v}"


# ────────────────────────────────────────────────────────────────────────────
# Token-to-name resolvers
#   - yield_name("YIELD_SCIENCE") -> "Science"
#   - condition_name("EFFECTCITY_CONNECTED") -> "Connected"
# ────────────────────────────────────────────────────────────────────────────

def yield_name(zindex: str | None) -> str:
    if not zindex:
        return ""
    return zindex.replace("YIELD_", "").replace("_", " ").title()


# Human-friendly labels for the most common "conditional" tokens used as
# the LHS in aaiEffectCityYieldRate / similar fields. Anything not listed
# falls back to a title-cased rendering of the raw token.
CONDITION_LABELS: dict[str, str] = {
    "EFFECTCITY_CONNECTED": "Connected",
    "EFFECTCITY_PROJECT_TREASURY": "Treasury",
    "EFFECTCITY_PROJECT_OLYMPICS": "Olympics",
    "EFFECTCITY_PROJECT_HOLD_COURT": "Hold Court",
    "EFFECTCITY_PROJECT_RALLY": "Rally",
}


def condition_name(zindex: str | None) -> str:
    if not zindex:
        return ""
    if zindex in CONDITION_LABELS:
        return CONDITION_LABELS[zindex]
    # Strip common prefixes
    s = zindex
    for pre in ("EFFECTCITY_", "PROJECT_", "EFFECTPLAYER_", "IMPROVEMENT_"):
        if s.startswith(pre):
            s = s[len(pre):]
    return s.replace("_", " ").title()


# Bool/integer "scalar" fields on effectPlayer/effectCity that have nice
# one-line representations.
SCALAR_LABELS: list[tuple[str, str, str]] = [
    # (xml_tag, when_bool_or_template, kind)
    # kind = "bool" → render label as-is when value is "1"
    # kind = "pct"  → render "+{val}% label"  (value is positive int)
    # kind = "pct_signed" → render "{sign}{val}% label"
    # kind = "int"  → render "{sign}{val} label"
    # kind = "rate" → game value/10, signed
    ("bHireMercenaries",       "Can hire Mercenaries from Tribes", "bool"),
    ("bAlwaysConnected",       "Cities always Connected",          "bool"),
    ("bAdjacentToOwn",         "Anyone can build adjacent",        "bool"),
    ("bIgnoreHill",            "No hill movement penalty",          "bool"),
    ("iHarvestModifier",       "Harvest",                          "pct"),
    ("iCultureRate",           "Culture/City",                     "rate"),
    ("iCultureRateModifier",   "Culture",                          "pct"),
    ("iGrowthModifier",        "Growth",                           "pct"),
    ("iTrainingModifier",      "Training",                         "pct"),
    ("iCivicsModifier",        "Civics",                           "pct"),
    ("iScienceModifier",       "Science",                          "pct"),
    ("iMoneyModifier",         "Money",                            "pct"),
    ("iFatigueLimit",          "Fatigue Limit",                    "int"),
    ("iPillageYieldModifier",  "Pillage Yield",                    "pct"),
    ("iSettlerCostModifier",   "Settler Cost",                     "pct_signed"),
    ("iRangedCostModifier",    "Ranged Cost",                      "pct_signed"),
    # Wonder / law scalar fields
    ("iVP",                    "Victory Points",                   "int"),
    ("iStartLawModifier",      "Start Law Cost",                   "pct_signed"),
    ("iTechsAvailableChange",  "Tech Card Hand Size",              "int"),
    ("iReligionOpinionChange", "Opinion with all Religions",       "int"),
    ("iConsumptionModifier",   "Unit Consumption",                 "pct_signed"),
    ("iWonderModifier",        "Wonder Cost",                      "pct_signed"),
    ("iXPModifier",            "XP for All Units",                 "pct_signed"),
    ("iMaxActions",            "Max Actions",                      "int"),
    ("iStateReligionSpread",   "State Religion Spread Chance",     "pct"),
    ("bNoUnitConsumption",     "Units consume no Resources",       "bool"),
    ("bBuildAllReligions",     "Can build Non-State Religion Disciples", "bool"),
    ("bRiverMovement",         "Movement bonus along Rivers",      "bool"),
    ("bRiverBridging",         "Can cross Rivers without penalty", "bool"),
    ("bNoSellPenalty",         "Sell at the same price as buying", "bool"),
    ("bPurgeReligions",        "Disciples can purge World Religions", "bool"),
    ("bPaganStateReligion",    "Can adopt Pagan State Religions",  "bool"),
    ("bRemoveAllVegetation",   "Can remove all Vegetation",        "bool"),
]


# Per-city conditional yield fields: <tag>/Pair → "{val} Y/{label}"
PER_CITY_YIELD_RATE_FIELDS: list[tuple[str, str]] = [
    ("aiYieldRateCulture",             "Culture Level"),
    ("aiYieldRateReligion",            "Religion"),
    ("aiYieldRatePaganReligion",       "Pagan Religion"),
    ("aiYieldRateReligionNonState",    "Non-State Religion"),
    ("aiYieldRatePopulation",          "Pop"),
    ("aiYieldRateSpecialist",          "Specialist"),
    ("aiYieldRateSpecialistUrban",     "Urban Specialist"),
    ("aiYieldRateSpecialistRural",     "Rural Specialist"),
    ("aiYieldRateMilitary",            "Military Unit"),
    ("aiYieldRateHolyCityWorld",       "Holy City"),
    ("aiYieldRateSpecialistClass",     "Specialist Class"),
]


# ────────────────────────────────────────────────────────────────────────────
# Curated coverage — fields each renderer below phrases itself. Everything
# else that the game renders (per scripts/data/helptext_registry.json) is
# appended generically by effects.extra_lines(). scripts/audit_coverage.py
# reads this to verify nothing player-facing is silently dropped.
# ────────────────────────────────────────────────────────────────────────────

HANDLED_FIELDS: dict[str, set[str]] = {
    "effectCity": {
        "aiYieldRate", "aiYieldModifier", "aaiEffectCityYieldRate",
        "aaiTileYieldRateAdjacentDouble", "aaiTileYieldModifier",
        "aeFreeEffectUnit", "aiImprovementRiverModifier", "aiUnitCostModifier",
        "iAdjacentClassCostModifier", "aiUnitTraitCostModifier",
        "aaiImprovementClassYield", "aiImprovementClassModifier",
        "aeEffectCityEffectCity", "aiYieldRateCulture", "aiYieldRateReligion",
        "aiYieldRatePaganReligion", "aiYieldRateReligionNonState",
        "aiYieldRatePopulation", "aiYieldRateSpecialist",
        "aiYieldRateSpecialistUrban", "aiYieldRateSpecialistRural",
        "aiYieldRateMilitary",
        "aiYieldRateHolyCityWorld", "aiYieldRateSpecialistClass",
        "aiImprovementModifier", "aeFreeUnitEffectCity", "aeLuxuryResources",
        "abNoImprovementClassMax", "TerrainImprovementValid", "aeHurryMoney",
        "SpecialistNoPrereq", "aiUnitTraitLevel", "iCityHP", "iUnitHealAlways",
        "iUnitLevel", "iSpecialistUrbanTrainTimeModifier",
        "iImprovementCostModifier", "iRebelProb", "iRandomPromotions",
        "iHurryDiscontentModifier", "bHurryOrders", "bHurryPopulation",
        "bNoReligionSpread",
        # Deliberately phrased by build_families.py (City Defense / Specialist
        # Cost lines control order + wording there).
        "iStrengthModifier", "iSpecialistCostModifier",
        # Structural / traversal fields, not effect lines of their own.
        "EffectCityUnlock",
    },
    "effectPlayer": {
        # SCALAR_LABELS tags
        "bHireMercenaries", "bAlwaysConnected", "bAdjacentToOwn",
        "bIgnoreHill", "iHarvestModifier", "iCultureRate",
        "iCultureRateModifier", "iGrowthModifier", "iTrainingModifier",
        "iCivicsModifier", "iScienceModifier", "iMoneyModifier",
        "iFatigueLimit", "iPillageYieldModifier", "iSettlerCostModifier",
        "iRangedCostModifier", "iVP", "iStartLawModifier",
        "iTechsAvailableChange", "iReligionOpinionChange",
        "iConsumptionModifier", "iWonderModifier", "iXPModifier",
        "iMaxActions", "iStateReligionSpread", "bNoUnitConsumption",
        "bBuildAllReligions", "bRiverMovement", "bRiverBridging",
        "bNoSellPenalty", "bPurgeReligions", "bPaganStateReligion",
        "bRemoveAllVegetation",
        # Explicit pair/list fields
        "aiMissionYieldCostModifier", "iTribeFatigueChange", "aiYieldRate",
        "aiYieldRateLaws", "aiWarYield", "aeTradeYield", "aeWaterUnit",
        "aeBuyTile", "bBuyTile",
        # Structural traversal (rendered by recursing, not as lines)
        "EffectCity", "EffectCityExtra", "StateReligionEffectCity",
        "CapitalEffectCity", "StartBonus", "FoundBonus", "Bonus",
        "EffectUnit", "EffectPlayer",
    },
    "effectUnit": {
        "iPillageYieldModifier", "iFatigueExtra", "aiMilitaryKillYield",
        "iHomeModifier",
    },
    "bonus": {
        "aiYieldStockpile", "aiGlobalYields", "aiYields", "aiYieldRate",
        "aeFreeProject", "aeAddProjects", "aeFreeUnit", "aiUnits",
        "aiCityYields", "iHappinessLevels", "AddImprovementClass",
        "bHolyCityAgents", "iLegitimacy",
    },
}


def _extra(entry: ET.Element, section: str, indexes: dict | None) -> list[str]:
    """Registry-backstop lines for fields the curated renderers skip."""
    if _effects is None:
        return []
    return _effects.extra_lines(
        entry, section, exclude=HANDLED_FIELDS[section], indexes=indexes
    )


# ────────────────────────────────────────────────────────────────────────────
# Renderers
# ────────────────────────────────────────────────────────────────────────────

def render_effect_city(e: ET.Element, *, per_city: bool = True, indexes: dict | None = None) -> list[str]:
    """Render an EffectCity entry as a list of human-readable lines.

    `per_city` adds the '/City' suffix to yield-rate lines. Set False when
    the rendering caller is operating at player scope (effectPlayer fields).
    """
    out: list[str] = []
    suffix = "/City" if per_city else ""

    for pair in e.findall("aiYieldRate/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"{fmt_decimal(v)} {y}{suffix}")

    for pair in e.findall("aiYieldModifier/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% {y}")

    for pair in e.findall("aaiEffectCityYieldRate/Pair"):
        cond = condition_name(pair.findtext("zIndex"))
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0") / 10
            out.append(f"{fmt_decimal(v)} {y}/{cond}")

    # Tile yield bonuses (e.g., +Farm yields on River)
    for pair in e.findall("aaiTileYieldRateAdjacentDouble/Pair"):
        tile = condition_name(pair.findtext("zIndex"))
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0") / 10
            out.append(f"{fmt_decimal(v)} {y}/{tile}")

    for pair in e.findall("aaiTileYieldModifier/Pair"):
        tile = condition_name(pair.findtext("zIndex"))
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0")
            out.append(f"{fmt_decimal(v)}% {y}/{tile}")

    # Free unit effects bundled with this city effect (e.g., Focus 1)
    for fe in e.findall("aeFreeEffectUnit/zValue"):
        out.append(_render_unit_effect_label(fe.text or ""))

    # Improvement-on-river modifiers (Egypt: +40% Farm on River)
    for pair in e.findall("aiImprovementRiverModifier/Pair"):
        imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENT_", "").title()
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% {imp} on River")

    # Unit cost modifier per unit-type (Greece: -25% Settler Cost)
    for pair in e.findall("aiUnitCostModifier/Pair"):
        unit = (pair.findtext("zIndex") or "").replace("UNIT_", "").title()
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% {unit} Cost")

    # Improvement-class cost modifiers (Egypt extra: -20% Cost for Adjacent Imps)
    iacm = e.findtext("iAdjacentClassCostModifier")
    if iacm and iacm != "0":
        out.append(f"{fmt_decimal(int(iacm))}% Cost for Adjacent Improvements")

    # Per-unit-trait cost modifiers (Persia: -25% Ranged Cost)
    for pair in e.findall("aiUnitTraitCostModifier/Pair"):
        trait = (pair.findtext("zIndex") or "").replace("UNITTRAIT_", "").title()
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% {trait} Cost")

    # Per-improvement-class yield (Persia: +0.5 Orders/Pastures)
    for pair in e.findall("aaiImprovementClassYield/Pair"):
        imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENTCLASS_", "").title()
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0") / 10
            out.append(f"{fmt_decimal(v)} {y}/{imp}")

    # Improvement-class % modifier (Kush: +50% Shrines)
    for pair in e.findall("aiImprovementClassModifier/Pair"):
        imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENTCLASS_", "").title()
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% {imp}")

    # Resource-triggered effects: "When city has Resource X, gain effect Y"
    # (Aksum: ELEPHANT → GIVE_IVORY). Render as "Elephants give Ivory".
    for pair in e.findall("aeEffectCityEffectCity/Pair"):
        trigger = pair.findtext("zIndex") or ""
        result = pair.findtext("zValue") or ""
        if trigger.startswith("EFFECTCITY_RESOURCE_") and indexes is not None:
            resource = trigger.replace("EFFECTCITY_RESOURCE_", "").replace("_", " ").title()
            result_entry = indexes.get("effectCity.xml", {}).get(result)
            if result_entry is not None:
                # Pull the produced luxury from aeLuxuryResources, or fall back to name
                luxes = [r.text.replace("RESOURCE_", "").title()
                         for r in result_entry.findall("aeLuxuryResources/zValue")
                         if r.text]
                if luxes:
                    out.append(f"{resource}s give {', '.join(luxes)}")
                    continue
        # Fallback: raw token
        out.append(f"{condition_name(trigger)} → {condition_name(result)}")

    # Conditional per-X yield rates (e.g., +1 Science/Forum, +2 Culture/Specialist)
    for tag, label in PER_CITY_YIELD_RATE_FIELDS:
        for pair in e.findall(f"{tag}/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0") / 10
            out.append(f"{fmt_decimal(v)} {y}/{label}")

    # Per-improvement modifier (e.g., +20% Mine, +20% Quarry)
    for pair in e.findall("aiImprovementModifier/Pair"):
        imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENT_", "").replace("_", " ").title()
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% {imp}")

    # Provides a free resource via an EffectCityResource trigger
    # (e.g., Autarky Extra → HORSE/CAMEL/ELEPHANT)
    res_names: list[str] = []
    for r in e.findall("aeFreeUnitEffectCity/zValue"):
        token = r.text or ""
        if token.startswith("EFFECTCITY_RESOURCE_"):
            res_names.append(token.replace("EFFECTCITY_RESOURCE_", "").replace("_", " ").title())
    if res_names:
        out.append(f"Provides: {', '.join(res_names)}")

    # Luxury resources directly listed (e.g., Al Khazneh)
    luxes = [r.text.replace("RESOURCE_", "").replace("_", " ").title()
             for r in e.findall("aeLuxuryResources/zValue") if r.text]
    if luxes:
        out.append(f"Provides Luxuries: {', '.join(luxes)}")

    # No max-count limit lifted for improvement class (e.g., Polytheism → shrines)
    for pair in e.findall("abNoImprovementClassMax/Pair"):
        if (pair.findtext("bValue") or "0") == "1":
            cls = (pair.findtext("zIndex") or "").replace("IMPROVEMENTCLASS_", "").title()
            out.append(f"No max count for {cls}")

    # Allow building specific improvement on specific terrain
    # (e.g., Centralization → Farm on Marsh)
    for pair in e.findall("TerrainImprovementValid/Pair"):
        terrain = (pair.findtext("First") or "").replace("TERRAIN_TARGET_", "").replace("_", " ").title()
        imp = (pair.findtext("Second") or "").replace("IMPROVEMENT_", "").replace("_", " ").title()
        if terrain and imp:
            out.append(f"Can build {imp} on {terrain}")

    # Hurry production with money
    for r in e.findall("aeHurryMoney/zValue"):
        token = (r.text or "")
        thing = token.replace("BUILD_", "").replace("_", " ").title() if token else "Production"
        out.append(f"Can hurry {thing} with Money")

    # Specialist unlock with no prerequisite (e.g., Guilds → Elder)
    sp = e.findtext("SpecialistNoPrereq") or ""
    if sp:
        nice = sp.replace("EFFECTCITY_SPECIALIST_", "").replace("_", " ").title()
        out.append(f"Can build {nice} Specialist without prereq")

    # Per-trait level boost (e.g., Mausoleum: +1 Level for Guard units)
    for pair in e.findall("aiUnitTraitLevel/Pair"):
        trait = (pair.findtext("zIndex") or "").replace("UNITTRAIT_", "").replace("_", " ").title()
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)} Level for new {trait} units")

    # Scalar EffectCity-only fields. NOTE: iStrengthModifier and
    # iSpecialistCostModifier are deliberately handled in build_families.py
    # so its City Defense / Specialist Cost lines control phrasing and order.
    _ec_scalars: list[tuple[str, str, str]] = [
        ("iCityHP",                           "City HP",                   "int"),
        ("iUnitHealAlways",                   "Unit Heal/Turn in Territory","int"),
        ("iUnitLevel",                        "Level for new Units",       "int"),
        ("iSpecialistUrbanTrainTimeModifier", "Urban Specialist Production Time", "pct_signed"),
        ("iImprovementCostModifier",          "Improvement Cost",          "pct_signed"),
        ("iRebelProb",                        "Rebel Chance",              "pct_signed"),
        ("iRandomPromotions",                 "Random Promotions for new Units", "int"),
        ("iHurryDiscontentModifier",         "Hurry Discontent",          "pct_signed"),
    ]
    for tag, label, kind in _ec_scalars:
        v = e.findtext(tag)
        if not v or v == "0":
            continue
        iv = int(v)
        if kind == "int":
            out.append(f"{fmt_decimal(iv)} {label}")
        elif kind == "pct_signed":
            out.append(f"{fmt_decimal(iv)}% {label}")

    # Booleans
    _ec_bools: list[tuple[str, str]] = [
        ("bHurryOrders",      "Can hurry production with Orders"),
        ("bHurryPopulation",  "Can hurry production with Population"),
        ("bNoReligionSpread", "No random Non-State Religion spread"),
    ]
    for tag, label in _ec_bools:
        if (e.findtext(tag) or "") == "1":
            out.append(label)

    out.extend(_extra(e, "effectCity", indexes))
    return out


def _render_unit_effect_label(unit_eff_id: str) -> str:
    """EFFECTUNIT_FOCUS1 → 'Units start with Focus I'."""
    s = unit_eff_id.replace("EFFECTUNIT_", "")
    if s.startswith("FOCUS"):
        try:
            n = int(s[5:])
            return f"Units start with Focus {('I' * n)[:3] or 'I'}"
        except ValueError:
            return f"Units start with {s.title()}"
    return f"Units gain {s.title().replace('_', ' ')}"


def render_effect_unit(e: ET.Element) -> list[str]:
    """Render an EffectUnit entry's scalar / yield fields (per-unit effects)."""
    out: list[str] = []
    pillage = e.findtext("iPillageYieldModifier")
    if pillage and pillage != "0":
        out.append(f"{fmt_decimal(int(pillage))}% Pillage Yield")
    fatigue = e.findtext("iFatigueExtra")
    if fatigue and fatigue != "0":
        out.append(f"{fmt_decimal(int(fatigue))} Fatigue Limit")
    for pair in e.findall("aiMilitaryKillYield/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)} {y}/Kill")
    # Fighting from own tiles (Unit.cs homeModifier — applies when the
    # from-tile owner is the unit's player)
    hm = e.findtext("iHomeModifier")
    if hm and hm != "0":
        out.append(f"{fmt_decimal(int(hm))}% Strength in own territory")
    out.extend(_extra(e, "effectUnit", None))
    return out


def render_effect_player_scalars(e: ET.Element) -> list[str]:
    """Render simple scalar fields directly on an EffectPlayer entry."""
    out: list[str] = []
    for tag, label, kind in SCALAR_LABELS:
        v = e.findtext(tag)
        if v is None or v == "" or v == "0":
            continue
        if kind == "bool" and v == "1":
            out.append(label)
        elif kind == "pct":
            out.append(f"+{int(v)}% {label}")
        elif kind == "pct_signed":
            iv = int(v)
            out.append(f"{fmt_decimal(iv)}% {label}")
        elif kind == "int":
            out.append(f"{fmt_decimal(int(v))} {label}")
        elif kind == "rate":
            out.append(f"{fmt_decimal(int(v) / 10)} {label}")

    # Mission yield-cost modifiers (Maurya: -50% Civics Mission, -50% Training Mission)
    for pair in e.findall("aiMissionYieldCostModifier/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% {y} Mission Cost")

    # Tribe fatigue (Yuezhi: +1 — "Vassalize Tribe / +Ally Fatigue")
    tfc = e.findtext("iTribeFatigueChange")
    if tfc and tfc != "0":
        out.append(f"{fmt_decimal(int(tfc))} Tribe Fatigue Change")

    # Player-scope yield rates (e.g., Ziggurat: +20 Civics/Turn globally)
    for pair in e.findall("aiYieldRate/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"{fmt_decimal(v)} {y}/Turn")

    # Per-active-law yield (Legal Code: +10 Civics/Active Law)
    for pair in e.findall("aiYieldRateLaws/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"{fmt_decimal(v)} {y}/Active Law")

    # Per-war yield (Volunteers: +20 Training per War)
    for pair in e.findall("aiWarYield/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"{fmt_decimal(v)} {y} per War")

    # Trade yields (Coin Debasement: Orders ↔ Money)
    trade_yields = [yield_name(v.text or "") for v in e.findall("aeTradeYield/zValue") if v.text]
    if trade_yields:
        out.append(f"Can buy/sell {', '.join(trade_yields)} for Money")

    # Units that can move on water (Exploration → Scout)
    for u in e.findall("aeWaterUnit/zValue"):
        unit = (u.text or "").replace("UNIT_", "").title()
        if unit:
            out.append(f"{unit}s can move on Water")

    # Buy tiles with money (Colonies)
    bt = [v.text for v in e.findall("aeBuyTile/zValue") if v.text]
    if bt or (e.findtext("bBuyTile") == "1"):
        out.append("Can buy Tiles with Money")

    out.extend(_extra(e, "effectPlayer", None))
    return out


def render_effect_city_state_religion(e: ET.Element, *, indexes: dict | None = None) -> list[str]:
    """Render an EffectCity as 'State Religion: ...' lines (used by laws)."""
    base = render_effect_city(e, per_city=True, indexes=indexes)
    return [f"[State Religion] {line}" for line in base]


def render_effect_city_capital(e: ET.Element, *, indexes: dict | None = None) -> list[str]:
    """Render an EffectCity scoped to the Capital only."""
    base = render_effect_city(e, per_city=True, indexes=indexes)
    return [f"[Capital] {line}" for line in base]


def render_bonus(e: ET.Element, indexes: dict | None = None) -> list[str]:
    """Render a Bonus entry (granted on found/start)."""
    out: list[str] = []
    for tag in ("aiYieldStockpile", "aiGlobalYields", "aiYields"):
        for pair in e.findall(f"{tag}/Pair"):
            y = yield_name(pair.findtext("zIndex"))
            v = int(pair.findtext("iValue") or "0")
            out.append(f"{fmt_decimal(v)} {y}")
    for pair in e.findall("aiYieldRate/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)} {y}")
    for fp in e.findall("aeFreeProject/zValue") + e.findall("aeAddProjects/zValue"):
        token = fp.text or ""
        nice = ""
        if indexes is not None:
            proj = indexes.get("project.xml", {}).get(token)
            if proj is not None:
                nice = _lookup_name(indexes, proj.findtext("Name") or "")
        out.append(f"Unlocks {nice or condition_name(token)}")
    for fu in e.findall("aeFreeUnit/Pair") + e.findall("aiUnits/Pair"):
        u = (fu.findtext("zIndex") or "").replace("UNIT_", "").title()
        n = int(fu.findtext("iValue") or "0")
        out.append(f"+{n} {u}")
    # Per-city instant yields (e.g., Ishtar Gate: +100 Culture in every City)
    for pair in e.findall("aiCityYields/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)} {y} in every City")
    # Instant happiness levels in every city (e.g., Hagia Sophia)
    hl = e.findtext("iHappinessLevels")
    if hl and hl != "0":
        n = int(hl)
        out.append(f"+{n} Happiness Level{'s' if n != 1 else ''} in every City")
    # Free improvement of a class added to every city (e.g., Jebel Barkal Temple)
    add_cls = e.findtext("AddImprovementClass")
    if add_cls:
        nice = add_cls.replace("IMPROVEMENTCLASS_", "").replace("_", " ").title()
        out.append(f"Adds a free {nice} to every City")
    # Holy-city agents (e.g., the Oracle)
    if (e.findtext("bHolyCityAgents") or "0") == "1":
        out.append("Holy City spawns Agents")
    # Legitimacy grants (event/trait bonuses; rendered by the event-option
    # help builder in-game, so it's absent from the helptext registry)
    leg = e.findtext("iLegitimacy")
    if leg and leg != "0":
        out.append(f"{fmt_decimal(int(leg))} Legitimacy")
    out.extend(_extra(e, "bonus", indexes))
    return out


# ────────────────────────────────────────────────────────────────────────────
# Top-level: render a nation's full effect surface
# ────────────────────────────────────────────────────────────────────────────

def render_nation_effects(
    effect_player_id: str,
    indexes: dict[str, dict[str, ET.Element]],
) -> list[str]:
    """Render every effect that ships with the EFFECTPLAYER_NATION_X entry."""
    ep = indexes.get("effectPlayer.xml", {}).get(effect_player_id)
    if ep is None:
        return []

    lines: list[str] = []
    lines.extend(render_effect_player_scalars(ep))

    # Per-city effect
    ec_id = ep.findtext("EffectCity")
    if ec_id:
        ec = indexes.get("effectCity.xml", {}).get(ec_id)
        if ec is not None:
            lines.extend(render_effect_city(ec, per_city=True, indexes=indexes))

    # Extra per-city effect (e.g., Egypt)
    ece_id = ep.findtext("EffectCityExtra")
    if ece_id:
        ec = indexes.get("effectCity.xml", {}).get(ece_id)
        if ec is not None:
            lines.extend(render_effect_city(ec, per_city=True, indexes=indexes))

    # One-time bonuses (Start / Found)
    for tag in ("StartBonus", "FoundBonus"):
        b_id = ep.findtext(tag)
        if not b_id:
            continue
        b = indexes.get("bonus.xml", {}).get(b_id)
        if b is not None:
            prefix = "Start: " if tag == "StartBonus" else "Found: "
            for line in render_bonus(b, indexes):
                # Pass through "Unlocks X" as-is, otherwise prefix Start:/Found:
                if line.startswith("Unlocks "):
                    lines.append(line)
                else:
                    lines.append(prefix + line.lstrip("+"))

    # Unit effects (e.g., Assyria EFFECTUNIT_ASSYRIA contains pillage/kill bonuses)
    eu_id = ep.findtext("EffectUnit")
    if eu_id:
        eu = indexes.get("effectUnit.xml", {}).get(eu_id)
        if eu is not None:
            lines.extend(render_effect_unit(eu))

    # Nested EffectPlayer (e.g., Greece Olympics, Aksum Mint Coin, Maurya Buddhism)
    sub = ep.findtext("EffectPlayer")
    if sub:
        sub_entry = indexes.get("effectPlayer.xml", {}).get(sub)
        sub_name_key = sub_entry.findtext("Name") if sub_entry is not None else ""
        # If the nested effect points at a project (TEXT_PROJECT_*), render
        # "Unlocks <Project>" — that's what nations like Greece do for Olympics.
        if sub_name_key and sub_name_key.startswith("TEXT_PROJECT_"):
            nice = _lookup_name(indexes, sub_name_key)
            if nice:
                lines.append(f"Unlocks {nice}")
            else:
                lines.append(f"Unlocks {condition_name(sub)}")
        # Always recurse to capture any concrete modifiers on the nested entry too
        for line in render_nation_effects(sub, indexes):
            lines.append(line)

    # Deduplicate while preserving order
    seen = set()
    deduped: list[str] = []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            deduped.append(ln)
    return deduped


def render_effect_player(
    effect_player_id: str,
    indexes: dict[str, dict[str, ET.Element]],
) -> list[str]:
    """Generic renderer for any EFFECTPLAYER_* entry.

    Like `render_nation_effects` but follows extra side-channels used by
    laws and wonders: StateReligionEffectCity, CapitalEffectCity.
    """
    ep = indexes.get("effectPlayer.xml", {}).get(effect_player_id)
    if ep is None:
        return []

    lines: list[str] = []
    lines.extend(render_effect_player_scalars(ep))

    # Per-city effect
    ec_id = ep.findtext("EffectCity")
    if ec_id:
        ec = indexes.get("effectCity.xml", {}).get(ec_id)
        if ec is not None:
            lines.extend(render_effect_city(ec, per_city=True, indexes=indexes))

    # Extra per-city effect
    ece_id = ep.findtext("EffectCityExtra")
    if ece_id:
        ec = indexes.get("effectCity.xml", {}).get(ece_id)
        if ec is not None:
            lines.extend(render_effect_city(ec, per_city=True, indexes=indexes))

    # State-religion-only per-city effect
    srec_id = ep.findtext("StateReligionEffectCity")
    if srec_id:
        ec = indexes.get("effectCity.xml", {}).get(srec_id)
        if ec is not None:
            lines.extend(render_effect_city_state_religion(ec, indexes=indexes))

    # Capital-only per-city effect (e.g., Centralization)
    cap_id = ep.findtext("CapitalEffectCity")
    if cap_id:
        ec = indexes.get("effectCity.xml", {}).get(cap_id)
        if ec is not None:
            lines.extend(render_effect_city_capital(ec, indexes=indexes))

    # One-time bonuses
    for tag, prefix in (("StartBonus", "Start: "), ("FoundBonus", "Found: "), ("Bonus", "On completion: ")):
        b_id = ep.findtext(tag)
        if not b_id:
            continue
        b = indexes.get("bonus.xml", {}).get(b_id)
        if b is not None:
            for line in render_bonus(b, indexes):
                if line.startswith("Unlocks "):
                    lines.append(line)
                else:
                    lines.append(prefix + line.lstrip("+"))

    # Unit effects
    eu_id = ep.findtext("EffectUnit")
    if eu_id:
        eu = indexes.get("effectUnit.xml", {}).get(eu_id)
        if eu is not None:
            lines.extend(render_effect_unit(eu))

    # Nested EffectPlayer (e.g., Constitution → Decree, etc.)
    sub = ep.findtext("EffectPlayer")
    if sub:
        sub_entry = indexes.get("effectPlayer.xml", {}).get(sub)
        sub_name_key = sub_entry.findtext("Name") if sub_entry is not None else ""
        if sub_name_key and sub_name_key.startswith("TEXT_PROJECT_"):
            nice = _lookup_name(indexes, sub_name_key)
            lines.append(f"Unlocks {nice or condition_name(sub)}")
        for line in render_effect_player(sub, indexes):
            lines.append(line)

    # Deduplicate while preserving order
    seen = set()
    deduped: list[str] = []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            deduped.append(ln)
    return deduped


# ────────────────────────────────────────────────────────────────────────────
# Shrine effects (improvement.xml entry → list of lines)
# ────────────────────────────────────────────────────────────────────────────

def render_shrine_effects(improvement_entry: ET.Element) -> list[str]:
    """Render a shrine's improvement entry into human-readable yield/modifier lines."""
    out: list[str] = []
    for pair in improvement_entry.findall("aiYieldOutput/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        out.append(f"{fmt_decimal(v)} {y}")

    for pair in improvement_entry.findall("aaiTileYieldRateAdjacentDouble/Pair"):
        tile = condition_name(pair.findtext("zIndex"))
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0") / 10
            out.append(f"{fmt_decimal(v)} {y}/{tile}")

    for pair in improvement_entry.findall("aaiTileYieldModifier/Pair"):
        tile = condition_name(pair.findtext("zIndex"))
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0")
            out.append(f"{fmt_decimal(v)}% {y}/{tile}")

    for pair in improvement_entry.findall("aaiImprovementYieldRateAdjacent/Pair"):
        imp = condition_name(pair.findtext("zIndex"))
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0") / 10
            out.append(f"{fmt_decimal(v)} {y}/{imp}")

    return out


if __name__ == "__main__":
    import json
    import sys

    xml_dir = Path(__file__).resolve().parent.parent / "reference" / "XML" / "Infos"
    idx = load_xml_indexes(xml_dir)
    targets = [
        "EFFECTPLAYER_NATION_ASSYRIA",
        "EFFECTPLAYER_NATION_BABYLONIA",
        "EFFECTPLAYER_NATION_CARTHAGE",
        "EFFECTPLAYER_NATION_EGYPT",
        "EFFECTPLAYER_NATION_GREECE",
        "EFFECTPLAYER_NATION_PERSIA",
        "EFFECTPLAYER_NATION_ROME",
    ]
    for t in targets:
        print(f"\n{t}:")
        for line in render_nation_effects(t, idx):
            print(f"  · {line}")
