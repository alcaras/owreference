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


# Event/option prose is full of runtime template vars the static site can't
# fill: grammar ({G0:him:her}), entity references ({CHARACTER-1,1},
# {RELIGION-1,1}, …) and bare link(TOKEN) markup. Rather than blank them (which
# left dangling "'s thing"), we replace every entity ref with a bracketed
# placeholder so the reader can see exactly what gets filled in.
ENTITY_NOUNS = {
    "CHARACTER": "character", "PLAYER": "rival", "UNITPLAYER": "rival", "CITY": "city",
    "RELIGION": "religion", "FAMILY": "family", "TRIBE": "tribe", "TITLE": "title",
    "UNIT": "unit", "GOAL": "ambition", "RELATIVE": "relative", "NATION": "nation",
    "LAW": "law", "LANDMARK": "landmark", "RESOURCE": "resource", "THEOLOGY": "theology",
    "TECH": "tech", "IMPROVEMENT": "improvement", "TRAIT": "trait", "OCCURRENCE": "event",
}
_LINK_BARE_RE = re.compile(r"\blink\(([A-Z0-9_]+?)(?:\s*,\s*\d+)?\)")


def _link_bare(m: "re.Match") -> str:
    """bare link(MISSION_HOLD_COURT) → 'Hold Court' (drop the category prefix)."""
    parts = m.group(1).split("_")
    words = parts[1:] if len(parts) > 1 else parts
    return " ".join(w.capitalize() for w in words)


def _repl_token(m: "re.Match") -> str:
    inner = m.group(1).strip()
    g = re.match(r"G\d+:([^:]*)", inner)                 # {G0:his:her} → his
    if g:
        return g.group(1)
    w = re.match(r"(?:sentencecase|lowercase|uppercase|capitalize):(.*)", inner, re.I)
    if w:                                                # {sentencecase:X} → X (re-processed)
        return w.group(1)
    typ = re.split(r"[-:,0-9. ]", inner, 1)[0].upper()
    if typ in ENTITY_NOUNS:                             # {RELIGION-1,1} → [religion]
        return f"[{ENTITY_NOUNS[typ]}]"
    return ""                                            # grammar helpers (S, p.is_sub.S, random_R…) → drop


def clean_text(s: str) -> str:
    if not s:
        return s
    s = _strip_link_templates(s)            # {lowercase:link(TOKEN,N)} → Token Words
    s = _LINK_BARE_RE.sub(_link_bare, s)    # bare link(TOKEN)
    for _ in range(6):                      # resolve nested {…{…}…}
        new = re.sub(r"\{([^{}]*)\}", _repl_token, s)
        if new == s:
            break
        s = new
    s = re.sub(r"\s+'s\b", "'s", s)                          # "name 's" → "name's"
    s = re.sub(r"\b(the )(the )+", r"\1", s, flags=re.I)     # "the the family" → "the family"
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)                   # space before punctuation
    s = re.sub(r"\(\s*\)", "", s)
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
    other = False  # aiOtherYields scale by the TARGET player's cities, not yours
    for r in outcome["rewards"]:
        if r["value"] is None:
            continue
        if r["scope"].endswith("Base"):
            base, yld, lbl = r["value"], r["yield"], r["label"]
            other = r["scope"].startswith("aiOther")
        elif r["scope"].endswith("Per"):
            per = r["value"]
    if base is None:
        return None
    # Mission reward yields are authored at DISPLAY scale and shown raw in-game
    # (the bonus display call passes no YIELDS_MULTIPLIER), so we do NOT divide
    # by 10 here. e.g. Rally = 90 + 10/city Training, reaching 230+ late game.
    base_d, per_d = base, (per or 0)
    cities_label = "Rival cities" if other else "Your cities"
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
        "citiesLabel": cities_label,
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


