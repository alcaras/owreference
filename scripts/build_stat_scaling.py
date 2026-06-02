#!/usr/bin/env python3
"""
Build src/data/stat-scaling.json — the four character ratings (Wisdom,
Charisma, Courage, Discipline) and how each role's effect scales with the
rating value, computed PURELY from the game's own formula (no spreadsheet).

Source of truth (all XML + the decompiled C# the formula lives in):
  rating.xml   → per-rating base rates:
                   aiYieldCourtRate     (Leader flat yield, the signature yield)
                   aiYieldGovernorModifier (Governor yield %)
                   aiYieldAgentPercent  (Agent yield %)
                   iCriticalChance / iDefenseModifier / iAttackModifier /
                   iUnitXP             (General — combat, one per rating)
  yield.xml    → iTriangleOffset per yield (Science -2, Civics -1, Training 0,
                 Money +1) — the offset fed to triangleOffset for flat yields
  color.xml    → per-rating accent hex

Formula (Utils.cs / InfoHelpers.cs, verified against the source):
  triangle(n)            = sign(n)·|n|·(|n|+1)/2
  triangleBoost(n)       = sign(n)·triangle(|n|+1)            (0 at n=0)
  triangleOffset(n,off)  = n                       if |n|+off <= 0
                           sign(n)·(triangle(|n|+off) - off)  otherwise

  Leader   (flat yield) = courtRate · triangleOffset(rating, yieldOffset)   [/10 display]
  Governor (yield %)    = govModifier · triangleBoost(rating)
  Agent    (yield %)    = agentPercent · rating                  (linear)
  General  (combat)     = combatBase  · triangleBoost(rating)

Competitive Mode = the GAMEOPTION_LOWER_CHARACTER_YIELDS sub-option. It swaps
the triangular curve for a LINEAR one through an "equivalent rating" of
RATING_EQUIVALENT_LOWER_CHARACTER_YIELDS (=5):
  modifyRating_competitive(v, r, off) = v · r · triangleOffset(5, off) / 5
  boostRating_competitive(v, r)       = v · r · triangleBoost(5)      / 5

These are the literal game outputs; they can differ from the legacy
spreadsheet's normalized Leader display. We render the raw game formula.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "stat-scaling.json"

# Competitive-mode linear-equivalent rating (globalsInt.xml
# RATING_EQUIVALENT_LOWER_CHARACTER_YIELDS).
RATING_EQUIVALENT = 5

# Rating value range shown on the page (the in-game character rating band).
RATING_MIN, RATING_MAX = -3, 15

# Stat → (slug, display name, signature yield, the General/combat field + how
# to label & format it). The General effect is the only role that changes
# *kind* per stat; everything else keys off the signature yield.
STATS = [
    ("RATING_WISDOM",     "wisdom",     "Wisdom",     "SCIENCE",  "iCriticalChance",  "Crit Chance", "pct"),
    ("RATING_CHARISMA",   "charisma",   "Charisma",   "CIVICS",   "iDefenseModifier", "Defense",     "pct"),
    ("RATING_COURAGE",    "courage",    "Courage",    "TRAINING", "iAttackModifier",  "Attack",      "pct"),
    ("RATING_DISCIPLINE", "discipline", "Discipline", "MONEY",    "iUnitXP",          "Unit XP",     "flat"),
]


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


# ── the game's integer math ────────────────────────────────────────────────
def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


def triangle(n: int) -> int:
    a = abs(n)
    return _sign(n) * a * (a + 1) // 2


def triangle_boost(n: int) -> int:
    return 0 if n == 0 else _sign(n) * triangle(abs(n) + 1)


def triangle_offset(n: int, off: int) -> int:
    v = abs(n) + off
    if v <= 0:
        return n
    return _sign(n) * (triangle(v) - off)


def modify_rating(value: int, rating: int, off: int, competitive: bool) -> int:
    """Flat-yield scaling (InfoHelpers.modifyRating)."""
    if not competitive:
        return value * triangle_offset(rating, off)
    eq = max(1, RATING_EQUIVALENT)
    return value * rating * triangle_offset(eq, off) // eq


def boost_rating(value: int, rating: int, competitive: bool) -> int:
    """Percent / combat scaling (InfoHelpers.boostRating)."""
    if not competitive:
        return value * triangle_boost(rating)
    eq = max(1, RATING_EQUIVALENT)
    return value * rating * triangle_boost(eq) // eq


def text_index(*files: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in files:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").split("~")[0].strip()
            if k and en and k not in out:
                out[k] = en
    return out


def main() -> int:
    rating_idx = {e.findtext("zType"): e for e in parse("rating.xml").findall("Entry") if e.findtext("zType")}
    color_idx = {e.findtext("zType"): e for e in parse("color.xml").findall("Entry") if e.findtext("zType")}
    yield_off = {
        (e.findtext("zType") or "").replace("YIELD_", ""): int(e.findtext("iTriangleOffset") or "0")
        for e in parse("yield.xml").findall("Entry") if e.findtext("zType")
    }
    text = text_index("text-infos.xml", "text-rating.xml")

    def first_pair_value(entry: ET.Element, tag: str, yield_key: str) -> int:
        for pair in entry.findall(f"{tag}/Pair"):
            if (pair.findtext("zIndex") or "").replace("YIELD_", "") == yield_key:
                return int(pair.findtext("iValue") or "0")
        return 0

    def color_hex(entry: ET.Element) -> str:
        c = color_idx.get(entry.findtext("zColor") or "")
        if c is None:
            return "#c9a04a"
        r = int(c.findtext("iRed") or "0"); g = int(c.findtext("iGreen") or "0"); b = int(c.findtext("iBlue") or "0")
        return f"#{r:02x}{g:02x}{b:02x}"

    ratings = list(range(RATING_MIN, RATING_MAX + 1))
    stats_out: list[dict] = []

    for rid, slug, name, ykey, combat_field, combat_label, combat_fmt in STATS:
        entry = rating_idx[rid]
        court = first_pair_value(entry, "aiYieldCourtRate", ykey)
        gov = first_pair_value(entry, "aiYieldGovernorModifier", ykey)
        agent = first_pair_value(entry, "aiYieldAgentPercent", ykey)
        combat_base = int(entry.findtext(combat_field) or "0")
        off = yield_off.get(ykey, 0)
        yield_label = ykey.title()

        # Each role declares: key, label, the effect kind, and the per-rating
        # cell builder for base + competitive. Flat-yield cells display /10.
        def row(rating: int, competitive: bool) -> dict:
            leader = modify_rating(court, rating, off, competitive) / 10
            governor = boost_rating(gov, rating, competitive)
            agt = agent * rating  # Agent percent is linear in both modes
            general = boost_rating(combat_base, rating, competitive)
            return {
                "rating": rating,
                "leader": round(leader, 2),
                "governor": governor,
                "agent": agt,
                "general": general,
            }

        roles = [
            {"key": "leader",   "label": "Leader",   "effect": yield_label,           "kind": "yield", "yield": ykey.lower()},
            {"key": "governor", "label": "Governor", "effect": f"{yield_label} %",     "kind": "pct",   "yield": ykey.lower()},
            {"key": "agent",    "label": "Agent",    "effect": f"{yield_label} %",     "kind": "pct",   "yield": ykey.lower()},
            {"key": "general",  "label": "General",  "effect": combat_label,           "kind": combat_fmt, "yield": ykey.lower()},
        ]

        stats_out.append({
            "id": rid,
            "slug": slug,
            "name": name,
            "yield": ykey.lower(),
            "yieldLabel": yield_label,
            "color": color_hex(entry),
            "triangleOffset": off,
            "baseRates": {"court": court, "governor": gov, "agent": agent, "combat": combat_base, "combatField": combat_field},
            "roles": roles,
            "base": [row(r, False) for r in ratings],
            "cm": [row(r, True) for r in ratings],
            "help": text.get(entry.findtext("Help") or "", ""),
        })

    out = {
        "ratings": ratings,
        "ratingEquivalent": RATING_EQUIVALENT,
        "stats": stats_out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(stats_out)} stats × {len(ratings)} rating rows × 2 modes")
    # Dev sanity print: Wisdom Leader curve (should be triangleOffset(n,-2))
    w = stats_out[0]
    print("  Wisdom Leader (base):", [r["leader"] for r in w["base"] if r["rating"] in range(1, 9)])
    print("  Wisdom Governor (base):", [r["governor"] for r in w["base"] if r["rating"] in range(1, 9)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
