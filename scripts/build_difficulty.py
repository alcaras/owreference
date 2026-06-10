#!/usr/bin/env python3
"""
Build src/data/difficulty.json from difficultyMode.xml + difficulty.xml +
advantage.xml (and the level files each mode composes).

Naming quirk (verified against text-infos.xml + game source):
  - difficultyMode.xml holds the *named* difficulties players pick
    ("The New" … "The Great"). Each one is a preset bundling six dials:
    Prosperity, AI Development, AI Aggression (opponentLevel), Tribal Level,
    AI Handicap (advantage), and Calamities (occurrenceLevel).
  - difficulty.xml is the **Prosperity** dial (TEXT_DIFFICULTY_ABLE =
    "Affluent" … TEXT_DIFFICULTY_GREAT = "Fragile"): the player's starting
    stockpile, base per-turn yields, base city money/discontent, empty-site
    share, distant-raid pressure, and angry-family rebel chance.
  - AI nations always play at Prosperity "Thriving" (globalsType.xml
    AI_DIFFICULTY = DIFFICULTY_STRONG), regardless of the chosen mode.

Scaling rules (verified in reference/Source):
  - aiYieldStockpile values are *display* numbers — Player.cs multiplies them
    by Constants.YIELDS_MULTIPLIER on grant. Do NOT divide by 10.
  - EffectPlayer/EffectCity aiYieldRate values are internal tenths — the
    shared humanizer divides by 10, as everywhere else on the site.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    fmt_decimal, load_xml_indexes, render_effect_player, yield_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "difficulty.json"


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def text_of(indexes: dict, key: str, fallback: str = "") -> str:
    return indexes.get("__text__", {}).get(key, fallback)


def entry_name(indexes: dict, entry: ET.Element, prefix: str) -> str:
    """Resolve an entry's Name text key, falling back to its zType token."""
    z = entry.findtext("zType") or ""
    name_key = entry.findtext("Name") or ""
    return text_of(indexes, name_key) or z.replace(prefix, "").replace("_", " ").title()


def int_of(e: ET.Element, tag: str) -> int:
    v = e.findtext(tag)
    try:
        return int(v) if v else 0
    except ValueError:
        return 0


# ── Local renderers for fields the shared humanizer doesn't cover ──────────
# (humanize.py is off-limits per task constraints; these are difficulty-only
# fields, rendered here with the same phrasing conventions.)

def extra_effect_city_lines(ec: ET.Element) -> list[str]:
    """EffectCity scalars render_effect_city skips: specialist/project cost,
    free XP for newly built units (City.getBuildUnitXP)."""
    out: list[str] = []
    v = int_of(ec, "iSpecialistCostModifier")
    if v:
        out.append(f"{fmt_decimal(v)}% Specialist Cost")
    v = int_of(ec, "iProjectCostModifier")
    if v:
        out.append(f"{fmt_decimal(v)}% Project Cost")
    v = int_of(ec, "iUnitXP")
    if v:
        out.append(f"{fmt_decimal(v)} XP for new Units")
    return out


def extra_effect_unit_lines(eu: ET.Element) -> list[str]:
    """render_effect_unit skips iStrengthModifier (the advantage penalties'
    -5/-10/-25% unit strength)."""
    out: list[str] = []
    v = int_of(eu, "iStrengthModifier")
    if v:
        out.append(f"{fmt_decimal(v)}% Unit Strength")
    return out