# A reward is a structured dict so the page can render the yield icon, exact
# amount and scaling tags. `text` is always present (display + search fallback).
#   yield gain : {text, yield, base, per}    base flat + per-city, turn-scales
#   per-city   : {text, yield, eachCity}     applied to each city, turn-scales
#   flat/other : {text}                      traits, units, relationships, …
def _yld(ykey: str, base: int | None = None, per: int = 0, each: int | None = None) -> dict:
    key = ykey.replace("YIELD_", "").lower()
    yl = ykey.replace("YIELD_", "").title()
    if each is not None:
        return {"text": f"{'+' if each >= 0 else ''}{each} {yl} (each city)", "yield": key, "eachCity": each}
    text = f"{'+' if base >= 0 else ''}{base} {yl}"
    if per:
        text += f" ({'+' if per >= 0 else ''}{per}/city)"
    return {"text": text, "yield": key, "base": base, "per": per}


def _txt(s: str) -> dict:
    return {"text": s}


# All bonus tables: base game + the per-content event-bonus files where the
# BONUS_EVENTOPTION_* contextual payloads actually live (without these the
# event rewards collapse to a useless "Affects a character" fallback).
BONUS_FILES = (
    "bonus.xml", "bonus-event.xml", "bonus-event-sap.xml", "bonus-event-btt.xml",
    "bonus-event-eoti.xml", "bonus-event-wd.xml", "bonus-event-wog.xml",
)


def bonus_index() -> dict:
    return index_many(*BONUS_FILES)


# Memory token → opinion delta (a "memory" is the lasting opinion shift a
# subject keeps after an event). Lazily loaded + cached.
_MEMORY_OPINION: dict | None = None


def _memory_opinion(token: str):
    global _MEMORY_OPINION
    if _MEMORY_OPINION is None:
        _MEMORY_OPINION = {}
        for fn in ("memory-character.xml", "memory-player.xml", "memory-family.xml",
                   "memory-tribe.xml", "memory-religion.xml", "memory-eoti.xml"):
            p = XML_DIR / fn
            if not p.exists():
                continue
            for e in ET.parse(p).getroot().findall("Entry"):
                zt = e.findtext("zType")
                op = e.findtext("iOpinion")
                if zt:
                    _MEMORY_OPINION[zt] = int(op) if op and op.strip() else None
    return _MEMORY_OPINION.get(token)


def _named(text: dict, token: str, prefix: str) -> str:
    return text.get("TEXT_" + token, _tok(token, prefix))


# trait token → list of effect lines (what the trait does), for reward tooltips.
# Built once from trait.xml via the shared effect humanizer.
_TRAIT_TIPS: dict | None = None


def _trait_tip(token: str) -> list[str]:
    global _TRAIT_TIPS
    if _TRAIT_TIPS is None:
        _TRAIT_TIPS = {}
        from humanize import (load_xml_indexes, render_effect_player,
                              render_effect_city, render_effect_unit)
        idx = load_xml_indexes(XML_DIR)
        ec = idx.get("effectCity.xml", {})
        eu = idx.get("effectUnit.xml", {})
        tp = XML_DIR / "trait.xml"
        if tp.exists():
            for e in ET.parse(tp).getroot().findall("Entry"):
                tid = e.findtext("zType")
                if not tid:
                    continue
                lines: list[str] = []
                lp = e.findtext("LeaderEffectPlayer")
                if lp and lp != "NONE":
                    lines += [f"As leader: {s}" for s in render_effect_player(lp, idx)]
                gc = e.findtext("GovernorEffectCity")
                if gc and gc in ec:
                    lines += [f"As governor: {s}" for s in render_effect_city(ec[gc], per_city=True, indexes=idx)]
                ge = e.findtext("GeneralEffectUnit")
                if ge and ge in eu:
                    lines += [f"As general: {s}" for s in render_effect_unit(eu[ge])]
                for rt, v in pairs(e, "aiRatingFallback"):
                    lines.append(f"{'+' if v >= 0 else ''}{v} {_tok(rt, 'RATING_')}")
                op = int(e.findtext("iOpinion") or "0")
                if op:
                    lines.append(f"{'+' if op > 0 else ''}{op} base opinion of this character")
                os_ = int(e.findtext("iOpinionSame") or "0")
                if os_:
                    lines.append(f"+{os_} opinion with same-trait characters")
                if e.findtext("bRemoveLeader") == "1":
                    lines.append("Removed as leader")
                if e.findtext("bNoJob") == "1":
                    lines.append("Cannot hold a job")
                _TRAIT_TIPS[tid] = lines
    return _TRAIT_TIPS.get(token, [])


