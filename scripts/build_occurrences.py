#!/usr/bin/env python3
"""
Build src/data/occurrences.json from occurrence.xml + occurrenceClass.xml +
occurrenceLevel.xml (+ text-occurrence*.xml).

Occurrences are the game's persistent "world events": the Wrath of Gods
Calamities (plague, drought, flood, eruption…), scenario-driven world
transformations (Desolation, Ebbing Sea, Rejuvenation), and the era/crisis
occurrences from the base game, Behind the Throne, and Empires of the Indus.

Output shape:
  {
    "calamityClass": { id, name, dlc, dlcLabel, minRepeatPlayer,
                       maxPendingTurns, balanceDistribution, defaultLevel,
                       levels: [{id, name, help, minTurnsModifier,
                                 repeatTurnsModifier, aiMinTurns,
                                 aiSkipChance, noOccurrences, isDefault}] },
    "groups": [ { id, label, blurb, occurrences: [ … ] } ],
    "totals": { occurrences, calamities, byDlc: {label: n} }
  }

Each occurrence carries humanized line lists (trigger / effects / impact /
terrainChanges / traits / ending) plus flag chips, so the page just renders
strings through <LinkedText> + classifyYield.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_player, render_effect_city,
    render_effect_unit, render_bonus, _lookup_name, fmt_decimal, yield_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "occurrences.json"

# GameContentRequired token → DLC display name (from additionalContent.xml,
# hardcoded here because that file maps many tokens per DLC and these four
# are stable).
DLC_LABEL = {
    "CALAMITIES":           "Wrath of Gods",
    "EVENTPACK_SCANDAL":    "Behind the Throne",
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus",
    "BEHIND_THE_THRONE":    "Behind the Throne",
}

# SUBJECT_TILE_* have no Name in subject.xml — small display map.
SUBJECT_LABEL = {
    "SUBJECT_TILE_COASTAL_WATER": "Coastal Water",
    "SUBJECT_TILE_ARID":          "Arid",
    "SUBJECT_TILE_DESERT":        "Desert",
    "SUBJECT_TILE_RIVER":         "River",
    "SUBJECT_TILE_URBAN":         "Urban",
    "SUBJECT_TILE_TREES":         "Trees",
    "SUBJECT_TILE_VOLCANO":       "Volcano",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def b(entry: ET.Element, tag: str) -> bool:
    return (entry.findtext(tag) or "0") == "1"


def i(entry: ET.Element, tag: str) -> int:
    try:
        return int(entry.findtext(tag) or "0")
    except ValueError:
        return 0


def pct10000(v: int) -> str:
    """aaiTileTerrainChangeChance values are out of 10,000."""
    p = v / 100.0
    return f"{p:g}%"


class Labels:
    """Resolve TERRAIN_TARGET_* / TERRAIN_CHANGE_* / SUBJECT_TILE_* / TRAIT_*
    tokens to in-game display names via each file's Name key + the merged
    text index. Falls back to a title-cased token."""

    def __init__(self, indexes: dict):
        self.indexes = indexes
        self.maps: dict[str, dict[str, str]] = {}
        for fname in ("terrainTarget.xml", "terrainChange.xml", "trait.xml"):
            p = XML_DIR / fname
            if not p.exists():
                continue
            m: dict[str, str] = {}
            for e in ET.parse(p).getroot().findall("Entry"):
                z = e.findtext("zType") or ""
                nk = e.findtext("Name") or ""
                if z:
                    m[z] = _lookup_name(indexes, nk) or ""
            self.maps[fname] = m

    def _fallback(self, token: str) -> str:
        parts = token.split("_")
        # Drop the category prefix(es): TERRAIN_TARGET_X → X, SUBJECT_TILE_X → X
        for pre in ("TERRAIN_TARGET", "TERRAIN_CHANGE", "SUBJECT_TILE", "TRAIT", "MEMORYPLAYER"):
            pp = pre.split("_")
            if parts[: len(pp)] == pp:
                parts = parts[len(pp):]
                break
        return " ".join(p.title() for p in parts)

    def terrain(self, token: str | None) -> str:
        if not token:
            return ""
        for fname in ("terrainTarget.xml", "terrainChange.xml"):
            v = self.maps.get(fname, {}).get(token)
            if v:
                return v
        return self._fallback(token)

    def subject(self, token: str | None) -> str:
        if not token:
            return ""
        return SUBJECT_LABEL.get(token, self._fallback(token))

    def trait(self, token: str | None) -> str:
        if not token:
            return ""
        return self.maps.get("trait.xml", {}).get(token) or self._fallback(token)


# ── help-text cleaning ──────────────────────────────────────────────────────
# Occurrence HelpText uses link(TERRAIN_TARGET_COAST)-style markup; humanize's
# generic stripper renders that as "Target Coast". Resolve the tokens against
# our terrain/text labels instead.

_HELP_LINK_RE = re.compile(
    r"\{lowercase:link\(([A-Z0-9_]+)(?:,\d+)?\)\}|\blink\(([A-Z0-9_]+)(?:,\d+)?\)")


def load_raw_text(*filenames: str) -> dict[str, str]:
    """en-US first form, with link() markup left intact."""
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").split("~")[0].strip()
            if k and en:
                out.setdefault(k, en)
    return out


def clean_help(raw: str, labels: "Labels", text: dict[str, str]) -> str:
    def repl(m: "re.Match[str]") -> str:
        token = m.group(1) or m.group(2) or ""
        nice = text.get(f"TEXT_{token}", "")
        if not nice and (token.startswith("TERRAIN") or token.startswith("VEGETATION")):
            nice = labels.terrain(token)
        if not nice:
            parts = token.split("_")
            if len(parts) > 1:
                parts = parts[1:]
            nice = " ".join(p.title() for p in parts)
        return nice
    return _HELP_LINK_RE.sub(repl, raw)


# ── supplemental effect rendering ────────────────────────────────────────────
# Fields humanize.py doesn't cover yet. We render them here rather than
# editing humanize.py (kept out of scope for this builder).

def extra_effect_player_lines(ep: ET.Element) -> list[str]:
    out: list[str] = []
    v = i(ep, "iVisionChange")
    if v:
        out.append(f"{fmt_decimal(v)} Vision for all Units")
    v = i(ep, "iFamilyOpinionChange")
    if v:
        out.append(f"{fmt_decimal(v)} Family Opinion")
    v = i(ep, "iWorldReligionSpread")
    if v:
        out.append(f"+{v}% World Religion Spread Chance")
    return out


def extra_effect_city_lines(ec: ET.Element, labels: Labels, indexes: dict) -> list[str]:
    out: list[str] = []
    # Earthquake: −2 Stone on Urban tiles (aaiTerrainYield, value is 10× display)
    for pair in ec.findall("aaiTerrainYield/Pair"):
        terr = (pair.findtext("zIndex") or "").replace("TERRAIN_", "").title()
        sub = pair.find("SubPair")
        if sub is None:
            continue
        y = yield_name(sub.findtext("zSubIndex"))
        v = int(sub.findtext("iValue") or "0") / 10.0
        out.append(f"{fmt_decimal(v)} {y} on {terr} tiles")
    # Plague: units in territory have a chance per turn to catch the plague
    for triple in ec.findall("aaiTerritoryEffectUnitChanceTurns/Triple"):
        eu_id = triple.findtext("First") or ""
        chance = int(triple.findtext("Second") or "0")
        eu = indexes.get("effectUnit.xml", {}).get(eu_id)
        detail = ""
        if eu is not None:
            dmg = i(eu, "iDamageAlways")
            fat = i(eu, "iFatigueExtra")
            bits = []
            if dmg:
                bits.append(f"{dmg} damage/turn")
            if fat:
                bits.append(f"{fmt_decimal(fat)} Fatigue")
            if b(eu, "bApplyEffectUnitAdjacentOnly") or eu.find("AttackApplyEffectUnitTurns") is not None:
                bits.append("spreads on contact")
            detail = f" ({', '.join(bits)})" if bits else ""
        out.append(f"Units in territory: {chance}% chance/turn to be Plagued{detail}")
    return out


def extra_bonus_lines(bonus: ET.Element, indexes: dict) -> list[str]:
    out: list[str] = []
    # aeAllCityBonuses: a sub-bonus applied to every city (e.g. plague start
    # kills a citizen everywhere).
    for zv in bonus.findall("aeAllCityBonuses/zValue"):
        sub = indexes.get("bonus.xml", {}).get(zv.text or "")
        if sub is None:
            continue
        cit = i(sub, "iCitizens")
        if cit:
            n = abs(cit)
            verb = "Loses" if cit < 0 else "Gains"
            out.append(f"Every City {verb.lower()} {n} Citizen{'s' if n != 1 else ''}")
        for line in render_bonus(sub, indexes):
            out.append(f"{line} in every City")
    return out


# ── per-occurrence humanizers ───────────────────────────────────────────────

def trigger_lines(e: ET.Element, labels: Labels) -> list[str]:
    out: list[str] = []
    min_t, max_t = i(e, "iMinTurns"), i(e, "iMaxTurns")
    if min_t and max_t:
        out.append(f"Can occur between turn {min_t} and turn {max_t}")
    elif min_t:
        out.append(f"Can occur from turn {min_t}")
    elif max_t:
        out.append(f"Can occur until turn {max_t}")
    sc = i(e, "iStartChance")
    if sc:
        out.append(f"{sc}% chance per turn to trigger")
    tp = e.findtext("TerrainPrereq")
    if tp:
        out.append(f"Requires {labels.terrain(tp)} on the map")
    subjects = [labels.subject(z.text) for z in e.findall("aeTileTargetSubjectAny/zValue") if z.text]
    if subjects:
        owned = " player-owned" if b(e, "bTileTargetPlayerOwned") else ""
        out.append(f"Strikes a{owned} {' or '.join(subjects)} tile")
    elif b(e, "bTileTargetPlayerOwned"):
        out.append("Strikes a player-owned tile")
    at = e.findtext("AffectTerrain")
    if at:
        out.append(f"Affects all {labels.terrain(at)} tiles on the map")
    if b(e, "bAffectAllRiver"):
        out.append("Affects all river-adjacent tiles on the map")
    cont = e.findtext("TileContiguousTerrain")
    rng = i(e, "iTileContiguousRange")
    if cont:
        span = f" within {rng} tiles" if rng else ""
        out.append(f"Spreads across contiguous {labels.terrain(cont)}{span}")
    if b(e, "bTileContiguousFreshWater"):
        out.append("Spreads along contiguous fresh water and river tiles")
    if b(e, "bTileAffectAdjacent"):
        out.append("Also affects tiles adjacent to the affected area")
    ign = e.findtext("IgnoreTerrain")
    if ign:
        out.append(f"Ignores {labels.terrain(ign)} tiles")
    delay = i(e, "iDelayTurns")
    if delay:
        out.append(f"{delay}-turn warning before it strikes")
    rep, rep_p = i(e, "iRepeatTurns"), i(e, "iRepeatTurnsPlayer")
    if rep:
        out.append(f"At least {rep} turns between instances")
    if rep_p:
        out.append(f"At least {rep_p} turns between instances for the same player")
    return out


def impact_lines(e: ET.Element, labels: Labels, move_mult: int) -> list[str]:
    out: list[str] = []
    v = i(e, "iCityDamage")
    if v:
        out.append(f"Cities take {v} damage/turn")
    v = i(e, "iCityDamageCoastal")
    if v:
        out.append(f"Coastal Cities take {v} damage/turn")
    v = i(e, "iCityPillageImprovements")
    if v:
        out.append(f"Pillages {v} random improvement{'s' if v != 1 else ''} per City")
    v = i(e, "iCityPillageImprovementsCoast")
    if v:
        out.append(f"Pillages {v} random coastal improvement{'s' if v != 1 else ''} per City")
    v = i(e, "iTileUnitDamage")
    if v:
        out.append(f"Units on affected tiles take {v} damage/turn")
    if b(e, "bTilePillage"):
        out.append("Pillages all improvements on affected tiles")
    v = i(e, "iTilePillageChance")
    if v:
        out.append(f"{v}% chance to pillage each improvement on affected tiles")
    v = i(e, "iTileBaseYieldModifier")
    if v:
        out.append(f"{fmt_decimal(v)}% base yields on affected tiles")
    v = i(e, "iTileMovementCostExtra")
    if v:
        mv = v / move_mult if move_mult else v
        out.append(f"+{mv:g} movement cost on affected tiles")
    v = i(e, "iTileRevealChange")
    if v:
        out.append(f"-{v} visibility on affected tiles")
    if b(e, "bTileImpassable"):
        out.append("Affected tiles are impassable")
    if b(e, "bTileUnanchor"):
        out.append("Unanchors ships on affected tiles")
    v = i(e, "iTileVegetationReduceChance")
    if v:
        out.append(f"{v}% chance to destroy vegetation on affected tiles (pillaging improvements)")
    for pair in e.findall("aiVegetationReduceChance/Pair"):
        veg = (pair.findtext("zIndex") or "").replace("VEGETATION_", "").title()
        pv = int(pair.findtext("iValue") or "0")
        out.append(f"{pv}% chance to destroy {veg} on affected tiles")
    spread = i(e, "iVegetationReduceSpreadChance")
    if spread:
        div = i(e, "iVegetationReduceSpreadDivisor")
        halving = f", halving each step" if div == 2 else (f", ÷{div} each step" if div else "")
        out.append(f"Destruction spreads to adjacent tiles ({spread}% chance{halving})")
    return out


def terrain_changes(e: ET.Element, labels: Labels) -> list[dict]:
    out: list[dict] = []
    for pair in e.findall("aaiTileTerrainChangeChance/Pair"):
        frm = labels.terrain(pair.findtext("zIndex"))
        sub = pair.find("SubPair")
        if sub is None:
            continue
        to = labels.terrain(sub.findtext("zSubIndex"))
        v = int(sub.findtext("iValue") or "0")
        out.append({"from": frm, "to": to, "chance": pct10000(v)})
    return out


def trait_lines(e: ET.Element, labels: Labels, text: dict[str, str]) -> list[str]:
    out: list[str] = []
    for pair in e.findall("aiTraitProb/Pair"):
        t = labels.trait(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        out.append(f"Characters: {v}% chance/turn to become {t}")
    return out


def ending_lines(e: ET.Element, labels: Labels) -> list[str]:
    out: list[str] = []
    mn, mx = i(e, "iMinDuration"), i(e, "iMaxDuration")
    if mn and mx:
        if mn == mx:
            out.append(f"Lasts {mn} turn{'s' if mn != 1 else ''}")
        else:
            out.append(f"Lasts {mn}–{mx} turns")
    elif mx:
        out.append(f"Lasts up to {mx} turns")
    elif mn:
        out.append(f"Lasts at least {mn} turns")
    ec, inc = i(e, "iEndChance"), i(e, "iEndChanceIncrement")
    if ec and inc:
        out.append(f"{ec}% chance per turn to end, +{inc}% each turn")
    elif ec == 100:
        out.append("Ends immediately after it strikes")
    elif ec:
        out.append(f"{ec}% chance per turn to end")
    elif inc:
        out.append(f"Chance to end grows by {inc}% each turn")
    elif not mx:
        out.append("Does not end on its own")
    for pair in e.findall("aiTraitRemoveProbEnd/Pair"):
        t = labels.trait(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        chance = "" if v >= 100 else f"{v}% chance to "
        out.append(f"When it ends: {chance}{t} characters recover" if v >= 100
                   else f"When it ends: {v}% chance for {t} characters to recover")
    mem = e.findtext("MemoryPlayerInvalid")
    if mem:
        nice = mem.replace("MEMORYPLAYER_", "").replace("_", " ").title()
        out.append(f"Won't repeat while the {nice} memory lingers")
    return out


def flag_chips(e: ET.Element) -> list[str]:
    out: list[str] = []
    if b(e, "bMajor"):
        out.append("Major — only one major occurrence at a time")
    if b(e, "bForceGlobal"):
        out.append("Global")
    if b(e, "bNoDuplicates"):
        out.append("No duplicates")
    if not b(e, "bEncyclopedia") and e.findtext("bEncyclopedia") is not None:
        pass  # encyclopedia visibility isn't player-facing; skip
    return out


def effect_lines(e: ET.Element, labels: Labels, indexes: dict) -> list[str]:
    lines: list[str] = []
    sb_id = e.findtext("StartBonus")
    if sb_id:
        bonus = indexes.get("bonus.xml", {}).get(sb_id)
        if bonus is not None:
            for line in render_bonus(bonus, indexes):
                lines.append(f"On start: {line}")
            for line in extra_bonus_lines(bonus, indexes):
                lines.append(f"On start: {line}")
    ep_id = e.findtext("EffectPlayer")
    if ep_id:
        lines.extend(render_effect_player(ep_id, indexes))
        ep = indexes.get("effectPlayer.xml", {}).get(ep_id)
        if ep is not None:
            lines.extend(extra_effect_player_lines(ep))
            ec_id = ep.findtext("EffectCity")
            ec = indexes.get("effectCity.xml", {}).get(ec_id) if ec_id else None
            if ec is not None:
                lines.extend(extra_effect_city_lines(ec, labels, indexes))
            # Description text (e.g. Rally Defense's on-unit-lost bonus)
            desc_key = ep.findtext("Description")
            if desc_key:
                desc = _lookup_name(indexes, desc_key)
                if desc:
                    lines.append(desc)
    for tag, prefix in (("EffectCity", "Affected Cities: "),
                        ("EffectCityTerritory", "Cities with affected territory: ")):
        ec_id = e.findtext(tag)
        if not ec_id:
            continue
        ec = indexes.get("effectCity.xml", {}).get(ec_id)
        if ec is None:
            continue
        for line in render_effect_city(ec, per_city=False, indexes=indexes):
            lines.append(prefix + line)
        for line in extra_effect_city_lines(ec, labels, indexes):
            lines.append(prefix + line)
    eu_id = e.findtext("EffectUnit")
    if eu_id:
        eu = indexes.get("effectUnit.xml", {}).get(eu_id)
        if eu is not None:
            for line in render_effect_unit(eu):
                lines.append(f"Affected Units: {line}")
    # Dedupe, preserve order
    seen: set[str] = set()
    deduped: list[str] = []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            deduped.append(ln)
    return deduped


# ── grouping ────────────────────────────────────────────────────────────────

# Calamity pairing: OCCURRENCE_X + OCCURRENCE_X_MITIGATED. Variant suffixes
# for the world-transformation occurrences.
VARIANT_SUFFIXES = ("_SLOW", "_MEDIUM", "_FAST", "_GRADUAL", "_SHORT", "_LONG")


def variant_of(zt: str) -> tuple[str, str]:
    """OCCURRENCE_EVAPORATE_SLOW → ('OCCURRENCE_EVAPORATE', 'Slow')."""
    if zt.endswith("_MITIGATED"):
        return zt[: -len("_MITIGATED")], "Mitigated"
    for suf in VARIANT_SUFFIXES:
        if zt.endswith(suf):
            return zt[: -len(suf)], suf[1:].title()
    return zt, ""


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    labels = Labels(indexes)
    text = indexes["__text__"]
    raw_text = load_raw_text("text-occurrence-wog.xml", "text-occurrence-btt.xml")

    move_mult = 9
    for ge in parse("globalsInt.xml").findall("Entry"):
        if (ge.findtext("zType") or "") == "MOVEMENT_MULTIPLER":
            move_mult = int(ge.findtext("iValue") or "9")

    # ── occurrence class + levels (the Calamities game option) ──
    cls_entry = None
    for ce in parse("occurrenceClass.xml").findall("Entry"):
        if ce.findtext("zType"):
            cls_entry = ce
            break
    calamity_class = None
    if cls_entry is not None:
        default_level = cls_entry.findtext("DefaultOccurrenceLevel") or ""
        level_idx = {le.findtext("zType"): le for le in parse("occurrenceLevel.xml").findall("Entry") if le.findtext("zType")}
        levels = []
        for zv in cls_entry.findall("aeOccurrenceLevels/zValue"):
            le = level_idx.get(zv.text or "")
            if le is None:
                continue
            levels.append({
                "id": zv.text,
                "name": text.get(le.findtext("Name") or "", ""),
                "help": text.get((le.findtext("Help") or ""), ""),
                "minTurnsModifier": i(le, "iMinTurnsModifier"),
                "repeatTurnsModifier": i(le, "iRepeatTurnsModifier"),
                "aiMinTurns": i(le, "iAIMinTurns"),
                "aiSkipChance": i(le, "iAISkipChance"),
                "noOccurrences": b(le, "bNoOccurrences"),
                "isDefault": (zv.text == default_level),
            })
        dlc = cls_entry.findtext("GameContentRequired") or ""
        calamity_class = {
            "id": cls_entry.findtext("zType"),
            "name": text.get(cls_entry.findtext("Name") or "", "Calamities"),
            "dlc": dlc,
            "dlcLabel": DLC_LABEL.get(dlc, dlc.replace("_", " ").title()),
            "minRepeatPlayer": i(cls_entry, "iMinRepeatPlayer"),
            "maxPendingTurns": i(cls_entry, "iMaxPendingTurns"),
            "balanceDistribution": b(cls_entry, "bBalanceDistribution"),
            "defaultLevel": default_level,
            "levels": levels,
        }

    # ── occurrences ──
    occurrences: list[dict] = []
    for e in parse("occurrence.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        name = text.get(e.findtext("Name") or "", zt.replace("OCCURRENCE_", "").replace("_", " ").title())
        dlc = e.findtext("GameContentRequired") or ""
        cls = e.findtext("Class") or ""
        base_id, variant = variant_of(zt)
        help_key = e.findtext("HelpText") or ""

        occurrences.append({
            "id": zt,
            "slug": zt.replace("OCCURRENCE_", "").lower().replace("_", "-"),
            "name": name,
            "dlc": dlc,
            "dlcLabel": DLC_LABEL.get(dlc, dlc.replace("_", " ").title()) if dlc else "Base game",
            "classId": cls,
            "baseId": base_id,
            "variant": variant,
            "helpText": clean_help(raw_text.get(help_key, text.get(help_key, "")), labels, text) if help_key else "",
            "flags": flag_chips(e),
            "trigger": trigger_lines(e, labels),
            "effects": effect_lines(e, labels, indexes),
            "impact": impact_lines(e, labels, move_mult),
            "terrainChanges": [f"{tc['from']} → {tc['to']} ({tc['chance']} chance)"
                               for tc in terrain_changes(e, labels)],
            "terrainChangesRaw": terrain_changes(e, labels),
            "traits": trait_lines(e, labels, text),
            "ending": ending_lines(e, labels),
        })

    # ── groups ──
    def is_calamity(o: dict) -> bool:
        return o["classId"] == "OCCURRENCECLASS_CALAMITIES"

    def is_transformation(o: dict) -> bool:
        # CALAMITIES-content occurrences with no class: scenario/map-driven
        # world transformations (Ebbing Sea, Desolation, Tumbling Mountain,
        # Rejuvenation).
        return o["dlc"] == "CALAMITIES" and not o["classId"]

    calamities = [o for o in occurrences if is_calamity(o)]
    transformations = [o for o in occurrences if is_transformation(o)]
    eras = [o for o in occurrences if not is_calamity(o) and not is_transformation(o)]

    # Pair calamities: full strike + mitigated variant side by side.
    families: "OrderedDict[str, dict]" = OrderedDict()
    for o in calamities:
        fam = families.setdefault(o["baseId"], {
            "id": o["baseId"],
            "slug": o["baseId"].replace("OCCURRENCE_", "").lower().replace("_", "-"),
            "name": "",
            "full": None,
            "mitigated": None,
        })
        if o["variant"] == "Mitigated":
            fam["mitigated"] = o
        else:
            fam["full"] = o
            fam["name"] = o["name"]

    # Group transformations by base id (Slow/Medium/Fast/… variants together).
    trans_groups: "OrderedDict[str, dict]" = OrderedDict()
    for o in transformations:
        g = trans_groups.setdefault(o["baseId"], {
            "id": o["baseId"],
            "slug": o["baseId"].replace("OCCURRENCE_", "").lower().replace("_", "-"),
            "name": o["name"],
            "variants": [],
        })
        g["variants"].append(o)

    by_dlc: dict[str, int] = {}
    for o in occurrences:
        by_dlc[o["dlcLabel"]] = by_dlc.get(o["dlcLabel"], 0) + 1

    payload = {
        "calamityClass": calamity_class,
        "calamityFamilies": list(families.values()),
        "transformations": list(trans_groups.values()),
        "eras": eras,
        "totals": {
            "occurrences": len(occurrences),
            "calamities": len(calamities),
            "transformations": len(transformations),
            "eras": len(eras),
            "byDlc": by_dlc,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(occurrences)} occurrences "
          f"({len(families)} calamity families, {len(trans_groups)} transformations, {len(eras)} eras/crises)")
    for k, v in sorted(by_dlc.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
