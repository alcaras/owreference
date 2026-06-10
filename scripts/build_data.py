#!/usr/bin/env python3
"""
Build src/data/nations.json and src/styles/nation-tokens.css from:
  - reference/XML/Infos/*.xml   (canonical game data)
  - src/data/annotations/nations.yaml  (human-curated descriptions, seeded from xlsx)

Run after `make sync` or any time XML changes.
Deterministic output for clean git diffs.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_nation_effects, render_shrine_effects,
    render_effect_player, render_effect_city, fmt_decimal, yield_name,
    _lookup_name,
)
try:  # registry backstop (used to de-dup curated trait scalars)
    import effects as _effects  # noqa: E402
except ImportError:
    _effects = None

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT_JSON = ROOT / "src" / "data" / "nations.json"
OUT_CSS = ROOT / "src" / "styles" / "nation-tokens.css"
ANNOTATIONS = ROOT / "src" / "data" / "annotations" / "nations.yaml"


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def first_form(s: str | None) -> str:
    """Game text strings are tilde-separated forms (singular~plural~adjective). Take the first."""
    if not s:
        return ""
    return s.split("~")[0].strip()


def load_text(filename: str) -> dict[str, str]:
    """Read a text-*.xml, return {zType: en-US first form}."""
    out: dict[str, str] = {}
    for entry in parse(filename).findall("Entry"):
        z = entry.findtext("zType")
        en = entry.findtext("en-US")
        if z and en:
            out[z] = first_form(en)
    return out


def load_colors() -> dict[str, dict[str, str]]:
    """Return {nation_id: {bg, text}} from color.xml."""
    colors: dict[str, dict[str, str]] = {}
    for entry in parse("color.xml").findall("Entry"):
        z = entry.findtext("zType") or ""
        hex_val = entry.findtext("zHexValue") or ""
        if not hex_val:
            continue
        # Normalize #RRGGBBAA → #RRGGBB
        if re.fullmatch(r"#[0-9a-fA-F]{8}", hex_val):
            hex_val = hex_val[:7]
        m = re.fullmatch(r"COLOR_(NATION_[A-Z_]+?)(_TEXT)?", z)
        if not m or "_FAMILY_" in m.group(1):
            continue
        nation = m.group(1)
        kind = "text" if m.group(2) else "bg"
        colors.setdefault(nation, {})[kind] = hex_val.lower()
    return colors


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(h: str) -> float:
    """Relative luminance per WCAG, 0..1."""
    def chan(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = hex_to_rgb(h)
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def best_fg(bg: str) -> str:
    """Pick black or white text for contrast against a tinted-down bg."""
    # In our dark theme cells, we overlay a 0.35-alpha black scrim on the bg.
    # That means the effective bg is darker than `bg` itself, so most colors want white text.
    # Only very light bgs (luma > 0.7) get black-ish text.
    return "#111418" if luminance(bg) > 0.65 else "#f5f6f8"


SHRINE_TYPE_PRIMARY_YIELD = {
    "WAR":        "TRAINING",
    "KINGSHIP":   "CIVICS",
    "WISDOM":     "SCIENCE",
    "SUN":        "ORDERS",
    "WATER":      "MONEY",
    "LOVE":       "GROWTH",
    "UNDERWORLD": "CULTURE",
    "HEARTH":     "CULTURE",
    "FIRE":       None,   # modifier-based: mines / lumber mills
    "HEALING":    None,   # modifier-based: grove / healer
    "HUNTING":    None,   # modifier-based: farms / camps / ranged
}
# Keyword fallback for FIRE/HEALING/HUNTING — match against yaml shrine text
SHRINE_TYPE_KEYWORDS = {
    "FIRE":    ["mine", "lumber"],
    "HEALING": ["grove", "healer"],
    "HUNTING": ["farm", "camp", "ranged"],
}


def _shrine_effect_lines(entry: ET.Element, indexes: dict | None) -> list[str]:
    """All non-output effect lines of a shrine improvement entry, XML-canonical.

    Mirrors the adjacency walks in build_shrines.py so the Nations page and
    the Shrines page describe shrines from the same fields. One deliberate
    difference: aiUnitTraitXP is shown RAW (+10 XP), matching the game's own
    HelpText.Improvement.cs (buildSignedTextVariable(iValue) — no /10 scale)
    and the legacy spreadsheet.
    """
    effects: list[str] = list(render_shrine_effects(entry))
    # The yield output is rendered separately — drop duplicates.
    outputs = set()
    for pair in entry.findall("aiYieldOutput/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        outputs.add(f"{fmt_decimal(v)} {y}")
    effects = [e for e in effects if e not in outputs]

    for pair in entry.findall("aiAdjacentImprovementClassModifier/Pair"):
        imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENTCLASS_", "").title()
        v = int(pair.findtext("iValue") or "0")
        effects.append(f"{fmt_decimal(v)}% adjacent {imp}")
    for pair in entry.findall("aiAdjacentImprovementModifier/Pair"):
        imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENT_", "").title()
        v = int(pair.findtext("iValue") or "0")
        effects.append(f"{fmt_decimal(v)}% adjacent {imp}")
    for pair in entry.findall("aaiAdjacentImprovementClassYield/Pair"):
        imp = (pair.findtext("zIndex") or "").replace("IMPROVEMENTCLASS_", "").title()
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0") / 10
            effects.append(f"{fmt_decimal(v)} {y}/adjacent {imp}")
    for pair in entry.findall("aiAdjacentResourceYieldOutput/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        effects.append(f"{fmt_decimal(v)} {y} per adjacent Resource")
    for pair in entry.findall("aiAdjacentWonderYieldOutput/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0") / 10
        effects.append(f"{fmt_decimal(v)} {y} per adjacent Wonder")
    for pair in entry.findall("aaiAdjacentHeightYieldModifier/Pair"):
        h = (pair.findtext("zIndex") or "").replace("HEIGHT_", "").title()
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0")
            effects.append(f"{fmt_decimal(v)}% {y}/adjacent {h}")
    # Unit-trait XP grants (e.g., War shrines → +10 XP for Infantry). Raw value.
    for pair in entry.findall("aiUnitTraitXP/Pair"):
        trait = (pair.findtext("zIndex") or "").replace("UNITTRAIT_", "").title()
        v = int(pair.findtext("iValue") or "0")
        effects.append(f"{fmt_decimal(v)} {trait} XP")
    # EffectCity attached to the shrine (extra per-city effects).
    ec_id = entry.findtext("EffectCity") or ""
    if ec_id and indexes is not None:
        ec = indexes.get("effectCity.xml", {}).get(ec_id)
        if ec is not None:
            for line in render_effect_city(ec, per_city=False, indexes=indexes):
                if line not in effects and line not in outputs:
                    effects.append(line)
    # de-dup, keep order
    seen: set[str] = set()
    return [e for e in effects if not (e in seen or seen.add(e))]


def load_shrines(indexes: dict | None = None) -> dict[str, list[dict]]:
    """Return {nation_id: [shrine_dict, ...]} sorted by iSubClass."""
    text_improvement = load_text("text-improvement.xml")
    out: dict[str, list[dict]] = {}
    for entry in parse("improvement.xml").findall("Entry"):
        if (entry.findtext("Class") or "") != "IMPROVEMENTCLASS_SHRINE":
            continue
        nation = entry.findtext("NationPrereq") or ""
        if not nation.startswith("NATION_"):
            continue
        zt = entry.findtext("zType") or ""
        name_key = entry.findtext("Name") or ""
        # Shrine of Ninurta → Ninurta (drop "Shrine of " prefix)
        full = text_improvement.get(name_key, zt.replace("IMPROVEMENT_SHRINE_", "").title())
        deity = full.replace("Shrine of ", "").strip()

        av = entry.findtext("AssetVariation") or ""
        type_match = re.match(r"ASSET_VARIATION_IMPROVEMENT_SHRINE_([A-Z]+)", av)
        type_key = type_match.group(1) if type_match else "UNKNOWN"

        sub = int(entry.findtext("iSubClass") or "0")

        primary_yield = SHRINE_TYPE_PRIMARY_YIELD.get(type_key)
        # Pull yield outputs to also show what the shrine itself produces
        outputs: list[dict] = []
        output_strs: list[str] = []
        for pair in entry.findall("aiYieldOutput/Pair"):
            yk = pair.findtext("zIndex") or ""
            iv = pair.findtext("iValue") or "0"
            if yk.startswith("YIELD_"):
                outputs.append({"yield": yk[6:].lower(), "value": int(iv)})
                output_strs.append(
                    f"{fmt_decimal(int(iv) / 10)} {yield_name(yk)}")

        # XML-canonical one-line effect (yield output + tile/adjacency
        # effects) — replaces the hand-curated yaml shrine strings.
        effect_str = ", ".join(
            output_strs + _shrine_effect_lines(entry, indexes))

        out.setdefault(nation, []).append({
            "id": zt,
            "name": deity,
            "fullName": full,
            "type": type_key,
            "typeLabel": type_key.title(),
            "subClass": sub,
            "primaryYield": primary_yield,
            "yieldOutput": outputs,
            "effectStr": effect_str,
        })
    for n in out:
        out[n].sort(key=lambda s: s["subClass"])
    return out


def match_yaml_shrines(yaml_shrines: list[str], xml_shrines: list[dict]) -> list[dict]:
    """For each yaml string, attach the matching XML shrine by primary yield (heuristic).
    Returns list of {effect, shrine} in yaml order."""
    if not yaml_shrines or not xml_shrines:
        return [{"effect": s, "shrine": None} for s in yaml_shrines]

    yield_to_shrine: dict[str, dict] = {}
    for s in xml_shrines:
        if s["primaryYield"]:
            yield_to_shrine.setdefault(s["primaryYield"], s)
    keyword_to_shrine: list[tuple[str, dict]] = []
    for s in xml_shrines:
        for kw in SHRINE_TYPE_KEYWORDS.get(s["type"], []):
            keyword_to_shrine.append((kw, s))

    used_ids: set[str] = set()
    pairs: list[dict] = []
    for effect in yaml_shrines:
        lower = effect.lower()
        chosen: dict | None = None
        # Try primary yield match
        for y, shrine in yield_to_shrine.items():
            yname = y.lower()
            short = {"orders": "order", "training": "training", "science": "sci",
                     "civics": "civic", "culture": "cult", "growth": "growth",
                     "money": "money"}.get(yname, yname)
            if short in lower and shrine["id"] not in used_ids:
                chosen = shrine
                break
        if not chosen:
            for kw, shrine in keyword_to_shrine:
                if kw in lower and shrine["id"] not in used_ids:
                    chosen = shrine
                    break
        if chosen:
            used_ids.add(chosen["id"])
        pairs.append({"effect": effect, "shrine": chosen})

    # Backfill any unmatched yaml entries with leftover XML shrines (by iSubClass)
    leftovers = [s for s in xml_shrines if s["id"] not in used_ids]
    for p in pairs:
        if p["shrine"] is None and leftovers:
            p["shrine"] = leftovers.pop(0)

    return pairs


_ROMAN = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}

def _format_id_name(zt: str, prefix: str) -> str:
    """CHARACTER_ASHUR_UBALLIT_I → 'Ashur Uballit I'; keeps Roman numerals upright."""
    s = zt[len(prefix):] if zt.startswith(prefix) else zt
    return " ".join(p if p in _ROMAN else p.title() for p in s.split("_"))


def _format_dlc(tag: str) -> str:
    """WONDERS_DYNASTIES → 'Wonders & Dynasties'."""
    if not tag:
        return ""
    return tag.replace("_", " & ").title()


def load_unit_traits() -> dict[str, str]:
    """For each unit id, return the slug of its primary unit-trait glyph
    (lowercase, e.g. UNIT_HOPLITE → 'infantry'). The glyph is the white
    silhouette shown inside the unit's shape on the map. Uses aeUnitTrait
    (the first listed wins) and falls back to UnitCycle for generic units."""
    out: dict[str, str] = {}
    CYCLE_TO_TRAIT = {
        "WORKER": "worker", "DISCIPLE": "disciple",
        "MILITARY_INFANTRY": "infantry", "MILITARY_RANGED": "ranged",
        "MILITARY_MOUNTED": "mounted", "MILITARY_SIEGE": "siege",
        "MILITARY_WATER": "ship",
    }
    if not (XML_DIR / "unit.xml").exists():
        return out
    for entry in parse("unit.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("UNIT_"):
            continue
        # Prefer the unit's first explicit trait
        for t in entry.findall("aeUnitTrait/zValue"):
            tk = (t.text or "").replace("UNITTRAIT_", "").lower()
            if tk:
                out[zt] = tk
                break
        if zt in out:
            continue
        # Fall back to UnitCycle for units without explicit traits (Scout, etc.)
        cycle = (entry.findtext("UnitCycle") or "").replace("UNITCYCLE_", "")
        if cycle in CYCLE_TO_TRAIT:
            out[zt] = CYCLE_TO_TRAIT[cycle]
    return out


def load_unit_name_map() -> dict[str, str]:
    """Map human-readable unit name → unit zType (for resolving the UU
    string 'Battering Ram / Siege Tower' to underlying UNIT_BATTERING_RAM /
    UNIT_SIEGE_TOWER for glyph lookup)."""
    out: dict[str, str] = {}
    text_unit = load_text("text-unit.xml") if (XML_DIR / "text-unit.xml").exists() else {}
    if not (XML_DIR / "unit.xml").exists():
        return out
    for entry in parse("unit.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("UNIT_"):
            continue
        name_key = entry.findtext("Name") or ""
        if not name_key:
            continue
        nice = text_unit.get(name_key, "")
        if nice:
            out[nice] = zt
    return out


# Culture-tier prereqs for nation-unique units (no TechPrereq — they unlock
# at a city Culture level; no CulturePrereq at all = buildable from the start).
_CULTURE_LABEL = {
    "": "Initial",
    "CULTURE_WEAK": "Weak",
    "CULTURE_DEVELOPING": "Developing",
    "CULTURE_STRONG": "Strong",
    "CULTURE_LEGENDARY": "Legendary",
}
_CULTURE_ORDER = {
    "": 0, "CULTURE_WEAK": 1, "CULTURE_DEVELOPING": 2,
    "CULTURE_STRONG": 3, "CULTURE_LEGENDARY": 4,
}


def _fmt_base_upgrade(base: int, upg: int | None, neg: bool = False) -> str:
    """'150' / '150/200' / '-2/-4' value formatting for two-stage UU lines."""
    sign = "-" if neg else ""
    if upg is None or upg == base:
        return f"{sign}{base}"
    return f"{sign}{base}/{sign}{upg}"


def load_unique_units(unit_traits: dict[str, str],
                      indexes: dict | None = None) -> dict[str, dict]:
    """XML-canonical unique-unit block per nation, derived from unit.xml.

    A nation's UU line is the chain base → upgrade (aeUpgradeUnit) within its
    own NationPrereq units (e.g., Hastatus → Legionary). When a nation has
    several unique roots (Yuezhi: Steppe Rider AND Kushan Cavalry line), the
    longest chain wins, tie-broken by highest end-of-chain Culture tier.

    Vision is the *effective* value the game shows: iVision plus the
    iVisionExtra of every EffectUnit the unit carries — both its own
    aeEffectUnit list and the EffectUnit implied by each UnitTrait
    (Unit.cs getVisionAt + setUnitType; e.g., Mounted +1, Siege/Elephant -1,
    Light Chariot's High Vision +1).
    """
    # Unit/effect names are spread across text files (text-unit.xml,
    # text-unit-hittite.xml, text-eoti.xml for DLC units…) — use the
    # humanizer's combined text map when available.
    all_text = (indexes or {}).get("__text__", {})
    text_unit = all_text or (load_text("text-unit.xml") if (XML_DIR / "text-unit.xml").exists() else {})
    text_effect_unit = all_text or (load_text("text-effectUnit.xml") if (XML_DIR / "text-effectUnit.xml").exists() else {})

    # UnitTrait → implied EffectUnit (unitTrait.xml <EffectUnit>)
    trait_effect: dict[str, str] = {}
    for entry in parse("unitTrait.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        eu = entry.findtext("EffectUnit") or ""
        if zt and eu:
            trait_effect[zt] = eu
    # EffectUnit → iVisionExtra
    vision_extra: dict[str, int] = {}
    for entry in parse("effectUnit.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        v = int(entry.findtext("iVisionExtra") or "0")
        if zt and v:
            vision_extra[zt] = v

    def _eff_name(eu: str) -> str:
        return text_effect_unit.get(
            f"TEXT_{eu}", eu.replace("EFFECTUNIT_", "").replace("_", " ").title())

    units: dict[str, dict] = {}
    by_nation: dict[str, list[str]] = defaultdict(list)
    for entry in parse("unit.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        nation = entry.findtext("NationPrereq") or ""
        if not zt.startswith("UNIT_") or not nation.startswith("NATION_"):
            continue
        traits = [t.text for t in entry.findall("aeUnitTrait/zValue") if t.text]
        effect_units = [t.text for t in entry.findall("aeEffectUnit/zValue") if t.text]
        vision = int(entry.findtext("iVision") or "0")
        for t in traits:
            vision += vision_extra.get(trait_effect.get(t, ""), 0)
        for eu in effect_units:
            vision += vision_extra.get(eu, 0)
        name_key = entry.findtext("Name") or f"TEXT_{zt}"
        units[zt] = {
            "id": zt,
            "nation": nation,
            "name": text_unit.get(name_key, zt.replace("UNIT_", "").replace("_", " ").title()),
            "culture": (entry.findtext("CulturePrereq") or "").strip(),
            "costs": [((p.findtext("zIndex") or ""), int(p.findtext("iValue") or "0"))
                      for p in entry.findall("aiYieldCost/Pair")],
            "consumption": [((p.findtext("zIndex") or ""), int(p.findtext("iValue") or "0"))
                            for p in entry.findall("aiYieldConsumption/Pair")],
            "movement": int(entry.findtext("iMovement") or "0"),
            "rangeMax": int(entry.findtext("iRangeMax") or "0"),
            "vision": vision,
            "traits": traits,
            "abilities": effect_units,
            "upgrades": [t.text for t in entry.findall("aeUpgradeUnit/zValue") if t.text],
        }
        by_nation[nation].append(zt)

    out: dict[str, dict] = {}
    for nation, ids in by_nation.items():
        idset = set(ids)
        upgrade_targets = {u for uid in ids for u in units[uid]["upgrades"] if u in idset}
        chains: list[list[str]] = []
        for root in ids:
            if root in upgrade_targets:
                continue
            chain = [root]
            cur = root
            while True:
                nxt = [u for u in units[cur]["upgrades"] if u in idset]
                if not nxt:
                    break
                cur = nxt[0]
                chain.append(cur)
            chains.append(chain)
        if not chains:
            continue
        chains.sort(key=lambda c: (
            -len(c), -_CULTURE_ORDER.get(units[c[-1]]["culture"], 0), c[0]))
        chain = chains[0]
        base = units[chain[0]]
        upg = units[chain[1]] if len(chain) > 1 else None

        # Cost: base-order yields, "50/100 Wood" when the upgrade differs.
        upg_costs = dict(upg["costs"]) if upg else {}
        cost_parts = [
            f"{_fmt_base_upgrade(v, upg_costs.get(yk) if upg else None)} {yield_name(yk)}"
            for yk, v in base["costs"]]
        # Upkeep: consumption as negatives; Training last (it's universal —
        # keeps the leading yield, and so the cell color, on the resource).
        upg_cons = dict(upg["consumption"]) if upg else {}
        cons = sorted(base["consumption"], key=lambda kv: kv[0] == "YIELD_TRAINING")
        upkeep_parts = [
            f"{_fmt_base_upgrade(v, upg_cons.get(yk) if upg else None, neg=True)} {yield_name(yk)}"
            for yk, v in cons]
        # Move / Range / Vision (base and upgrade agree for every UU line;
        # render a/b if a future patch splits them).
        ms_parts = [f"{_fmt_base_upgrade(base['movement'], upg['movement'] if upg else None)} Move"]
        if base["rangeMax"] or (upg and upg["rangeMax"]):
            ms_parts.append(f"{_fmt_base_upgrade(base['rangeMax'], upg['rangeMax'] if upg else None)} Range")
        ms_parts.append(f"{_fmt_base_upgrade(base['vision'], upg['vision'] if upg else None)} Vision")
        # Traits: unit traits (minus the implicit Promotable), union of the
        # chain in base order, then ability EffectUnits by display name.
        trait_words: list[str] = []
        for uid in chain:
            for t in units[uid]["traits"]:
                if t == "UNITTRAIT_PROMOTABLE":
                    continue
                w = t.replace("UNITTRAIT_", "").replace("_", " ").title()
                if w not in trait_words:
                    trait_words.append(w)
        for uid in chain:
            for eu in units[uid]["abilities"]:
                w = _eff_name(eu)
                if w not in trait_words:
                    trait_words.append(w)

        out[nation] = {
            "names": " / ".join(units[uid]["name"] for uid in chain),
            "traits": ", ".join(trait_words),
            "cost": ", ".join(cost_parts),
            "upkeep": ", ".join(upkeep_parts),
            "moveSight": ", ".join(ms_parts),
            "unitsResolved": [{
                "id": uid,
                "name": units[uid]["name"],
                "trait": unit_traits.get(uid, ""),
                "culture": _CULTURE_LABEL.get(units[uid]["culture"],
                                              units[uid]["culture"].replace("CULTURE_", "").title()),
            } for uid in chain],
        }
    return out


def load_portrait_map() -> dict[str, str]:
    """Map CHARACTER_PORTRAIT_X → underlying sprite name (HISTORICAL_PERSON_Y).
    Drives portrait resolution for named characters since the game's
    'PreferredPortrait' on each character points at a portrait id, not
    the sprite directly."""
    out: dict[str, str] = {}
    for p in XML_DIR.glob("characterPortrait*.xml"):
        # Skip the support files (Opinion/FeaturePoints/AgeInterpolation)
        if "Opinion" in p.name or "Feature" in p.name or "AgeInterpolation" in p.name:
            continue
        try:
            for entry in ET.parse(p).getroot().findall("Entry"):
                pid = entry.findtext("zType") or ""
                if not pid.startswith("CHARACTER_PORTRAIT_"):
                    continue
                # Use the ADULT sprite when present; fall back to first match
                adult = ""
                first = ""
                for pair in entry.findall("azAgeGroupSpriteNames/Pair"):
                    age = pair.findtext("zIndex") or ""
                    sprite = pair.findtext("zValue") or ""
                    if not sprite:
                        continue
                    if not first:
                        first = sprite
                    if age == "CHARACTER_AGE_GROUP_ADULT":
                        adult = sprite
                        break
                out[pid] = adult or first
        except ET.ParseError:
            continue
    return out


_RATING_LABEL = {
    "RATING_WISDOM": "Wisdom", "RATING_CHARISMA": "Charisma",
    "RATING_COURAGE": "Courage", "RATING_DISCIPLINE": "Discipline",
}
_TRAIT_ICON_DIR = ROOT / "public" / "img" / "icons" / "traits"


def _trait_ep_scalars(ep: "ET.Element") -> list[str]:
    """Scalar fields on a trait's EffectPlayer that the generic humanizer
    skips but the in-game trait tooltip shows (opinion shifts, religion
    spread, stat-triggered bonuses)."""
    out: list[str] = []
    simple = (
        ("iLeaderOpinionChange", "{v:+d} Leader Opinion"),
        ("iFamilyOpinionChange", "{v:+d} Family Opinion"),
        ("iReligionOpinionChange", "{v:+d} Religion Opinion"),
        ("iStateReligionSpread", "{v:+d}% State Religion Spread Chance"),
    )
    for fld, fmt in simple:
        v = int(ep.findtext(fld) or "0")
        if v:
            out.append(fmt.format(v=v))
    for pair in ep.findall("StatBonus/Pair"):
        stat = (pair.findtext("First") or "").replace("STAT_", "").replace(
            "_", " ").title()
        bonus = (pair.findtext("Second") or "").replace(
            "BONUS_", "").replace("_", " ").title()
        if stat and bonus:
            out.append(f"On {stat}: {bonus}")
    return out


# The fields _trait_ep_scalars curates. The registry backstop in
# humanize/effects now also renders these generically inside
# render_effect_player — subtract those generic lines so each fact shows
# once, in the curated phrasing.
_TRAIT_SCALAR_FIELDS = frozenset({
    "iLeaderOpinionChange", "iFamilyOpinionChange",
    "iReligionOpinionChange", "iStateReligionSpread", "StatBonus",
})


def _trait_scalar_generic_lines(ep: "ET.Element", indexes: dict | None) -> set[str]:
    """The registry-backstop renderings of _TRAIT_SCALAR_FIELDS for this
    EffectPlayer entry (to be removed in favor of the curated phrasing)."""
    if _effects is None:
        return set()
    reg = _effects.REGISTRY.get("effectPlayer", {})
    all_fields = {spec.get("xmlField") or key for key, spec in reg.items()}
    return set(_effects.extra_lines(
        ep, "effectPlayer",
        exclude=frozenset(all_fields - _TRAIT_SCALAR_FIELDS),
        indexes=indexes))


def _trait_detail(trait_id: str, label: str,
                   indexes: dict | None) -> dict:
    """Enrich a leader trait with its archetype-ness, glyph, and the
    effect lines the in-game tooltip shows (humanised from trait.xml).

    Archetype traits (TRAIT_*_ARCHETYPE) always have a glyph at
    img/icons/traits/<slug>.png — the page shows that instead of the word.
    """
    is_arch = trait_id.endswith("_ARCHETYPE")
    slug = (trait_id.replace("TRAIT_", "")
            .replace("_ARCHETYPE", "").lower())
    icon = (f"img/icons/traits/{slug}.png"
            if (_TRAIT_ICON_DIR / f"{slug}.png").exists() else None)

    effects: list[str] = []
    # Archetype traits: the icon speaks for itself — the user does NOT want
    # the archetype's kit re-explained here (it's on the Archetypes page).
    if not is_arch:
        tx = (indexes or {}).get("trait.xml", {}).get(trait_id)
        if tx is not None:
            # 1. Effect-player effects the humanizer already understands.
            for ref_field in ("EffectPlayer", "LeaderEffectPlayer"):
                ref = tx.findtext(ref_field)
                if not ref:
                    continue
                lines = render_effect_player(ref, indexes)
                # Scalar fields on the trait's effect-player — curated
                # phrasing below; drop the registry-backstop's generic
                # duplicates of the same fields first.
                ep = (indexes or {}).get("effectPlayer.xml", {}).get(ref)
                if ep is not None:
                    generic = _trait_scalar_generic_lines(ep, indexes)
                    lines = [ln for ln in lines if ln not in generic]
                    if ep.findall("StatBonus/Pair"):
                        # The registry can phrase StatBonus through more than
                        # one template — drop any generic form; the curated
                        # "On <stat>: <bonus>" lines below cover every pair.
                        lines = [ln for ln in lines
                                 if not ln.startswith("Stat Bonus: ")]
                effects.extend(lines)
                if ep is not None:
                    effects.extend(_trait_ep_scalars(ep))
            # 2. Trait-level opinion scalars (shown in-tooltip).
            for fld, fmt in (
                ("iOpinionSame", "{v:+d} Opinion (same trait)"),
                ("iReligionHeadModifier", "{v:+d} Opinion as Religion Head"),
                ("iFamilyHeadModifier", "{v:+d} Opinion as Family Head"),
            ):
                v = int(tx.findtext(fld) or "0")
                if v:
                    effects.append(fmt.format(v=v))
            # 3. Rating — aiRating, falling back to aiRatingFallback (many
            #    traits, e.g. Cunning/Infamous/Bold, only set the fallback).
            rating_pairs = tx.findall("aiRating/Pair") or tx.findall(
                "aiRatingFallback/Pair")
            for pair in rating_pairs:
                rk = pair.findtext("zIndex") or ""
                rv = int(pair.findtext("iValue") or "0")
                if rv and rk in _RATING_LABEL:
                    effects.append(f"{rv:+d} {_RATING_LABEL[rk]}")
    # de-dup, keep order
    seen: set[str] = set()
    effects = [e for e in effects if not (e in seen or seen.add(e))]

    return {
        "id": trait_id,
        "label": label,
        "archetype": is_arch,
        "slug": slug,
        "icon": icon,
        "effects": effects,
    }


def load_characters(indexes: dict | None = None) -> dict[str, dict]:
    """Index character.xml entries by zType. Each char carries
    aeTraits + PreferredPortrait so we can show founder traits + portrait."""
    out: dict[str, dict] = {}
    if not (XML_DIR / "character.xml").exists():
        return out
    # Pull names from every text-name*.xml variant; fall back to a
    # formatted version of the raw FirstName id.
    name_texts: dict[str, str] = {}
    for p in XML_DIR.glob("text-name*.xml"):
        try:
            for e in ET.parse(p).getroot().findall("Entry"):
                k = e.findtext("zType") or ""
                en = (e.findtext("en-US") or "").split("~")[0].strip()
                if not k or not en:
                    continue
                # Strip any leading <![CDATA[ markers / inline font tags.
                en = re.sub(r"<[^>]+>", "", en)
                # Use the simpler key only; skip _HISTORICAL variants
                # (those carry cuneiform / decorative Unicode).
                if "_HISTORICAL" in k or k.endswith("_H"):
                    continue
                name_texts[k] = en
        except ET.ParseError:
            continue
    text_trait = load_text("text-trait.xml") if (XML_DIR / "text-trait.xml").exists() else {}
    for entry in parse("character.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("CHARACTER_"):
            continue
        first_name_key = entry.findtext("FirstName") or ""
        text_key = f"TEXT_{first_name_key}" if first_name_key else ""
        display = name_texts.get(text_key) or _format_id_name(zt, "CHARACTER_")
        traits = []
        for t in entry.findall("aeTraits/zValue"):
            tk = t.text or ""
            if not tk:
                continue
            label = text_trait.get(
                f"TEXT_{tk}", tk.replace("TRAIT_", "").replace("_", " ").title())
            traits.append(_trait_detail(tk, label, indexes))
        out[zt] = {
            "name": display,
            "gender": entry.findtext("Gender") or "",
            "age": int(entry.findtext("iAge") or "0"),
            "preferredPortrait": entry.findtext("PreferredPortrait") or "",
            "url": entry.findtext("URL") or "",
            "traits": traits,
        }
    return out


def find_portrait(character_name: str, char_id: str = "", preferred_portrait: str = "",
                  portrait_map: dict[str, str] | None = None) -> str | None:
    """Return public/img path for the character's portrait.
    Priority:
      1. Resolve PreferredPortrait via characterPortrait.xml → sprite name
         (e.g. CHARACTER_PORTRAIT_AKSUM_KALEB → HISTORICAL_PERSON_KALEB).
      2. Slug-based fallback (display name + char id, with suffix variants).
      3. Glob-based fallback (any file starting with the slug).
    """
    PORTRAITS = [
        (ROOT / "public" / "img" / "portraits" / "historical", "historical"),
        (ROOT / "public" / "img" / "portraits" / "character_select", "character_select"),
    ]

    # 1. Try the explicit characterPortrait → sprite mapping
    if preferred_portrait and portrait_map:
        sprite = portrait_map.get(preferred_portrait, "")
        if sprite:
            # HISTORICAL_PERSON_KALEB → kaleb.png in historical/
            slug = ""
            for prefix in ("HISTORICAL_PERSON_", "CHARACTER_SELECT_"):
                if sprite.startswith(prefix):
                    slug = sprite[len(prefix):].lower()
                    break
            if slug:
                for pool, web in PORTRAITS:
                    candidate = pool / f"{slug}.png"
                    if candidate.exists():
                        return f"img/portraits/{web}/{candidate.name}"

    # 2. Build slug candidates from name and char_id (with common suffixes stripped)
    candidates: list[str] = []
    if character_name:
        candidates.append(re.sub(r"[ \-]+", "_", character_name).lower())
    if char_id and char_id.startswith("CHARACTER_"):
        candidates.append(char_id[len("CHARACTER_"):].lower())
    extra: list[str] = []
    for c in candidates:
        for suf in ("_leader", "_navigator", "_caesar_leader", "_caesar"):
            if c.endswith(suf):
                extra.append(c[: -len(suf)])
    candidates.extend(extra)

    seen: set[str] = set()
    for slug in candidates:
        if not slug or slug in seen:
            continue
        seen.add(slug)
        for pool, web in PORTRAITS:
            if not pool.exists():
                continue
            for suffix in ["", "_elder", "_adult", "_teen", "_senior"]:
                candidate = pool / f"{slug}{suffix}.png"
                if candidate.exists():
                    return f"img/portraits/{web}/{candidate.name}"

    # 3. Fuzzy prefix scan — match any file beginning with the slug
    for slug in seen:
        for pool, web in PORTRAITS:
            if not pool.exists() or len(slug) < 4:
                continue
            matches = sorted(pool.glob(f"{slug}*.png"))
            # Prefer the base portrait (no _elder/_adult suffix)
            matches.sort(key=lambda p: ("_elder" in p.name, "_senior" in p.name, p.name))
            if matches:
                return f"img/portraits/{web}/{matches[0].name}"
    return None


def load_royal_courts() -> dict[str, dict]:
    """XML-canonical start royal family per nation: the DefaultDynasty's
    FirstRuler plus the living members of that dynasty in character.xml.

    Emits the same shape the yaml used: {name, spouse, heir1, heir2, ...},
    each as '<Traits> <Archetype> (<age>)' — e.g. 'Pious Commander (22)' —
    so the Nations table renders unchanged.

    Notes on derivation (all plain character.xml facts, no game-logic guess):
      - membership: aePlayerDynasties contains the DefaultDynasty;
        characters with iYearsDead are dead at start and skipped.
      - spouse(s): Spouse link with the leader (Maurya has two).
      - 'heirs' are the remaining living members, labeled by family relation
        (Father/Mother/Spouse links) and grouped children → grandchildren →
        siblings → other kin; TRAIT_EXCLUDED members (barred from the
        succession, e.g. the Hittite court) are skipped. The true in-game
        heir ORDER is succession-law logic; this grouping reproduces the
        observed starts without simulating it.
    """
    if not (XML_DIR / "dynasty.xml").exists() or not (XML_DIR / "character.xml").exists():
        return {}
    text_trait = load_text("text-trait.xml") if (XML_DIR / "text-trait.xml").exists() else {}

    dyn_ruler: dict[str, str] = {}
    for entry in parse("dynasty.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if zt:
            dyn_ruler[zt] = entry.findtext("FirstRuler") or entry.findtext("Founder") or ""

    chars: dict[str, dict] = {}
    for entry in parse("character.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("CHARACTER_"):
            continue
        chars[zt] = {
            "id": zt,
            "age": int(entry.findtext("iAge") or "0"),
            "gender": entry.findtext("Gender") or "",
            "traits": [t.text for t in entry.findall("aeTraits/zValue") if t.text],
            "father": entry.findtext("Father") or "",
            "mother": entry.findtext("Mother") or "",
            "spouse": entry.findtext("Spouse") or "",
            "dead": bool((entry.findtext("iYearsDead") or "").strip()),
            "dynasties": [t.text for t in entry.findall("aePlayerDynasties/zValue") if t.text],
        }

    def label(trait: str) -> str:
        return text_trait.get(
            f"TEXT_{trait}",
            trait.replace("TRAIT_", "").replace("_ARCHETYPE", "").replace("_", " ").title())

    def desc(c: dict) -> str:
        flavors = [label(t) for t in c["traits"] if not t.endswith("_ARCHETYPE")]
        arch = [label(t) for t in c["traits"] if t.endswith("_ARCHETYPE")]
        words = " ".join(flavors + arch)
        return f"{words} ({c['age']})" if words else f"({c['age']})"

    def parents(c: dict) -> set[str]:
        return {p for p in (c["father"], c["mother"]) if p}

    def fem(c: dict) -> bool:
        return c["gender"] == "GENDER_FEMALE"

    out: dict[str, dict] = {}
    for entry in parse("nation.xml").findall("Entry"):
        nation = entry.findtext("zType") or ""
        dd = entry.findtext("DefaultDynasty") or ""
        leader_id = dyn_ruler.get(dd, "")
        leader = chars.get(leader_id)
        if not nation.startswith("NATION_") or leader is None:
            continue
        members = [c for c in chars.values()
                   if dd in c["dynasties"] and c["id"] != leader_id]
        alive = [c for c in members if not c["dead"]]
        # Spouse links count even when the spouse is dead at start (needed
        # for step-/in-law relations, e.g. Hatshepsut ↔ Thutmose II).
        spouse_ids_all = {c["id"] for c in members
                          if c["spouse"] == leader_id or leader["spouse"] == c["id"]}
        spouses = [c for c in alive if c["id"] in spouse_ids_all]

        leader_parents = parents(leader)
        grandparent_ids = {gp for p in leader_parents
                           for gp in parents(chars.get(p, {"father": "", "mother": ""}))}

        def rel(c: dict) -> tuple[int, str]:
            """(sort-group, relationship label) for a living court member."""
            ps = parents(c)
            if leader_id in ps:
                return 0, ("daughter" if fem(c) else "son")
            if ps & spouse_ids_all:
                return 0, ("stepdaughter" if fem(c) else "stepson")
            if any(leader_id in parents(chars.get(p, {"father": "", "mother": ""})) for p in ps):
                return 1, ("granddaughter" if fem(c) else "grandson")
            if leader_parents and ps & leader_parents:
                return 2, ("sister" if fem(c) else "brother")
            if c["id"] in leader_parents:
                return 3, ("mother" if fem(c) else "father")
            if c["id"] in grandparent_ids:
                return 3, ("grandmother" if fem(c) else "grandfather")
            if any(ps & parents(chars[s]) for s in spouse_ids_all if s in chars):
                return 3, ("sister-in-law" if fem(c) else "brother-in-law")
            if c["spouse"] in spouse_ids_all:
                return 3, ("co-wife" if fem(c) else "co-husband")
            return 3, "kin"

        heirs = [c for c in alive
                 if c["id"] not in spouse_ids_all and "TRAIT_EXCLUDED" not in c["traits"]]
        keyed = sorted(((rel(c), c) for c in heirs),
                       key=lambda rc: (rc[0][0], -rc[1]["age"], rc[1]["id"]))

        court: dict[str, str] = {"name": desc(leader)}
        if spouses:
            court["spouse"] = " / ".join(desc(c) for c in spouses)
        for i, ((_, relation), c) in enumerate(keyed, start=1):
            flavors_or_arch = [t for t in c["traits"]]
            court[f"heir{i}"] = (f"{relation}, {desc(c)}" if flavors_or_arch
                                 else f"{relation} ({c['age']})")
        out[nation] = court
    return out


def load_dynasties(characters: dict[str, dict], portrait_map: dict[str, str]) -> dict[str, list[dict]]:
    """Return {nation_id: [dynasty_dict, ...]} from dynasty.xml. Each dynasty
    is enriched with its founder character's traits and portrait."""
    text_infos = load_text("text-infos.xml")
    out: dict[str, list[dict]] = {}
    if not (XML_DIR / "dynasty.xml").exists():
        return out
    for entry in parse("dynasty.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("DYNASTY_"):
            continue
        nation = entry.findtext("Nation") or ""
        if not nation:
            continue
        name = text_infos.get(entry.findtext("Name") or "", _format_id_name(zt, "DYNASTY_"))
        desc = text_infos.get(entry.findtext("Description") or "", "")
        founder_id = entry.findtext("Founder") or ""
        first_ruler_id = entry.findtext("FirstRuler") or ""
        founder = characters.get(founder_id) if founder_id else None
        first_ruler = characters.get(first_ruler_id) if first_ruler_id else None
        # Prefer the FirstRuler for portrait + traits — the dynasty's playable
        # leader at game start. Fall back to founder.
        primary = first_ruler or founder
        primary_name = first_ruler["name"] if first_ruler else (founder["name"] if founder else "")
        primary_id = first_ruler_id if first_ruler else founder_id
        preferred = primary["preferredPortrait"] if primary else ""
        portrait = find_portrait(primary_name, primary_id, preferred, portrait_map) if (primary_name or primary_id) else None
        out.setdefault(nation, []).append({
            "id": zt,
            "slug": zt.replace("DYNASTY_", "").lower(),
            "name": name,
            "description": desc,
            "founder": founder["name"] if founder else None,
            "firstRuler": first_ruler["name"] if first_ruler else None,
            "leaderAge": primary["age"] if primary else None,
            "leaderTraits": primary["traits"] if primary else [],
            "leaderUrl": primary["url"] if primary else "",
            "portrait": portrait,
            "gameContent": _format_dlc(entry.findtext("GameContentRequired") or ""),
        })
    return out


def load_nations() -> list[dict]:
    text_nation = load_text("text-nation.xml")
    text_family = load_text("text-family.xml")
    text_infos = load_text("text-infos.xml")
    text_unit = load_text("text-unit.xml") if (XML_DIR / "text-unit.xml").exists() else {}
    colors = load_colors()
    xml_indexes = load_xml_indexes(XML_DIR)
    shrines_by_nation = load_shrines(xml_indexes)
    characters = load_characters(xml_indexes)
    portrait_map = load_portrait_map()
    unit_traits = load_unit_traits()
    unit_name_to_id = load_unit_name_map()
    unique_units = load_unique_units(unit_traits, xml_indexes)
    royal_courts = load_royal_courts()
    dynasties_by_nation = load_dynasties(characters, portrait_map)
    text_cityname = load_text("text-cityname.xml") if (XML_DIR / "text-cityname.xml").exists() else {}
    text_name = load_text("text-name.xml") if (XML_DIR / "text-name.xml").exists() else {}
    text_unit_for_starts = load_text("text-unit.xml") if (XML_DIR / "text-unit.xml").exists() else {}

    # Per-nation per-family hex (e.g., COLOR_NATION_ASSYRIA_FAMILY_01 → #b53c01).
    # Also alias the YEUZHI typo so the Yuezhi families pick up colors.
    family_hex: dict[tuple[str, int], str] = {}
    for entry in parse("color.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        hex_val = (entry.findtext("zHexValue") or "")
        m = re.fullmatch(r"COLOR_(NATION_[A-Z_]+)_FAMILY_(\d+)", zt)
        if m and hex_val:
            if re.fullmatch(r"#[0-9a-fA-F]{8}", hex_val):
                hex_val = hex_val[:7]
            family_hex[(m.group(1), int(m.group(2)))] = hex_val.lower()
            if m.group(1) == "NATION_YEUZHI":
                family_hex[("NATION_YUEZHI", int(m.group(2)))] = hex_val.lower()

    # Map family → (nation_id, class). Prefer abNation (canonical nation
    # reference) over TeamColor — Yuezhi has a typo'd TEAMCOLOR_NATION_YEUZHI
    # in the game data while abNation correctly says NATION_YUEZHI.
    families_by_nation: dict[str, list[dict]] = defaultdict(list)
    for entry in parse("family.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        name_key = entry.findtext("Name") or ""
        team_color = entry.findtext("TeamColor") or ""
        family_class = entry.findtext("FamilyClass") or ""
        color_idx = entry.findtext("iColorIndex") or "0"
        if not zt:
            continue
        nation = ""
        ab_nation_pairs = entry.findall("abNation/Pair")
        for p in ab_nation_pairs:
            if (p.findtext("bValue") or "0") == "1":
                nation = p.findtext("zIndex") or ""
                break
        if not nation and team_color.startswith("TEAMCOLOR_NATION_"):
            nation = team_color.replace("TEAMCOLOR_", "")
        if not nation:
            continue
        class_key = f"TEXT_{family_class}"  # TEXT_FAMILYCLASS_CHAMPIONS
        # XML uses 1-based slot numbers (FAMILY_01..04); iColorIndex is 0-based.
        slot = int(color_idx) + 1
        hex_color = family_hex.get((nation, slot))
        class_label = text_infos.get(class_key, family_class.replace("FAMILYCLASS_", "").title())
        fam_obj = {
            "id": zt,
            "name": text_family.get(name_key, zt.replace("FAMILY_", "").title()),
            "class": class_label,
            "classKey": family_class.replace("FAMILYCLASS_", "").lower(),
            "colorIndex": int(color_idx),
            "ingameColor": hex_color,
            "ingameFg": best_fg(hex_color) if hex_color else "#f5f6f8",
        }
        # Coalition supremacy (Tamil): family.xml SupremacyEffectPlayer — the
        # capital city's family grants its supremacy effects all game
        # (City.cs founding hook, gated on nation.xml bCoalition).
        sup_id = entry.findtext("SupremacyEffectPlayer") or ""
        if sup_id:
            sup_entry = xml_indexes.get("effectPlayer.xml", {}).get(sup_id)
            sup_name = ""
            if sup_entry is not None:
                sup_name = _lookup_name(xml_indexes, sup_entry.findtext("Name") or "")
            sup_effects = [
                ln for ln in render_effect_player(sup_id, xml_indexes)
                # drop the entry's own display name echoed via ExtraHelp
                if ln != sup_name
            ]
            fam_obj["supremacy"] = {
                "id": sup_id,
                "name": sup_name or sup_id.replace("EFFECTPLAYER_", "").title(),
                "effects": sup_effects,
            }
        families_by_nation[nation].append(fam_obj)

    # Build nations
    nations = []
    for entry in parse("nation.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt or not zt.startswith("NATION_"):
            continue
        gendered = entry.findtext("GenderedName") or ""
        # GENDERED_TEXT_NATION_ASSYRIA → TEXT_NATION_ASSYRIA
        text_key = gendered.replace("GENDERED_", "")
        name = text_nation.get(text_key, zt.replace("NATION_", "").title())

        starting_tech = [t.text.replace("TECH_", "").replace("_", " ").title()
                         for t in entry.findall("aeStartingTech/zValue") if t.text]
        starting_law = [t.text.replace("LAW_", "").replace("_", " ").title()
                        for t in entry.findall("aeStartingLaw/zValue") if t.text]
        dynasties = [t.text.replace("DYNASTY_", "").title()
                     for t in entry.findall("aeDynasties/zValue") if t.text]

        c = colors.get(zt, {"bg": "#444", "text": "#aaa"})
        bg = c.get("bg", "#444")
        fg = best_fg(bg)

        fams = sorted(families_by_nation.get(zt, []), key=lambda f: f["colorIndex"])
        nation_shrines = shrines_by_nation.get(zt, [])

        # City names (resolved to display text)
        city_names = []
        for cn in entry.findall("aeCityNames/zValue"):
            key = cn.text or ""
            if key:
                city_names.append(text_cityname.get(key, key.replace("CITYNAME_", "").title()))

        # First name pools
        first_names_male = []
        for nm in entry.findall("aeFirstNamesMale/zValue"):
            key = nm.text or ""
            if key:
                first_names_male.append(text_name.get(key, key.replace("NAME_", "").title()))
        first_names_female = []
        for nm in entry.findall("aeFirstNamesFemale/zValue"):
            key = nm.text or ""
            if key:
                first_names_female.append(text_name.get(key, key.replace("NAME_", "").title()))

        def _unit_pair(pair):
            uk = (pair.findtext("zIndex") or "")
            n_count = int(pair.findtext("iValue") or "0")
            if not uk:
                return None
            return {
                "id": uk,
                "name": text_unit_for_starts.get(f"TEXT_{uk}", uk.replace("UNIT_", "").replace("_", " ").title()),
                "count": n_count,
                "slug": uk.replace("UNIT_", "").lower().replace("_", "-"),
                "trait": unit_traits.get(uk, ""),
            }
        # Starting units (the first turn): pairs of (unit, count)
        start_units = [u for u in (_unit_pair(p) for p in entry.findall("aiStartUnit/Pair")) if u]
        # Initial city units (Worker, etc. spawned with the capital)
        city_units = [u for u in (_unit_pair(p) for p in entry.findall("aiCityUnit/Pair")) if u]

        first_build_id = entry.findtext("FirstBuild") or ""
        first_build_name = text_unit_for_starts.get(f"TEXT_{first_build_id}", first_build_id.replace("UNIT_", "").title()) if first_build_id else ""

        # Title labels
        leader_title = text_infos.get(entry.findtext("LeaderTitle") or "", "")
        heir_title = text_infos.get(entry.findtext("HeirTitle") or "", "")
        regent_title = text_infos.get(entry.findtext("RegentTitle") or "", "")
        successor_title = text_infos.get(entry.findtext("SuccessorTitle") or "", "")

        # Auto-derived bonus list from the game's effect tree.
        effect_player_id = (entry.findtext("EffectPlayer") or "").strip()
        effects_xml = render_nation_effects(effect_player_id, xml_indexes) if effect_player_id else []

        # Auto-derived shrine effects (per shrine)
        for s in nation_shrines:
            shrine_entry = xml_indexes.get("improvement.xml", {}).get(s["id"])
            if shrine_entry is not None:
                s["effectsXml"] = render_shrine_effects(shrine_entry)

        # XML-canonical shrine pairs ({effect, shrine}) — same shape the
        # yaml-matched pairs had, so the pages render unchanged. yaml
        # shrines (if any reappear in annotations) still win in merge.
        shrine_pairs = [{"effect": s["effectStr"], "shrine": s}
                        for s in nation_shrines]

        nations.append({
            "id": zt,
            "slug": zt.replace("NATION_", "").lower(),
            "name": name,
            "color": {"bg": bg, "fg": fg, "ingameText": c.get("text", bg)},
            "startingTech": starting_tech,
            "startingLaw": starting_law,
            "dynasties": dynasties,
            "dynastyDetails": dynasties_by_nation.get(zt, []),
            "families": fams,
            "shrineXml": nation_shrines,
            "shrines": shrine_pairs,
            "uniqueUnit": unique_units.get(zt, {}),
            "leader": royal_courts.get(zt, {}),
            "effectsXml": effects_xml,
            "cityNames": city_names,
            "firstNamesMale": first_names_male,
            "firstNamesFemale": first_names_female,
            "startUnits": start_units,
            "cityUnits": city_units,
            "firstBuild": {"id": first_build_id, "name": first_build_name} if first_build_id else None,
            "titles": {
                "leader": leader_title,
                "heir": heir_title,
                "regent": regent_title,
                "successor": successor_title,
            },
            "playable": (entry.findtext("bPlayable") == "1") or entry.findtext("bPlayable") is None,
            "gameContent": entry.findtext("GameContentRequired") or "",
        })

    # Stable order — by slug
    nations.sort(key=lambda n: n["slug"])
    return nations


def load_annotations() -> dict:
    if not ANNOTATIONS.exists():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        print("⚠ pyyaml not installed; skipping annotations layer", file=sys.stderr)
        return {}
    return yaml.safe_load(ANNOTATIONS.read_text()) or {}


def merge_annotations(nations: list[dict], annotations: dict,
                      unit_name_to_id: dict[str, str] | None = None,
                      unit_traits: dict[str, str] | None = None) -> list[dict]:
    """Overlay human-curated text onto canonical XML data — yaml wins for any
    key it still carries (today: only `bonuses`, for the nations whose
    EffectPlayer tree under-describes the kit — Aksum/Kush/Tamil/Yuezhi).
    Shrines / uniqueUnit / leader are XML-derived in load_nations(); if a
    yaml entry reappears for those, it overrides here (shrines get paired
    with XML shrines by primary yield, UU names get resolved to unit ids)."""
    by_slug = {n["slug"]: n for n in nations}
    for slug, ann in (annotations.get("nations") or {}).items():
        if slug not in by_slug:
            continue
        n = by_slug[slug]
        if "bonuses" in ann:
            n["bonuses"] = ann.get("bonuses") or []
        if "shrines" in ann:
            yaml_shrines = ann.get("shrines") or []
            n["shrines"] = match_yaml_shrines(yaml_shrines, n.get("shrineXml", []) or [])
        if "uniqueUnit" in ann:
            uu = dict(ann.get("uniqueUnit") or {})
            # Resolve UU names → underlying unit ids + trait glyphs
            if uu.get("names") and unit_name_to_id is not None:
                resolved = []
                for part in [p.strip() for p in str(uu["names"]).split("/")]:
                    uid = unit_name_to_id.get(part, "")
                    trait = (unit_traits or {}).get(uid, "") if uid else ""
                    resolved.append({"name": part, "id": uid, "trait": trait})
                uu["unitsResolved"] = resolved
            n["uniqueUnit"] = uu
        if "leader" in ann:
            n["leader"] = ann.get("leader") or {}
    return nations


def write_css(nations: list[dict]) -> None:
    lines = [
        "/* Generated by scripts/build_data.py — do not edit by hand. */",
        "/* Each nation gets a CSS class with --nation-bg and --nation-fg tokens. */",
        "",
    ]
    for n in nations:
        lines.append(f".n-{n['slug']} {{")
        lines.append(f"  --nation-bg: {n['color']['bg']};")
        lines.append(f"  --nation-fg: {n['color']['fg']};")
        lines.append(f"  --nation-ingame: {n['color']['ingameText']};")
        lines.append("}")
    OUT_CSS.write_text("\n".join(lines) + "\n")


def main() -> int:
    nations = load_nations()
    annotations = load_annotations()
    nations = merge_annotations(nations, annotations, load_unit_name_map(), load_unit_traits())

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(nations, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    write_css(nations)
    print(f"✓ wrote {OUT_JSON.relative_to(ROOT)} ({len(nations)} nations)")
    print(f"✓ wrote {OUT_CSS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