def humanize_bonus(bonus_id: str, bonus_idx: dict, text: dict, _seen: set | None = None) -> list[dict]:
    """Structured reward list for an event/mission bonus (see schema above).
    Yields are display-scale (shown raw in-game) — no /10. Recurses into nested
    bonus containers; resolves the actual effect rather than a token fallback."""
    if not bonus_id or bonus_id == "NONE":
        return []
    _seen = _seen or set()
    if bonus_id in _seen:
        return []
    _seen.add(bonus_id)
    b = bonus_idx.get(bonus_id)
    if b is None:
        return [_txt(_fallback_label(bonus_id))]
    out: list[dict] = []

    base = {y: v for y, v in pairs(b, "aiGlobalYieldsBase")}
    per = {y: v for y, v in pairs(b, "aiGlobalYieldsPer")}
    for y in list(base) + [k for k in per if k not in base]:
        out.append(_yld(y, base=base.get(y, 0), per=per.get(y, 0)))
    for y, v in pairs(b, "aiCityYields"):
        out.append(_yld(y, each=v))

    # Culture-by-city-tier (aaiCultureYield): a per-city amount that depends on
    # each city's culture level — render as a min–max range.
    cult = [int(sp.findtext("iValue") or "0")
            for pr in b.findall("aaiCultureYield/Pair") for sp in pr.findall("SubPair")
            if (sp.findtext("iValue") or "0") != "0"]
    if cult:
        lo, hi = min(cult), max(cult)
        rng = f"{lo}" if lo == hi else f"{lo}–{hi}"
        out.append({"text": f"+{rng} Culture (by city tier)", "yield": "culture"})

    xp = int(b.findtext("iXPCharacter") or "0")
    if xp:
        out.append(_txt(f"+{xp} XP to the character"))
    leg = int(b.findtext("iLegitimacy") or "0")
    if leg:
        out.append(_txt(f"{'+' if leg >= 0 else ''}{leg} Legitimacy"))
    hap = int(b.findtext("iHappinessLevels") or "0")
    if hap:
        out.append(_txt(f"{'+' if hap >= 0 else ''}{hap} Happiness level{'s' if abs(hap) != 1 else ''}"))
    for r, v in pairs(b, "aiRatings"):
        out.append(_txt(f"{'+' if v >= 0 else ''}{v} {_named(text, r, 'RATING_')}"))

    for t in b.findall("aeAddTraits/zValue"):
        if t.text:
            nm = _named(text, t.text, "TRAIT_")
            tip = _trait_tip(t.text)
            out.append({"text": f"Gain trait: {nm}",
                        **({"tipTitle": f"{nm} — trait", "tip": tip} if tip else {})})
    if b.findall("aeRandomTraitDelay/zValue") or b.findall("aeRandomTrait/zValue"):
        out.append(_txt("Gain a random trait"))
    if b.findall("aeRandomLeaderRelationshipDelay/zValue") or b.findall("aeRandomLeaderRelationship/zValue"):
        out.append(_txt("Gains a random leader relationship"))

    cour = b.findtext("MakeCourtier")
    if cour:
        out.append(_txt(f"Gain a {_named(text, cour, 'COURTIER_')}"))
    for p in b.findall("AddCourtier/Pair"):
        ct = p.findtext("First")
        if ct:
            out.append(_txt(f"Gain a {_named(text, ct, 'COURTIER_')}"))
    for sp in b.findall("aeAddSpecialistClasses/zValue"):
        if sp.text:
            out.append(_txt(f"Gain a {_named(text, sp.text, 'SPECIALISTCLASS_')}"))
    for pr in b.findall("aeAddProjects/zValue"):
        if pr.text:
            out.append(_txt(f"Begin project: {_named(text, pr.text, 'PROJECT_')}"))
    imp = b.findtext("SetImprovement")
    if imp:
        out.append(_txt(f"Build {_named(text, imp, 'IMPROVEMENT_')} on the tile"))
    addres = b.findtext("AddResource")
    if addres:
        out.append(_txt(f"Adds {_named(text, addres, 'RESOURCE_')}"))
    if (b.findtext("bKillUnit") or "0") == "1":
        out.append(_txt("A unit is killed"))

    for u, v in pairs(b, "aiUnits"):
        out.append(_txt(f"+{v} {_named(text, u, 'UNIT_')}"))
    for u, v in pairs(b, "aiBonusUnits"):
        out.append(_txt(f"+{v} {_tok(u, 'BONUSUNITCLASS_')} unit"))
    reb = int(b.findtext("iRebelUnits") or "0")
    if reb:
        out.append(_txt(f"{reb} rebel unit{'s' if reb != 1 else ''} appear"))
    rel = b.findtext("AddLeaderRelationship")
    if rel:
        out.append(_txt(f"Leader relationship: {_tok(rel, 'RELATIONSHIP_')}"))
    amb = b.findtext("Ambition")
    if amb:
        out.append(_txt(f"Progress ambition: {_tok(amb, 'GOAL_')}"))

    # Opinion memories — the lasting opinion shift a subject keeps.
    for tag, who in (("Memory", ""), ("MemoryLeader", " (leader of you)"),
                     ("MemoryAllFamilies", " (all families)")):
        mem = b.findtext(tag)
        if mem and mem != "NONE":
            op = _memory_opinion(mem)
            out.append(_txt(f"{'+' if op >= 0 else ''}{op} opinion{who}" if op else f"Opinion memory{who}"))

    fl = b.findtext("FreeLaw")
    if fl and fl != "NONE":
        out.append(_txt(f"Free law: {_named(text, fl, 'LAW_')}"))
    if (b.findtext("iMarrySubject") or "0") not in ("0", ""):
        out.append(_txt("Arranges a marriage"))
    for t in b.findall("aeTechs/zValue"):
        if t.text:
            out.append(_txt(f"Gain tech: {_named(text, t.text, 'TECH_')}"))
    if b.find("aiLawOpinion/Pair") is not None:
        out.append(_txt("Law-based opinion shift"))

    # Nested bonus containers (BONUS_*_OPTION_* often wrap several payloads).
    for bz in b.findall("aeBonuses/zValue"):
        out += humanize_bonus(bz.text or "", bonus_idx, text, _seen)
    for bz in b.findall("aeAllCityBonuses/zValue"):
        out += [{**r, "text": r["text"] + " (every city)"} for r in humanize_bonus(bz.text or "", bonus_idx, text, _seen)]
    for p in b.findall("aeReligionBonuses/Pair"):
        out += [{**r, "text": r["text"] + " (by religion)"} for r in humanize_bonus(p.findtext("Second") or "", bonus_idx, text, _seen)]

    # A bonus we DID find but can't surface any tangible effect for is treated as
    # a no-op (no chip), rather than a misleading "Affects a …". The fallback
    # label is only for bonuses missing from the data entirely (handled above).
    return out


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