def effect_player_lines(ep_id: str, indexes: dict) -> list[str]:
    """Shared humanizer first, then the locally-rendered leftovers."""
    if not ep_id:
        return []
    lines = list(render_effect_player(ep_id, indexes))
    ep = indexes.get("effectPlayer.xml", {}).get(ep_id)
    if ep is not None:
        ec_id = ep.findtext("EffectCity") or ""
        ec = indexes.get("effectCity.xml", {}).get(ec_id)
        if ec is not None:
            lines.extend(extra_effect_city_lines(ec))
        eu_id = ep.findtext("EffectUnit") or ""
        eu = indexes.get("effectUnit.xml", {}).get(eu_id)
        if eu is not None:
            lines.extend(extra_effect_unit_lines(eu))
    # Dedupe, preserve order
    seen: set[str] = set()
    return [ln for ln in lines if not (ln in seen or seen.add(ln))]


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)

    # ── Globals: which prosperity the AI uses, default modes ────────────────
    globals_type = {e.findtext("zType"): (e.findtext("zValue") or "")
                    for e in parse("globalsType.xml").findall("Entry")}
    ai_prosperity_id = globals_type.get("AI_DIFFICULTY", "DIFFICULTY_STRONG")
    default_mode_sp = globals_type.get("DEFAULT_DIFFICULTYMODE", "")
    default_mode_mp = globals_type.get("DEFAULT_DIFFICULTYMODE_MP", "")

    # ── Extra starting units per prosperity level (unit.xml) ────────────────
    extra_units: dict[str, list[str]] = {}
    for e in parse("unit.xml").findall("Entry"):
        for pair in e.findall("aiStartDifficulty/Pair"):
            diff = pair.findtext("zIndex") or ""
            n = int(pair.findtext("iValue") or "0")
            if not diff or n <= 0:
                continue
            unit = entry_name(indexes, e, "UNIT_")
            extra_units.setdefault(diff, []).extend([unit] * n)

    # ── Prosperity ladder (difficulty.xml) ───────────────────────────────────
    prosperity: list[dict] = []
    for e in parse("difficulty.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        stockpile = []
        for pair in e.findall("aiYieldStockpile/Pair"):
            y = pair.findtext("zIndex") or ""
            stockpile.append({
                "yield": y.replace("YIELD_", "").lower(),
                "label": yield_name(y),
                # Display value — source multiplies by YIELDS_MULTIPLIER itself.
                "value": int(pair.findtext("iValue") or "0"),
            })
        rebel_lines = []
        for pair in e.findall("aiEffectCityRebelProb/Pair"):
            ec_id = pair.findtext("zIndex") or ""
            v = int(pair.findtext("iValue") or "0")
            ec = indexes.get("effectCity.xml", {}).get(ec_id)
            label = entry_name(indexes, ec, "EFFECTCITY_") if ec is not None \
                else ec_id.replace("EFFECTCITY_OPINIONFAMILY_", "").title()
            rebel_lines.append(f"{label} cities: +{v}% Rebel chance")
        prosperity.append({
            "id": z,
            "slug": z.replace("DIFFICULTY_", "").lower(),
            "name": entry_name(indexes, e, "DIFFICULTY_"),
            "stockpile": stockpile,
            "extraUnits": extra_units.get(z, []),
            "effects": effect_player_lines(e.findtext("EffectPlayer") or "", indexes),
            "emptyNearbySitePercent": int_of(e, "iEmptyNearbySitePercent"),
            "raidProbCity": int_of(e, "iRaidProbCity"),
            "raidNumCity": int_of(e, "iRaidNumCity"),
            "rebelProbs": rebel_lines,
        })
    prosperity_by_id = {p["id"]: p for p in prosperity}

    # ── AI Handicap ladder (advantage.xml) ───────────────────────────────────
    advantages: list[dict] = []
    for e in parse("advantage.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        advantages.append({
            "id": z,
            "slug": z.replace("ADVANTAGE_", "").lower(),
            "name": entry_name(indexes, e, "ADVANTAGE_"),
            "effects": effect_player_lines(e.findtext("EffectPlayer") or "", indexes),
        })

    # ── AI Development (development.xml) ─────────────────────────────────────
    developments: dict[str, dict] = {}
    for e in parse("development.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        details: list[str] = []
        cities = int_of(e, "iAvgCities")
        techs = int_of(e, "iTechs")
        pop = int_of(e, "iCapitalPopulation")
        if cities:
            details.append(f"~{cities} Cities at start")
        if techs:
            details.append(f"{techs} Techs researched")
        if pop:
            details.append(f"Capital starts at {pop} Citizens")
        nw, nr = int_of(e, "iNoWonderTurns"), int_of(e, "iNoReligionTurns")
        if nw:
            details.append(f"No Wonders for {nw} turns")
        if nr:
            details.append(f"No Religions for {nr} turns")
        developments[z] = {"name": entry_name(indexes, e, "DEVELOPMENT_"),
                           "details": details}

    # ── AI Aggression (opponentLevel.xml) ────────────────────────────────────
    opponent_levels: dict[str, dict] = {}
    for e in parse("opponentLevel.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        details = []
        war = int_of(e, "iWarModifier")
        if war:
            details.append(f"{fmt_decimal(war)}% AI war desire")
        swt = int_of(e, "iStartWarMinTurn")
        if swt:
            details.append(f"No AI wars vs humans before turn {swt}")
        ewt = int_of(e, "iEndWarMinTurns")
        if ewt:
            details.append(f"AI fights at least {ewt} turns before peace")
        nw, nr = int_of(e, "iNoWonderTurns"), int_of(e, "iNoReligionTurns")
        if nw:
            details.append(f"AI skips Wonders for {nw} turns")
        if nr:
            details.append(f"AI skips Religions for {nr} turns")
        if (e.findtext("bNoForcedMarch") or "") == "1":
            details.append("AI never uses Forced March")
        if (e.findtext("bNoExpansion") or "") == "1":
            details.append("AI never expands to new sites")
        opponent_levels[z] = {"name": entry_name(indexes, e, "OPPONENTLEVEL_"),
                              "details": details}

    # ── Tribal Level (tribeLevel.xml) ────────────────────────────────────────
    tribe_levels: dict[str, dict] = {}
    for e in parse("tribeLevel.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        details = []
        if (e.findtext("bNoTribe") or "") == "1":
            details.append("No Tribes on the map")
        sites = int_of(e, "iBarbSitesNearby")
        if sites:
            details.append(f"{sites} Tribal sites near each player")
        war = int_of(e, "iWarModifier")
        if war:
            details.append(f"{fmt_decimal(war)}% Tribal war desire")
        dev = int_of(e, "iImprovementDevelopModifier")
        if dev:
            details.append(f"{fmt_decimal(dev)}% Tribal site development")
        spawn = int_of(e, "iTurnUnitModifier")
        if spawn:
            details.append(f"{fmt_decimal(spawn)}% time between Tribal units")
        defend = int_of(e, "iDefendUnits")
        if defend:
            details.append(f"+{defend} defender{'s' if defend != 1 else ''} at Tribal sites")
        raid_turn = int_of(e, "iRaidStartTurn")
        if raid_turn:
            details.append(f"Raids from turn {raid_turn}")
        raid_tile = int_of(e, "iRaidProbTile")
        if raid_tile:
            details.append(f"{raid_tile}% Raid chance/site/turn")
        conv_turn = int_of(e, "iTribeConvertTurn")
        if conv_turn:
            details.append(f"Sites can convert to Tribes after turn {conv_turn}"
                           f" ({int_of(e, 'iTribeConvertProb')}%/turn)")
        distant = int_of(e, "iDistantRaidStartTurn")
        if distant:
            details.append(f"Distant raids from turn {distant}")
        tribe_levels[z] = {"name": entry_name(indexes, e, "TRIBELEVEL_"),
                           "details": details}

    # ── Calamities (occurrenceLevel.xml) ─────────────────────────────────────
    calamity_levels: dict[str, dict] = {}
    for e in parse("occurrenceLevel.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        calamity_levels[z] = {
            "name": entry_name(indexes, e, "OCCURRENCELEVEL_CALAMITIES_"),
            "help": text_of(indexes, (e.findtext("Help") or "")),
        }

    # ── Difficulty modes (the named presets) ─────────────────────────────────
    modes: list[dict] = []
    for e in parse("difficultyMode.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        calam = ""
        for pair in e.findall("OccurrenceLevels/Pair"):
            if (pair.findtext("zIndex") or "") == "OCCURRENCECLASS_CALAMITIES":
                calam = pair.findtext("zValue") or ""
        prosp_id = e.findtext("Difficulty") or ""
        tribe_id = e.findtext("TribeLevel") or ""
        # Empty nearby sites = tribeLevel sites × prosperity percent, rounded
        # to nearest (InfoHelpers.getNumEmptySites).
        sites = 0
        prosp = prosperity_by_id.get(prosp_id)
        tl_entry = next((t for t in parse("tribeLevel.xml").findall("Entry")
                         if (t.findtext("zType") or "") == tribe_id), None)
        if prosp and tl_entry is not None:
            sites = (int_of(tl_entry, "iBarbSitesNearby")
                     * prosp["emptyNearbySitePercent"] + 50) // 100
        modes.append({
            "id": z,
            "slug": z.replace("DIFFICULTYMODE_", "").lower(),
            "name": entry_name(indexes, e, "DIFFICULTYMODE_"),
            "description": text_of(indexes, e.findtext("Description") or ""),
            "easy": (e.findtext("bEasy") or "") == "1",
            "prosperity": prosp_id,
            "development": e.findtext("Development") or "",
            "opponentLevel": e.findtext("OpponentLevel") or "",
            "tribeLevel": tribe_id,
            "advantage": e.findtext("Advantage") or "",
            "calamities": calam,
            "emptySites": sites,
            "isDefaultSP": z == default_mode_sp,
            "isDefaultMP": z == default_mode_mp,
        })

    payload = {
        "advantages": advantages,
        "aiProsperity": ai_prosperity_id,
        "aiProsperityName": prosperity_by_id.get(ai_prosperity_id, {}).get("name", ""),
        "calamityLevels": calamity_levels,
        "developments": developments,
        "modes": modes,
        "opponentLevels": opponent_levels,
        "prosperity": prosperity,
        "tribeLevels": tribe_levels,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(modes)} difficulty modes, "
          f"{len(prosperity)} prosperity levels, {len(advantages)} handicap steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
