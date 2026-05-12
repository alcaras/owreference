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

    # Merge bonus-event-*.xml entries into bonus.xml lookup
    bonus_idx = out.setdefault("bonus.xml", {})
    for p in xml_dir.glob("bonus-event-*.xml"):
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


_LINK_RE = re.compile(r"\{?lowercase:link\(([A-Z_]+)(?:,\d+)?\)\}?|link\(([A-Z_]+)(?:,\d+)?\)")


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
    # kind = "pct"  → render "+{val}% label"
    # kind = "int"  → render "{val} label"
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
]


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

    return out


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
