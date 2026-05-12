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
    "STAT_RUIN_EXPLORED":                "Ruins Explored",
    "STAT_THEOLOGY_ESTABLISHED":         "Theologies Established",
    "STAT_TILES_REVEALED":               "Tiles Revealed",
    "STAT_TURNS_REIGNED":                "Years Reigned",
    "STAT_AMBITION_ACHIEVED":            "Ambitions Achieved",
    "STAT_LEGACY_ACHIEVED":              "Legacies Achieved",
    "STAT_TRIBE_CONTACTED":              "Tribes Contacted",
    "STAT_TEAM_CONTACTED":               "Nations Contacted",
    "STAT_CARAVAN_ARRIVED":              "Caravans Arrived",
    "STAT_RELIGION_FOUNDED":             "World Religions Founded",
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
    "STAT_RUIN_EXPLORED":          "Exploration",
    "STAT_TILES_REVEALED":         "Exploration",
    "STAT_RELIGION_SPREAD":        "Religion",
    "STAT_THEOLOGY_ESTABLISHED":   "Religion",
    "STAT_RELIGION_FOUNDED":       "Religion",
    "STAT_TURNS_REIGNED":          "Reign",
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
        # Heuristic: cognomens with many stat conditions (>5) are part of the
        # legitimacy-driven "Main Line" — they aggregate every kind of activity
        # rather than rewarding one specialist track.
        track = "Main Line"
        positive_stats = [s for s in stats if s["value"] > 0]
        if 0 < len(positive_stats) <= 5:
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

    payload = {"cognomens": cogs, "tracks": tracks}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(cogs)} cognomens in {len(tracks)} tracks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