def _subject_kind(tok: str) -> str:
    if "COGNOMEN_" in tok:
        return " (a cognomen — an earned leader title)"
    if "CHARACTER_" in tok:
        return " (a character trait)"
    return ""


def option_requirements(opt: ET.Element) -> list[dict]:
    """Each requirement: {label, tip}. The tip spells out what the gating
    subjects are (cognomens are earned titles, etc.) so the chip is explainable."""
    reqs: list[dict] = []
    for tag in ("LeaderSubjectAny", "LeaderSubject", "aeSubjectReqs", "SubjectReqs"):
        vals = [v.text for v in opt.findall(f"{tag}/zValue") if v.text]
        if not vals:
            continue
        who = "The leader" if tag.startswith("Leader") else "The character"
        parts = [f"{subject_label(v)}{_subject_kind(v)}" for v in vals]
        tip = [f"{who} must have " + ("one of: " if len(parts) > 1 else "") + "; ".join(parts)]
        reqs.append({"label": " / ".join(subject_label(v) for v in vals), "tip": tip})
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
    bonus_idx = bonus_index()

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
            # Mission costs are display-scale and shown raw in-game (the cost
            # text builder passes no YIELDS_MULTIPLIER), so no /10 here.
            cost.append({"yield": y.lower(), "label": y.title(), "value": v})

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
