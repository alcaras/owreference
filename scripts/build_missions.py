#!/usr/bin/env python3
"""
Build src/data/missions.json — Rally Troops, Hold Court, Steal Research.

Source XMLs:
  mission.xml          — mission metadata (prereqs, cost, dice weights, subject)
  missionResult.xml    — each outcome (success/event/etc.) and the bonus it grants
  bonus.xml            — the actual yield rewards (base + per-rating scaling)
  text-mission.xml     — human-friendly names + descriptions

These three missions all share the dice-weighted outcome structure. We
fold their XML into one JSON keyed by mission slug, ready for the page.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import _strip_link_templates  # noqa: E402


# Event/option prose carries runtime template vars the static site can't fill:
# {G0:him:her} grammar (take the first form) and {FAMILY-1,1}/{CHARACTER-…}
# entity placeholders (replace with a generic noun). Strip anything left over.
_GRAMMAR_RE = re.compile(r"\{G\d+:([^:}]*):[^}]*\}")
_ENTITY_SUBS = [
    (re.compile(r"\{FAMILY[-\d,]*\}"),    "the family"),
    (re.compile(r"\{CHARACTER[-\d,]*\}"), "the character"),
    (re.compile(r"\{PLAYER[-\d,]*\}"),    "the rival"),
    (re.compile(r"\{CITY[-\d,]*\}"),      "the city"),
    (re.compile(r"\{NATION[-\d,]*\}"),    "the nation"),
    (re.compile(r"\{UNIT[-\d,]*\}"),      "the unit"),
]


def clean_text(s: str) -> str:
    if not s:
        return s
    s = _GRAMMAR_RE.sub(r"\1", s)
    for rx, repl in _ENTITY_SUBS:
        s = rx.sub(repl, s)
    s = re.sub(r"\{[^}]*\}", "", s)  # strip any remaining template token
    s = re.sub(r"\bthe the\b", "the", s, flags=re.IGNORECASE)  # "the {FAMILY}" → "the the family"
    return re.sub(r"\s+", " ", s).strip()

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "missions.json"

MISSIONS = [
    ("rally",          "MISSION_RALLY_TROOPS"),
    ("hold-court",     "MISSION_HOLD_COURT"),
    ("steal-research", "MISSION_STEAL_RESEARCH"),
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
                out[k] = _strip_link_templates(en)
    return out


def index(name: str) -> dict[str, ET.Element]:
    return {e.findtext("zType"): e for e in parse(name).findall("Entry") if e.findtext("zType")}


def yield_pairs(e: ET.Element, *tags: str) -> list[dict]:
    out: list[dict] = []
    for tag in tags:
        for pair in e.findall(f"{tag}/Pair"):
            y = (pair.findtext("zIndex") or "").replace("YIELD_", "")
            v = int(pair.findtext("iValue") or "0")
            out.append({"yield": y.lower(), "label": y.title(), "value": v, "scope": tag})
    return out


# Reward = (Base + Per × #Cities), then the game scales it up over the turns
# (a price/game-state multiplier we can't express statically). City counts to
# tabulate the base-rate reward across. From PlayerBonus.cs:5821.
SCALING_CITY_COUNTS = [1, 3, 6, 10, 15]


def _trim(v: float):
    return int(v) if v == int(v) else round(v, 1)


def scaling_from_outcome(outcome: dict) -> dict | None:
    """Pull the Base + Per(-city) yield off a mission's primary success
    outcome and tabulate the reward across a few empire sizes."""
    base = per = None
    yld = lbl = None
    for r in outcome["rewards"]:
        if r["value"] is None:
            continue
        if r["scope"].endswith("Base"):
            base, yld, lbl = r["value"], r["yield"], r["label"]
        elif r["scope"].endswith("Per"):
            per = r["value"]
    if base is None:
        return None
    base_d, per_d = base / 10, (per or 0) / 10
    return {
        "yield": yld,
        "label": lbl,
        "base": _trim(base_d),
        "per": _trim(per_d),
        # Raw (×10 internal) base/per the game's getAdjustedValue runs on — fed
        # verbatim to the client calculator so it reproduces the exact reward.
        "rawBase": base,
        "rawPer": per or 0,
        "perUnit": "city",
        "byCities": [{"cities": c, "value": _trim(base_d + per_d * c)} for c in SCALING_CITY_COUNTS],
    }


# Awkward SUBJECT_* condition tokens → readable gating labels. Anything not
# listed is title-cased from the token (SUBJECT_HIGH_CHARISMA → High Charisma).
SUBJECT_LABELS = {
    "SUBJECT_PLAYER_NO_WARS":     "No active wars",
    "SUBJECT_TRIBE_MAX_NEAR":     "Tribe nearby",
    "SUBJECT_PLAYER_FREEDOM":     "Freedom-leaning empire",
    "SUBJECT_CHARACTER_URBAN":    "Urban character",
    "SUBJECT_CHARACTER_STRONG":   "Strong character",
    "SUBJECT_CHARACTER_VAIN":     "Vain character",
    "SUBJECT_CHARACTER_CHARMING": "Charming character",
    "SUBJECT_COMPASSIONATE":      "Compassionate character",
}


def subject_label(s: str) -> str:
    if s in SUBJECT_LABELS:
        return SUBJECT_LABELS[s]
    t = s.replace("SUBJECT_", "").replace("COGNOMEN_", "").replace("CHARACTER_", "")
    return t.replace("_", " ").title()


def pairs(e: ET.Element, tag: str) -> list[tuple[str, int]]:
    return [((p.findtext("zIndex") or ""), int(p.findtext("iValue") or "0")) for p in e.findall(f"{tag}/Pair")]


def _tok(token: str, *prefixes: str) -> str:
    for p in prefixes:
        token = token.replace(p, "", 1)
    return token.replace("_", " ").title()


def _fallback_label(bonus_id: str) -> str:
    """Readable stand-in for a bonus with no concrete yield/unit/trait payload.
    EVENTOPTION_* contextual bonuses (opinion/relationship plumbing) collapse to
    a 'who it touches' phrase; named bonuses keep their title-cased token."""
    if "EVENTOPTION_" in bonus_id or "_OPTION_" in bonus_id:
        for key, label in (("_RESOURCE", "Grants a resource"), ("_FAMILY", "Affects a family"),
                           ("_CHARACTER", "Affects a character"), ("_PLAYER", "Affects a rival"),
                           ("_CITY", "Affects a city"), ("_UNIT", "Affects a unit")):
            if key in bonus_id:
                return label
        return "Special effect"
    return _tok(bonus_id, "BONUS_")


def humanize_bonus(bonus_id: str, bonus_idx: dict, text: dict) -> list[str]:
    """Readable one-liners for an event-reward bonus. Covers the structured
    fields seen on mission events; falls back to a cleaned token name."""
    if not bonus_id:
        return []
    b = bonus_idx.get(bonus_id)
    if b is None:
        return [_fallback_label(bonus_id)]
    out: list[str] = []

    base = {y: v for y, v in pairs(b, "aiGlobalYieldsBase")}
    per = {y: v for y, v in pairs(b, "aiGlobalYieldsPer")}
    for y in list(base) + [k for k in per if k not in base]:
        yl = y.replace("YIELD_", "").title()
        bv, pv = base.get(y, 0) / 10, per.get(y, 0) / 10
        s = f"{'+' if bv >= 0 else ''}{_trim(bv)} {yl}"
        if pv:
            s += f" (+{_trim(pv)}/city)"
        out.append(s)
    for y, v in pairs(b, "aiCityYields"):
        out.append(f"{'+' if v >= 0 else ''}{_trim(v/10)} {y.replace('YIELD_', '').title()} in a City")

    xp = int(b.findtext("iXPCharacter") or "0")
    if xp:
        out.append(f"+{_trim(xp/10)} XP to the character")
    for t in b.findall("aeAddTraits/zValue"):
        tr = t.text or ""
        out.append(f"Gain trait: {text.get('TEXT_' + tr, _tok(tr, 'TRAIT_'))}")
    for u, v in pairs(b, "aiUnits"):
        out.append(f"+{v} {text.get('TEXT_' + u, _tok(u, 'UNIT_'))}")
    for u, v in pairs(b, "aiBonusUnits"):
        out.append(f"+{v} {_tok(u, 'BONUSUNITCLASS_')} unit")
    reb = int(b.findtext("iRebelUnits") or "0")
    if reb:
        out.append(f"{reb} rebel unit{'s' if reb != 1 else ''} appear")
    rel = b.findtext("AddLeaderRelationship")
    if rel:
        out.append(f"Leader relationship: {_tok(rel, 'RELATIONSHIP_')}")
    amb = b.findtext("Ambition")
    if amb:
        out.append(f"Progress ambition: {_tok(amb, 'GOAL_')}")

    return out or [_fallback_label(bonus_id)]


def option_outcomes(opt: ET.Element, eopt_idx: dict, bonus_idx: dict, text: dict) -> list[dict]:
    """An option resolves to guaranteed bonuses, or a weighted roll between
    sub-options (aiEventOptionProb)."""
    prob_pairs = pairs(opt, "aiEventOptionProb")
    if prob_pairs:
        total = sum(v for _, v in prob_pairs) or 1
        outs = []
        for sub_id, w in prob_pairs:
            sub = eopt_idx.get(sub_id)
            rewards: list[str] = []
            if sub is not None:
                for bz in sub.findall("aeBonuses/zValue"):
                    rewards += humanize_bonus(bz.text or "", bonus_idx, text)
            outs.append({"probability": w / total, "weight": w, "rewards": rewards,
                         "label": _tok(sub_id, "EVENTOPTION_")})
        return outs
    rewards = []
    for bz in opt.findall("aeBonuses/zValue"):
        rewards += humanize_bonus(bz.text or "", bonus_idx, text)
    return [{"probability": 1.0, "weight": None, "rewards": rewards, "label": None}]


def option_requirements(opt: ET.Element) -> list[str]:
    reqs: list[str] = []
    for tag in ("LeaderSubjectAny", "LeaderSubject", "aeSubjectReqs", "SubjectReqs"):
        vals = [v.text for v in opt.findall(f"{tag}/zValue") if v.text]
        if vals:
            reqs.append(" / ".join(subject_label(v) for v in vals))
    return reqs


def build_events(event_result_id: str, story_idx: dict, eopt_idx: dict,
                 bonus_idx: dict, text: dict) -> list[dict]:
    """Every event story a mission's *_EVENT result can fire, with options and
    outcomes. Stories link via Trigger=EVENTTRIGGER_MISSION_FINISHED + TriggerData."""
    stories = [
        s for s in story_idx.values()
        if (s.findtext("Trigger") or "") == "EVENTTRIGGER_MISSION_FINISHED"
        and (s.findtext("TriggerData") or "") == event_result_id
    ]
    total_weight = sum(int(s.findtext("iWeight") or "0") for s in stories) or 1

    out: list[dict] = []
    for s in stories:
        zt = s.findtext("zType") or ""
        weight = int(s.findtext("iWeight") or "0")
        conditions = [subject_label(p.findtext("Second") or "")
                      for p in s.findall("SubjectExtras/Pair") if p.findtext("Second")]
        guaranteed: list[str] = []
        for bz in s.findall("aeBonuses/zValue"):
            guaranteed += humanize_bonus(bz.text or "", bonus_idx, text)

        options = []
        for oz in s.findall("aeOptions/zValue"):
            opt = eopt_idx.get(oz.text or "")
            if opt is None:
                continue
            options.append({
                "id": oz.text,
                "text": clean_text(text.get(opt.findtext("Text") or "", "")),
                "requirements": option_requirements(opt),
                "outcomes": option_outcomes(opt, eopt_idx, bonus_idx, text),
            })

        out.append({
            "id": zt,
            "name": clean_text(text.get(s.findtext("Name") or "", _tok(zt, "EVENTSTORY_"))),
            "text": clean_text(text.get(s.findtext("Text") or "", "")),
            "weight": weight,
            "share": weight / total_weight,
            "prob": int(s.findtext("iProb") or "0") or None,
            "conditions": conditions,
            "guaranteed": guaranteed,
            "options": options,
        })

    out.sort(key=lambda e: (-e["weight"], e["name"]))
    return out


def index_many(*names: str) -> dict[str, ET.Element]:
    """Merge several XML files into one zType→Entry index (base + DLC variants)."""
    out: dict[str, ET.Element] = {}
    for name in names:
        p = XML_DIR / name
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            z = e.findtext("zType")
            if z and z not in out:
                out[z] = e
    return out


def main() -> int:
    text = load_text(
        "text-mission.xml", "text-missionResult.xml", "text-infos.xml",
        "text-tech.xml", "text-subject.xml",
        # Event chain text: story titles/flavor, option prose, traits, units.
        "text-eventStory.xml", "text-eventStory-sap.xml", "text-eventStoryTitle.xml",
        "text-eventOption.xml", "text-eventOption-sap.xml",
        "text-trait.xml", "text-unit.xml",
    )
    missions_idx = index("mission.xml")
    results_idx = index("missionResult.xml")
    bonus_idx = index("bonus.xml")

    # Globals the reward calculator needs: per-yield stockpile cap (MAX_<YIELD>,
    # raw ×10 scale) and the turn the inflation ramp kicks in.
    gint = {e.findtext("zType"): int(e.findtext("iValue") or "0")
            for e in parse("globalsInt.xml").findall("Entry") if e.findtext("zType")}
    inflation_turns = gint.get("MONEY_INFLATION_TURNS", 60)
    story_idx = index_many("eventStory.xml", "eventStory-sap.xml", "eventStory-btt.xml")
    eopt_idx = index_many(
        "eventOption.xml", "eventOption-sap.xml", "eventOption-btt.xml",
        "eventOption-eoti.xml", "eventOption-wd.xml", "eventOption-wog.xml",
    )

    out: list[dict] = []
    for slug, mid in MISSIONS:
        m = missions_idx.get(mid)
        if m is None:
            print(f"⚠ missing mission {mid}", file=sys.stderr)
            continue

        name = text.get(m.findtext("Name") or "", mid.replace("MISSION_", "").title())
        desc = text.get(m.findtext("Description") or "", "")
        turns = int(m.findtext("iMissionTurns") or "0")
        tech_prereq = m.findtext("TechPrereq")
        tech_name = (
            text.get(f"TEXT_{tech_prereq}", tech_prereq.replace("TECH_", "").replace("_", " ").title())
            if tech_prereq else None
        )
        subject = (m.findtext("SubjectCharacter") or "").replace("SUBJECT_", "")
        subject_disp = subject.replace("_", " ").title() if subject else ""

        cost = []
        for pair in m.findall("aiYieldCost/Pair"):
            y = (pair.findtext("zIndex") or "").replace("YIELD_", "")
            v = int(pair.findtext("iValue") or "0")
            # Game stores yields ×10 for display, except Orders which are 1:1
            display = v / 10 if y not in ("ORDERS",) else v
            cost.append({"yield": y.lower(), "label": y.title(), "value": display})

        # Outcomes: aiResultDie holds {result_id: dice_weight}. Probability =
        # weight / total. Each result gets enriched with its bonus reward.
        outcomes_raw = m.findall("aiResultDie/Pair")
        total_weight = sum(int(p.findtext("iValue") or "0") for p in outcomes_raw)

        outcomes: list[dict] = []
        for p in outcomes_raw:
            rid = p.findtext("zIndex") or ""
            weight = int(p.findtext("iValue") or "0")
            result = results_idx.get(rid)
            outcome: dict = {
                "id": rid,
                "weight": weight,
                "probability": (weight / total_weight) if total_weight else 0,
                "name": text.get(
                    (result.findtext("Name") if result is not None else "") or "",
                    rid.replace("MISSIONRESULT_", "").replace("_", " ").title(),
                ),
                "description": text.get(
                    (result.findtext("Description") if result is not None else "") or "",
                    "",
                ),
                "rewards": [],
                "ratingModifier": [],
            }
            if result is not None:
                # Rating modifier on the result (e.g., Steal Research +24 Wisdom influence)
                for rp in result.findall("aiRatingModifier/Pair"):
                    r = (rp.findtext("zIndex") or "").replace("RATING_", "")
                    v = int(rp.findtext("iValue") or "0")
                    outcome["ratingModifier"].append({"rating": r.lower(), "label": r.title(), "value": v})

                # Resolve the bonus → yield rewards (base + per-rating scaling)
                bonus_id = result.findtext("TargetBonus")
                bonus = bonus_idx.get(bonus_id) if bonus_id else None
                if bonus is not None:
                    outcome["rewards"] = (
                        yield_pairs(bonus, "aiGlobalYieldsBase", "aiOtherYieldsBase", "aiYieldsBase")
                        + yield_pairs(bonus, "aiGlobalYieldsPer", "aiOtherYieldsPer", "aiYieldsPer")
                    )
                    if bonus.findtext("bRandomCourtier") == "1":
                        outcome["rewards"].append({"label": "Gain a random Courtier", "value": None, "scope": "Special"})

            outcomes.append(outcome)

        # Reward scaling: read off the primary (highest-weight, non-event)
        # success outcome — the first non-_EVENT outcome with a base reward.
        scaling = None
        for o in outcomes:
            if not o["id"].endswith("_EVENT"):
                scaling = scaling_from_outcome(o)
                if scaling:
                    break
        if scaling:
            scaling["cap"] = gint.get(f"MAX_{scaling['yield'].upper()}")  # raw cap, or None
            scaling["inflationTurns"] = inflation_turns

        # Event chain: the *_EVENT outcome's dice share is the trigger chance;
        # the stories it can fire (with options + outcomes) hang off it.
        event_outcome = next((o for o in outcomes if o["id"].endswith("_EVENT")), None)
        events = build_events(event_outcome["id"], story_idx, eopt_idx, bonus_idx, text) if event_outcome else []
        event_chance = ({
            "weight": event_outcome["weight"],
            "total": total_weight,
            "probability": event_outcome["probability"],
        } if event_outcome else None)

        out.append({
            "slug": slug,
            "id": mid,
            "name": name,
            "description": desc,
            "turns": turns,
            "subject": subject_disp,
            "techPrereq": (
                {"id": tech_prereq, "label": tech_name, "slug": tech_prereq.replace("TECH_", "").lower().replace("_", "-")}
                if tech_prereq else None
            ),
            "cost": cost,
            "outcomes": outcomes,
            "totalDiceWeight": total_weight,
            "scaling": scaling,
            "eventChance": event_chance,
            "events": events,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(out)} missions")
    for m in out:
        cost_str = ", ".join(f"{c['value']} {c['label']}" for c in m["cost"])
        print(f"  · {m['name']:20} {m['turns']} turn · {len(m['outcomes'])} outcomes · cost {cost_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
