#!/usr/bin/env python3
"""
Build src/data/cognomens.json from cognomen.xml + text-infos.xml +
genderedText.xml.

Each cognomen is a regnal title (e.g. "the Conqueror") earned by reaching
a Legitimacy threshold and a stat threshold (e.g. STAT_CITY_CAPTURED ≥ 2,
weighted at 2000 points per city). We render each as:

  • Title in English
  • Legitimacy threshold (iLegitimacy)
  • Minimum total weighted score (iMinValue)
  • The stat track and per-event point weight (aiStatValue)
  • An optional EffectPlayer for cognomens that grant ongoing effects

The "Main Line" (legitimacy-only) cognomens are distinguished from the
specialist side tracks (Warrior, Conqueror, Restorer, …) by having an
empty aiStatValue. We surface that as a `track` label.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "cognomens.json"


# Human-friendly labels for the stat tokens. Anything not listed falls back to
# a title-cased rendering of the suffix.
STAT_LABELS: dict[str, str] = {
    "STAT_UNIT_MILITARY_KILLED":         "Military Units Killed",
    "STAT_UNIT_MILITARY_KILLED_GENERAL": "Killed as General",
    "STAT_UNIT_LOST":                    "Units Lost",
    "STAT_UNIT_TRAINED":                 "Units Trained",
    "STAT_UNIT_PROMOTED":                "Units Promoted",
    "STAT_TRIBE_CLEARED":                "Tribal Sites Cleared",
    "STAT_TRIBE_PEACE":                  "Tribal Peaces",
    "STAT_TRIBE_ALLIANCE":               "Tribal Alliances",
    "STAT_TEAM_PEACE":                   "National Peaces",
    "STAT_TEAM_ALLIANCE":                "National Alliances",
    "STAT_CAPITAL_CAPTURED":             "Capitals Captured",
    "STAT_CITY_CAPTURED":                "Cities Captured",
    "STAT_CITY_RECAPTURED":              "Cities Recaptured",
    "STAT_CITY_FOUNDED":                 "Cities Founded",
    "STAT_COURTIER_ADDED":               "Courtiers Added",
    "STAT_SPECIALIST_PRODUCED":          "Specialists Produced",
    "STAT_TECH_DISCOVERED":              "Techs Discovered",
    "STAT_WONDER_FINISHED":              "Wonders Finished",
    "STAT_IMPROVEMENT_FINISHED":         "Improvements Finished",
    "STAT_LANDMARK_DISCOVERED":          "Landmarks Discovered",
    "STAT_LANDMARK_NAMED":               "Landmarks Named",
    "STAT_RELIGION_SPREAD":              "Religion Spread",
    "STAT_RUINS_EXPLORED":               "Ruins Explored",
    "STAT_THEOLOGY_ESTABLISHED":         "Theologies Established",
    "STAT_TILES_REVEALED":               "Tiles Revealed",
    "STAT_YEARS_REIGNED":                "Years Reigned",
    "STAT_AMBITION_ACHIEVED":            "Ambitions Achieved",
    "STAT_LEGACY_ACHIEVED":              "Legacies Achieved",
    "STAT_TRIBE_CONTACTED":              "Tribes Contacted",
    "STAT_TEAM_CONTACTED":               "Nations Contacted",
    "STAT_CARAVAN_ARRIVED":              "Caravans Arrived",
    "STAT_WORLD_RELIGION_FOUNDED":       "World Religions Founded",
    "STAT_IMPROVEMENT_REPAIRED":         "Improvements Repaired",
    # Empires of the Indus DLC stats.
    "STAT_CULTURE_LEVEL_INCREASED":      "Culture Levels Gained",
    "STAT_HAPPINESS_LEVEL_INCREASED":    "Happiness Levels Gained",
    "STAT_UNIT_HEALED":                  "Units Healed",
    "STAT_PAGAN_RELIGION_SPREAD":        "Pagan Religion Spread",
    "STAT_CULTS":                        "Cults Founded",
    "STAT_CLERGY_ADDED":                 "Clergy Added",
    "STAT_RESOURCE_HARVESTED":           "Resources Harvested",
    "STAT_VEGETATION_REMOVED":           "Vegetation Cleared",
    "STAT_IMPROVEMENT_PILLAGED":         "Improvements Pillaged",
    "STAT_UNIT_MILITARY_KILLED_ANY_GENERAL": "Enemy Generals Killed",
    "STAT_LAW_ADOPTED":                  "Laws Adopted",
    "STAT_LAW_CHANGED":                  "Laws Changed",
    "STAT_RELIGION_PURGED":              "Religions Purged",
}


# Group cognomens into named tracks by the primary stat they reward.
# "Main Line" is the legitimacy-only progression earned by simply ruling well.
TRACK_FROM_STAT: dict[str, str] = {
    "STAT_UNIT_MILITARY_KILLED":   "Killing",
    "STAT_UNIT_TRAINED":           "Training / Promoting",
    "STAT_UNIT_PROMOTED":          "Training / Promoting",
    "STAT_TRIBE_CLEARED":          "Tribal Sites",
    "STAT_TRIBE_PEACE":            "Alliances & Peace",
    "STAT_TRIBE_ALLIANCE":         "Alliances & Peace",
    "STAT_TEAM_PEACE":             "Alliances & Peace",
    "STAT_TEAM_ALLIANCE":          "Alliances & Peace",
    "STAT_CAPITAL_CAPTURED":       "Conquest",
    "STAT_CITY_CAPTURED":          "Conquest",
    "STAT_CITY_RECAPTURED":        "Reconquest",
    "STAT_CITY_FOUNDED":           "Founding Cities",
    "STAT_COURTIER_ADDED":         "Court & Specialists",
    "STAT_SPECIALIST_PRODUCED":    "Court & Specialists",
    "STAT_TECH_DISCOVERED":        "Tech & Wonders",
    "STAT_WONDER_FINISHED":        "Tech & Wonders",
    "STAT_IMPROVEMENT_FINISHED":   "Building",
    "STAT_LANDMARK_DISCOVERED":    "Exploration",
    "STAT_LANDMARK_NAMED":         "Exploration",
    "STAT_RUINS_EXPLORED":         "Exploration",
    "STAT_TILES_REVEALED":         "Exploration",
    "STAT_RELIGION_SPREAD":        "Religion",
    "STAT_THEOLOGY_ESTABLISHED":   "Religion",
    "STAT_WORLD_RELIGION_FOUNDED": "Religion",
    "STAT_IMPROVEMENT_REPAIRED":   "Building",
    "STAT_YEARS_REIGNED":          "Reign",
    # Empires of the Indus DLC side tracks. Each map key is the first positive
    # stat in that cognomen's vector, so the track heuristic routes it here.
    "STAT_CULTURE_LEVEL_INCREASED": "Benevolence",
    "STAT_PAGAN_RELIGION_SPREAD":   "Cults & Clergy",
    "STAT_RESOURCE_HARVESTED":      "Gathering",
    "STAT_IMPROVEMENT_PILLAGED":    "Raiding",
    "STAT_LAW_ADOPTED":             "Lawgiving",
    "STAT_RELIGION_PURGED":         "Zealotry",
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


def load_gendered_text() -> dict[str, str]:
    """Map GENDERED_TEXT_COGNOMEN_X → TEXT_COGNOMEN_X (masculine first form)."""
    out: dict[str, str] = {}
    p = XML_DIR / "genderedText.xml"
    if not p.exists():
        return out
    for entry in ET.parse(p).getroot().findall("Entry"):
        zid = entry.findtext("zType") or ""
        for pair in entry.findall("Texts/Pair"):
            if (pair.findtext("zIndex") or "").endswith("MASCULINE"):
                out[zid] = pair.findtext("zValue") or ""
                break
    return out


def load_turn_scales(text: dict[str, str]) -> list[dict]:
    """Game-speed cognomen scaling, from turnScale.xml.

    The award threshold is scaled by game speed via
    `utils().modify(value, turnScale().miCognomenModifier)` in Character.cs
    (`modify(v, m) = v * (100 + m) / 100`). Faster speeds accrue stats faster,
    so the bar is raised to compensate: Year ×1.0, Semester ×1.5, Season ×2.0,
    Month ×3.0. Modifier comes straight from XML; only the display label is
    looked up from text-infos.
    """
    out: list[dict] = []
    p = XML_DIR / "turnScale.xml"
    if not p.exists():
        return out
    for entry in ET.parse(p).getroot().findall("Entry"):
        zid = entry.findtext("zType") or ""
        if not zid:
            continue
        key = zid.replace("TURNSCALE_", "")
        label = text.get(f"TEXT_TURNSCALE_{key}_SINGULAR", key.title())
        modifier = int(entry.findtext("iCognomenModifier") or "0")
        out.append({"id": zid, "label": label, "modifier": modifier})
    return out


import re

# Manual aliases for stats whose in-game F5-panel label isn't in text-stat.xml
# (Cults/Clergy) or differs from it enough to be worth pinning explicitly.
MANUAL_STAT_ALIASES: dict[str, list[str]] = {
    "STAT_CULTS":                          ["Cults", "Cults Founded", "Cults Established"],
    "STAT_CLERGY_ADDED":                   ["Clergy Added", "Clergy"],
    "STAT_UNIT_MILITARY_KILLED_GENERAL":   ["Military Units Killed as General",
                                            "Killed as General"],
    "STAT_TRIBE_CLEARED":                  ["Tribal Sites Cleared", "Camps Cleared"],
}


def _norm_label(s: str) -> str:
    """Lowercase, non-alphanumerics → single space, trimmed. MUST stay in
    lockstep with the identical normaliser in cognomens-tracker.astro."""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _expand_templates(s: str) -> list[str]:
    """`{singular_N:Sing:Plur}` → both forms (cartesian over all templates);
    any other `{...}` link template is stripped."""
    m = re.search(r"\{singular_\d+:([^:}]*):([^}]*)\}", s)
    if m:
        out: list[str] = []
        for choice in (m.group(1), m.group(2)):
            out += _expand_templates(s[: m.start()] + choice + s[m.end():])
        return out
    return [re.sub(r"\{[^}]*\}", "", s).strip()]


def build_stat_aliases(input_stats: list[dict]) -> dict[str, str]:
    """normalised label → STAT token, for the tracker's game-paste parser.

    Sourced from the game's own stat strings (`text-stat.xml`, with
    `text-ui.xml` fallbacks) so it tracks the F5 leader panel verbatim and
    survives patches; augmented with our own display labels and a small manual
    map. Collisions would be a data bug — assert there are none.
    """
    tstat: dict[str, str] = {}
    for fn in ("text-stat.xml", "text-ui.xml"):
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            z = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").strip()
            if z and en:
                tstat[z] = en

    aliases: dict[str, str] = {}

    def add(label: str, token: str) -> None:
        key = _norm_label(label)
        if not key:
            return
        if key in aliases and aliases[key] != token:
            raise SystemExit(
                f"stat-alias collision: {key!r} → {aliases[key]} vs {token}"
            )
        aliases[key] = token

    for s in input_stats:
        token = s["stat"]
        suffix = token.replace("STAT_", "")
        raws = [
            tstat.get(f"TEXT_STAT_{suffix}"),
            tstat.get(f"TEXT_UI_STATS_{suffix}"),
            s["label"],  # our own STAT_LABELS rendering
            *MANUAL_STAT_ALIASES.get(token, []),
        ]
        for raw in raws:
            if not raw:
                continue
            for variant in _expand_templates(raw):
                add(variant, token)

    return aliases


def build_calculator(cogs: list[dict], text: dict[str, str]) -> dict:
    """The data the client-side tracker needs to replicate Character.cs.

    `updateCognomen()` awards the cognomen with the highest |legitimacy| whose
    score (Σ leaderStat × cognomen.statValue) clears the scaled minValue:

        scaledMin = cognomen.minValue * (20 + leaderIndex) / 20   (int math)
        scaledMin = modify(scaledMin, turnScale.cognomenModifier)

    leaderIndex is 0-based (1st leader ×20/20 = ×1.0, 2nd ×21/20 = ×1.05, …) —
    linear on the base, NOT compounding. Bad (negative-legitimacy) cognomens
    are only considered when the ALLOW_BAD_COGNOMENS game option is on. The page
    iterates `cogs` directly for the math; this block just drives the input
    form (which stats to ask for, their labels and point weights) and the
    game-speed selector.
    """
    # Order the input fields by the fullest Main Line cognomen (Great = 34
    # stats); every positive Main Line tier shares the same stat vector.
    main_line = [
        c for c in cogs if c["track"] == "Main Line" and c["legitimacy"] > 0
    ]
    canonical = max(main_line, key=lambda c: len(c["stats"]), default=None)
    main_vals = {s["stat"]: s["value"] for s in canonical["stats"]} if canonical else {}

    # Side-track weight per stat (single column in the legacy sheet — the value
    # is consistent across the side tracks that use it).
    side_vals: dict[str, int] = {}
    for c in cogs:
        if c["track"] == "Main Line" or c["legitimacy"] <= 0:
            continue
        for s in c["stats"]:
            side_vals.setdefault(s["stat"], s["value"])

    order = [s["stat"] for s in canonical["stats"]] if canonical else []
    seen = set(order)
    for c in cogs:
        for s in c["stats"]:
            if s["stat"] not in seen:
                seen.add(s["stat"])
                order.append(s["stat"])

    # Every stat that feeds a score-gated cognomen — the base Main Line/side
    # tracks plus the Empires of the Indus DLC tracks (Benevolence, Gathering,
    # Raiding, …). Indus stats have no Main Line weight, so `mainValue` is null
    # and the form shows only the side weight.
    input_stats = [
        {
            "stat": st,
            "label": STAT_LABELS.get(
                st, st.replace("STAT_", "").replace("_", " ").title()
            ),
            "mainValue": main_vals.get(st),
            "sideValue": side_vals.get(st),
        }
        for st in order
    ]
    tracked_stats = {s["stat"] for s in input_stats}

    # A cognomen is in scope for the tracker iff it has a real score gate.
    # (Excludes the auto New/Founder, which carry no aiStatValue.)
    for c in cogs:
        c["tracker"] = bool(
            c["minValue"] > 0
            and c["stats"]
            and all(s["stat"] in tracked_stats for s in c["stats"])
        )

    return {
        "inputStats": input_stats,
        "statAliases": build_stat_aliases(input_stats),
        "gameSpeeds": load_turn_scales(text),
        "leaderScaling": {
            "baseDivisor": 20,
            "note": (
                "Each successive leader raises every threshold by 5% of its "
                "base: scaledMin = base × (20 + leaderIndex) ÷ 20, with "
                "leaderIndex 0-based (1st ruler ×1.00, 2nd ×1.05, 3rd ×1.10…). "
                "Linear on the base, not compounding."
            ),
            "source": "Character.cs · getCognomenMinValue()",
        },
    }


def main() -> int:
    text = load_text("text-infos.xml", "text-concept.xml")
    gendered = load_gendered_text()

    cogs: list[dict] = []

    for entry in parse("cognomen.xml").findall("Entry"):
        zid = entry.findtext("zType") or ""
        if not zid:
            continue

        gn = entry.findtext("GenderedName") or ""
        text_key = gendered.get(gn, "")
        title = text.get(text_key, zid.replace("COGNOMEN_", "the ").replace("_", " ").title())

        legitimacy = int(entry.findtext("iLegitimacy") or "0")
        min_value = int(entry.findtext("iMinValue") or "0")
        gcr = entry.findtext("GameContentRequired") or ""

        stats: list[dict] = []
        for pair in entry.findall("aiStatValue/Pair"):
            stat = pair.findtext("zIndex") or ""
            iv = int(pair.findtext("iValue") or "0")
            label = STAT_LABELS.get(stat, stat.replace("STAT_", "").replace("_", " ").title())
            stats.append({"stat": stat, "label": label, "value": iv})

        # Track is determined by the first positive stat (or "Main Line" if empty).
        # Heuristic: the true Main Line tiers aggregate ~34 stats; specialist
        # side tracks top out at the 7-stat Exploration track (Explorer/
        # Intrepid). A <=8 cutoff routes the side tracks correctly while still
        # leaving the 34-stat Main Line ladder as "Main Line".
        track = "Main Line"
        positive_stats = [s for s in stats if s["value"] > 0]
        if 0 < len(positive_stats) <= 8:
            for s in positive_stats:
                if s["stat"] in TRACK_FROM_STAT:
                    track = TRACK_FROM_STAT[s["stat"]]
                    break

        cogs.append({
            "id": zid,
            "slug": zid.replace("COGNOMEN_", "").lower(),
            "title": title,
            "legitimacy": legitimacy,
            "minValue": min_value,
            "track": track,
            "stats": stats,
            "achievement": entry.findtext("Achievement") or "",
            "dlc": gcr,
        })

    # Sort: main line first by legitimacy, then by track and legitimacy
    TRACK_ORDER = [
        "Main Line", "Killing", "Training / Promoting", "Tribal Sites",
        "Alliances & Peace", "Conquest", "Reconquest", "Founding Cities",
        "Court & Specialists", "Tech & Wonders", "Building",
        "Exploration", "Religion", "Reign",
        # Empires of the Indus DLC tracks.
        "Benevolence", "Cults & Clergy", "Gathering", "Raiding",
        "Lawgiving", "Zealotry",
    ]
    def sort_key(c: dict) -> tuple:
        try:
            ti = TRACK_ORDER.index(c["track"])
        except ValueError:
            ti = len(TRACK_ORDER)
        return (ti, c["legitimacy"], c["title"])

    cogs.sort(key=sort_key)

    # Group by track for the page
    by_track: defaultdict[str, list[dict]] = defaultdict(list)
    for c in cogs:
        by_track[c["track"]].append(c)
    tracks = [{"name": t, "cognomens": by_track[t]} for t in TRACK_ORDER if t in by_track]

    calculator = build_calculator(cogs, text)

    payload = {"cognomens": cogs, "tracks": tracks, "calculator": calculator}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(cogs)} cognomens in {len(tracks)} tracks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
