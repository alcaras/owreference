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
  council.xml / council-btt.xml → per-seat aaiRatingYieldGlobal (flat/turn) and
                 aaiRatingYieldCity (flat per city) tables. Council seats scale
                 via modifyRating with OFFSET 0 (InfoHelpers.getRatingYieldRateCouncil),
                 i.e. base × triangle(rating) — R(R+1)/2. Grand Vizier (BTT) has
                 no rating-yield table, so only Ambassador/Chancellor/Spymaster
                 appear. (council-btt.xml is still parsed in case a patch adds one.)
  trait.xml / opinionCharacter.xml → agent-calculator constants: the Schemer
                 archetype's iAgentModifier (+10 percentage points, added flat
                 AFTER the rating multiply — InfoHelpers.getRatingYieldAgentPercent)
                 and each opinion level's iRateModifier (the agent's opinion of
                 you modifies the percent; sign flips when the rating is negative
                 via yieldWarning).

Formula (Utils.cs / InfoHelpers.cs, verified against the source):
  triangle(n)            = sign(n)·|n|·(|n|+1)/2
  triangleBoost(n)       = sign(n)·triangle(|n|+1)            (0 at n=0)
  triangleOffset(n,off)  = n                       if |n|+off <= 0
                           sign(n)·(triangle(|n|+off) - off)  otherwise

  Leader   (flat yield) = courtRate · triangleOffset(rating, yieldOffset)   [/10 display]
  Governor (yield %)    = govModifier · triangleBoost(rating)
  Agent    (yield %)    = agentPercent · rating                  (linear)
  General  (combat)     = combatBase  · triangleBoost(rating)
  Council  (flat yield) = seatRate   · triangleOffset(rating, 0)            [/10 display]
                          (= seatRate · R(R+1)/2; global or per-city per the seat)

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

# Rating value range shown on the page. Character.setRating applies no clamp,
# so ratings are unbounded in the engine and the formulas below stay valid past
# the band you normally see — the table runs to 25 to cover stacked-trait and
# late-game leaders.
RATING_MIN, RATING_MAX = -5, 25

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


def council_roles_by_rating() -> dict[str, list[dict]]:
    """rating zType → council seat roles giving flat yields from that rating.

    InfoHelpers.getRatingYieldRateCouncil{Global,City}: seat base value ×
    modifyRating(rating, offset=0). Global = empire-wide per turn; City = per city.
    """
    out: dict[str, list[dict]] = {}
    for fn in ("council.xml", "council-btt.xml"):
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            cid = e.findtext("zType") or ""
            if not cid:
                continue
            label = cid.replace("COUNCIL_", "").replace("_", " ").title()
            for tag, per_city in (("aaiRatingYieldGlobal", False), ("aaiRatingYieldCity", True)):
                for pair in e.findall(f"{tag}/Pair"):
                    rid = pair.findtext("zIndex") or ""
                    for sub in pair.findall("SubPair"):
                        ykey = (sub.findtext("zSubIndex") or "").replace("YIELD_", "")
                        val = int(sub.findtext("iValue") or "0")
                        if rid and ykey and val:
                            out.setdefault(rid, []).append({
                                "council": cid,
                                "label": label,
                                "yield": ykey,
                                "value": val,
                                "perCity": per_city,
                            })
    for roles in out.values():
        roles.sort(key=lambda r: (r["label"], r["perCity"]))
    return out


def agent_calc_constants() -> dict:
    """Constants the page's agent-yield calculator needs beyond the per-stat
    aiYieldAgentPercent: the Schemer trait's flat percent bonus and the
    opinion-level rate modifiers (InfoHelpers.getRatingYieldAgentPercent)."""
    schemer = 0
    for e in parse("trait.xml").findall("Entry"):
        if e.findtext("zType") == "TRAIT_SCHEMER_ARCHETYPE":
            schemer = int(e.findtext("iAgentModifier") or "0")
    opinions = []
    for e in parse("opinionCharacter.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        opinions.append({
            "id": zt,
            "name": zt.replace("OPINIONCHARACTER_", "").title(),
            "modifier": int(e.findtext("iRateModifier") or "0"),
        })
    return {"schemerModifier": schemer, "opinions": opinions}


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
    council_by_rating = council_roles_by_rating()

    def first_pair_value(entry: ET.Element, tag: str, yield_key: str) -> int:
        for pair in entry.findall(f"{tag}/Pair"):
            if (pair.findtext("zIndex") or "").replace("YIELD_", "") == yield_key:
                return int(pair.findtext("iValue") or "0")
        return 0

    def color_hex(entry: ET.Element) -> str:
        # color.xml stores the hex directly in zHexValue (there are no
        # iRed/iGreen/iBlue fields — reading those yielded #000000).
        c = color_idx.get(entry.findtext("zColor") or "")
        if c is None:
            return "#c9a04a"
        hexv = (c.findtext("zHexValue") or "").strip()
        return hexv.lower() if hexv.startswith("#") else "#c9a04a"

    # highest rating first — the interesting end of the table reads at the top
    ratings = list(range(RATING_MAX, RATING_MIN - 1, -1))
    stats_out: list[dict] = []

    for rid, slug, name, ykey, combat_field, combat_label, combat_fmt in STATS:
        entry = rating_idx[rid]
        court = first_pair_value(entry, "aiYieldCourtRate", ykey)
        gov = first_pair_value(entry, "aiYieldGovernorModifier", ykey)
        agent = first_pair_value(entry, "aiYieldAgentPercent", ykey)
        combat_base = int(entry.findtext(combat_field) or "0")
        off = yield_off.get(ykey, 0)
        yield_label = ykey.title()
        councils = council_by_rating.get(rid, [])

        # Each role declares: key, label, the effect kind, and the per-rating
        # cell builder for base + competitive. Flat-yield cells display /10.
        def row(rating: int, competitive: bool) -> dict:
            leader = modify_rating(court, rating, off, competitive) / 10
            governor = boost_rating(gov, rating, competitive)
            agt = agent * rating  # Agent percent is linear in both modes
            general = boost_rating(combat_base, rating, competitive)
            out = {
                "rating": rating,
                "leader": round(leader, 2),
                "governor": governor,
                "agent": agt,
                "general": general,
            }
            for c in councils:
                # Council seats: base × triangleOffset(rating, 0) = triangle(rating).
                out[c["label"].lower()] = round(modify_rating(c["value"], rating, 0, competitive) / 10, 2)
            return out

        roles = [
            {"key": "leader",   "label": "Leader",   "effect": yield_label,           "kind": "yield", "yield": ykey.lower()},
            {"key": "governor", "label": "Governor", "effect": f"{yield_label} %",     "kind": "pct",   "yield": ykey.lower()},
            {"key": "agent",    "label": "Agent",    "effect": f"{yield_label} %",     "kind": "pct",   "yield": ykey.lower()},
            {"key": "general",  "label": "General",  "effect": combat_label,           "kind": combat_fmt, "yield": ykey.lower()},
        ]
        for c in councils:
            cy = c["yield"].title()
            roles.append({
                "key": c["label"].lower(),
                "label": c["label"],
                "effect": f"{cy} /city" if c["perCity"] else cy,
                "kind": "yield",
                "yield": c["yield"].lower(),
                "council": True,
            })

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
        "agentCalc": agent_calc_constants(),
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
