#!/usr/bin/env python3
"""
Build src/data/missions.json — every base-game mission with a dice-weighted
outcome table (≥2 aiResultDie results).

Source XMLs:
  mission.xml          — mission metadata (prereqs, cost, dice weights, subject)
  missionResult.xml    — each outcome (success/event/etc.) and the bonus it grants
  bonus.xml            — the actual yield rewards (base + per-city scaling)
  text-mission*.xml    — human-friendly names + descriptions

Rally / Hold Court / Steal Research keep their dedicated top-level pages
(`dedicated: true`); everything else renders at /missions/<slug> via the same
MissionPage component. Scenario / named-leader variants (Olympias, Mentuhotep,
Court of the Divine King, Rising Star, …) are excluded; `_ANY`-style internal
duplicates are folded into their base mission with a note (`variantNotes`).
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import _strip_link_templates  # noqa: E402
# Shared curation: readable SubjectCharacter labels + DLC display names.
from build_mission_catalog import WHO_LABELS, DLC_LABELS  # noqa: E402


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

# Each entry: slug, mission id, options.
#   dedicated    — page lives at /<slug> (the three original pages); everything
#                  else renders at /missions/<slug>.
#   folds        — internal `_ANY` / role-variant duplicates folded into this
#                  page: (variant id, dice_identical?, note shown on the page).
#                  dice_identical is asserted against the XML at build time.
#   scalingNote  — shown when the reward calculator is honestly impossible.
#
# Excluded on purpose: scenario / named-leader variants (OLYMPIAS, MENTUHOTEP,
# COURT_OF_THE_DIVINE_KING, SCHEME_AGAINST_RIVAL_RISING_STAR, …) and the
# per-religion Quell Dissent missions (single-result — no dice table).
MISSIONS = [
    ("rally",          "MISSION_RALLY_TROOPS",  {"dedicated": True}),
    ("hold-court",     "MISSION_HOLD_COURT",    {"dedicated": True}),
    ("steal-research", "MISSION_STEAL_RESEARCH", {"dedicated": True}),

    ("influence",             "MISSION_INFLUENCE", {}),
    ("intercession-religion", "MISSION_INTERCESSION_RELIGION", {}),
    ("intercession-family",   "MISSION_INTERCESSION_FAMILY", {}),
    # In-game text names both MISSION_CONVERT_SELF and MISSION_CONVERT_RELIGION
    # "Convert Religion"; suffix the self-conversion so the two pages differ.
    ("convert-self",          "MISSION_CONVERT_SELF", {"nameSuffix": " (Self)"}),
    ("convert-state",         "MISSION_CONVERT_STATE", {}),
    ("convert-religion",      "MISSION_CONVERT_RELIGION", {}),
    ("adopt",                 "MISSION_ADOPT", {}),
    ("legitimize",            "MISSION_LEGITIMIZE", {}),
    ("chosen-heir",           "MISSION_CHOSEN_HEIR", {}),
    ("divorce",               "MISSION_DIVORCE", {}),
    ("infiltrate",            "MISSION_INFILTRATE", {"folds": [
        ("MISSION_INFILTRATE_ANY", True,
         "An internal any-character variant (MISSION_INFILTRATE_ANY) rolls the "
         "same outcome dice — it differs only in who may run it."),
    ]}),
    ("slander",               "MISSION_SLANDER", {"folds": [
        ("MISSION_SLANDER_ANY", True,
         "An internal any-character variant (MISSION_SLANDER_ANY) rolls the "
         "same outcome dice — it differs only in who may run it."),
    ]}),
    ("assassinate",           "MISSION_ASSASSINATE", {"folds": [
        ("MISSION_ASSASSINATE_ANY", False,
         "The internal any-character variant (MISSION_ASSASSINATE_ANY) rolls 4 "
         "outcomes instead of 5: the undetected-failure outcome is dropped and "
         "exposed failure takes its weight (2/6)."),
    ]}),
    ("expose-agent",          "MISSION_EXPOSE_AGENT", {}),
    ("treachery",             "MISSION_TREACHERY", {}),
    ("insurrection",          "MISSION_INSURRECTION", {}),
    ("move-network",          "MISSION_MOVE_NETWORK", {}),
    ("high-synod",            "MISSION_HIGH_SYNOD", {}),
    ("family-gift",           "MISSION_FAMILY_GIFT", {}),
    ("pacify-city",           "MISSION_PACIFY_CITY", {}),
    ("imprison",              "MISSION_IMPRISON", {}),
    ("release",               "MISSION_RELEASE", {}),
    ("capture",               "MISSION_CAPTURE", {}),
    ("tutor",                 "MISSION_TUTOR", {"folds": [
        ("MISSION_TUTOR_SCHOLAR", True,
         "MISSION_TUTOR_SCHOLAR — the same mission run by a Scholar-archetype "
         "leader instead of a Tutor — rolls the same outcome dice and skips "
         "the opinion-scaled Money cost."),
    ]}),
    ("revel",                 "MISSION_REVEL", {}),
    ("scheme-against-rival",  "MISSION_SCHEME_AGAINST_RIVAL", {}),
    ("seek-political-allies", "MISSION_SEEK_POLITICAL_ALLIES", {}),
    ("gamble",                "MISSION_GAMBLE", {}),
    ("plot-vengeance",        "MISSION_PLOT_MURDER", {}),
    ("intimidate",            "MISSION_INTIMIDATE", {}),
    ("lead-delegation",       "MISSION_LEAD_DELEGATION", {"scalingNote":
        "Each delegation outcome pays a base amount plus a per-city amount for "
        "both your cities and the rival's (e.g. Science: 40 + 10 per your city "
        "+ 50 + 20 per rival city), then turn-scales like other mission "
        "rewards. The single-axis calculator can't chart two city counts, so "
        "it is omitted — the outcome cards above carry the exact values."}),
    ("pagan-sacrifices",      "MISSION_PAGAN_SACRIFICES", {}),
    ("impart-stewardship",    "MISSION_IMPART_STEWARDSHIP", {}),
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


def scaling_from_outcome(outcome: dict):
    """Pull the Base + Per(-city) yield off a mission outcome and tabulate the
    reward across a few empire sizes. Returns the scaling dict, None (no
    turn-scaled reward), or "mixed" when the bonus pays along BOTH your city
    count and the rival's (two axes the single-slider calculator can't chart,
    e.g. Lead Delegation)."""
    fams: dict[str, dict] = {}
    for r in outcome["rewards"]:
        if r["value"] is None:
            continue
        sc = r["scope"]
        if sc.endswith("Base") or sc.endswith("Per"):
            f = "other" if sc.startswith("aiOther") else "own"
            fams.setdefault(f, {})["base" if sc.endswith("Base") else "per"] = r
    if not fams:
        return None
    if len(fams) > 1:
        return "mixed"
    fam_key, d = next(iter(fams.items()))
    if "base" not in d:
        return None
    base, yld, lbl = d["base"]["value"], d["base"]["yield"], d["base"]["label"]
    per = d["per"]["value"] if "per" in d else None
    other = fam_key == "other"  # aiOtherYields scale by the TARGET player's cities
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
        # aiCityYields pays the bonus CITY (source: PlayerBonus.cs ~7238), not
        # every city — aeAllCityBonuses adds its own "(every city)" suffix.
        return {"text": f"{'+' if each >= 0 else ''}{each} {yl} (city)", "yield": key, "eachCity": each}
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


# ── Memories ────────────────────────────────────────────────────────────────
# A "memory" (memory-{tribe,player,character,family,religion,eoti}.xml) is the
# lasting opinion shift a subject keeps after an event option. Per InfoMemory
# in the game source (InfoBase.cs ~4167): if MemoryLevel is set, BOTH value
# and turns come from memoryLevel.xml (iValue = opinion, iTurns = decay);
# otherwise the entry's own iValue/iTurns apply. turns 0/absent = permanent.
MEMORY_FILES = ("memory-character.xml", "memory-player.xml", "memory-family.xml",
                "memory-tribe.xml", "memory-religion.xml", "memory-eoti.xml")
# eoti's MEMORY_* labels live in text-eoti.xml, not a text-memory-* file.
MEMORY_TEXT_FILES = ("text-memory.xml", "text-memory-btt.xml", "text-memory-sap.xml",
                     "text-memory-wog.xml", "text-memory-hittite.xml", "text-eoti.xml")
# Same story/option sets every event builder reads (base + DLC packs).
STORY_FILES = ("eventStory.xml", "eventStory-sap.xml", "eventStory-btt.xml",
               "eventStory-eoti.xml", "eventStory-wd.xml", "eventStory-wog.xml")
OPTION_FILES = ("eventOption.xml", "eventOption-sap.xml", "eventOption-btt.xml",
                "eventOption-eoti.xml", "eventOption-wd.xml", "eventOption-wog.xml")

_MEMORY_INFO: dict | None = None


def memory_info() -> dict[str, dict]:
    """Memory token → {label, opinion, turns}. Lazily loaded + cached."""
    global _MEMORY_INFO
    if _MEMORY_INFO is not None:
        return _MEMORY_INFO
    mtext = load_text(*MEMORY_TEXT_FILES)
    levels: dict[str, tuple[int, int]] = {}
    lp = XML_DIR / "memoryLevel.xml"
    if lp.exists():
        for e in ET.parse(lp).getroot().findall("Entry"):
            zt = e.findtext("zType")
            if zt:
                levels[zt] = (int(e.findtext("iValue") or "0"),
                              int(e.findtext("iTurns") or "0"))
    _MEMORY_INFO = {}
    for fn in MEMORY_FILES:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            zt = e.findtext("zType")
            if not zt:
                continue
            lvl = e.findtext("MemoryLevel") or ""
            if lvl and lvl in levels:
                op, turns = levels[lvl]
            else:
                op = int(e.findtext("iValue") or "0")
                turns = int(e.findtext("iTurns") or "0")
            label = clean_text(mtext.get(e.findtext("Text") or "", ""))
            if not label:
                label = re.sub(r"^MEMORY[A-Z]*_", "", zt).replace("_", " ").title()
            _MEMORY_INFO[zt] = {"label": label, "opinion": op or None, "turns": turns or None}
    return _MEMORY_INFO


# Memory token → the event stories it gates. A memory only matters beyond its
# opinion value when a subject.xml entry keys off it (MemoryPrereq = subject
# must hold it; MemoryInvalid = subject must NOT hold it) AND some event casts
# or requires that subject. Events cast subjects through both schemas — the
# old aeSubjects/zValue + SubjectExtras/SubjectAny pairs, and the new nested
# Subjects/Subject with Type + Extra — and their options can additionally
# require subjects (LeaderSubject/PlayerSubject/aeSubjectReqs/…). Negated
# tests (SubjectNotExtras, NotExtra, *NotAny) flip the polarity: a negated
# MemoryPrereq subject means the memory BLOCKS the event, a negated
# MemoryInvalid subject means it enables it.
_MEMORY_CHAIN: dict | None = None


def memory_chain() -> dict[str, dict[str, list[str]]]:
    """Memory token → {"enables": [story ids], "blocks": [story ids]}."""
    global _MEMORY_CHAIN
    if _MEMORY_CHAIN is not None:
        return _MEMORY_CHAIN
    prereq_of: dict[str, str] = {}   # subject token → memory it requires
    invalid_of: dict[str, str] = {}  # subject token → memory it forbids
    sp = XML_DIR / "subject.xml"
    if sp.exists():
        for e in ET.parse(sp).getroot().findall("Entry"):
            z = e.findtext("zType")
            if not z:
                continue
            mp = e.findtext("MemoryPrereq")
            if mp and mp != "NONE":
                prereq_of[z] = mp
            mi = e.findtext("MemoryInvalid")
            if mi and mi != "NONE":
                invalid_of[z] = mi

    chain: dict[str, dict[str, list[str]]] = {}

    def add(mem: str, key: str, zid: str) -> None:
        d = chain.setdefault(mem, {"enables": [], "blocks": []})
        if zid not in d[key]:
            d[key].append(zid)

    eopt_idx = index_many(*OPTION_FILES)
    POS_REQ_TAGS = ("LeaderSubject", "LeaderSubjectAny", "PlayerSubject",
                    "IndexSubject", "IndexSubjectAny", "aeSubjectReqs", "SubjectReqs")
    NEG_REQ_TAGS = ("LeaderSubjectNotAny", "PlayerSubjectNotAny", "IndexSubjectNotAny")

    def opt_reqs(opt: ET.Element, tags: tuple[str, ...]) -> list[str]:
        toks: list[str] = []
        for tag in tags:
            toks += [v.text for v in opt.findall(f"{tag}/zValue") if v.text]
            single = (opt.findtext(tag) or "").strip()
            if single and single != "NONE":
                toks.append(single)
        return toks

    for zid, s in index_many(*STORY_FILES).items():
        pos: list[str] = [z.text for z in s.findall("aeSubjects/zValue") if z.text]
        neg: list[str] = []
        for tag in ("SubjectExtras", "SubjectAny"):
            pos += [p.findtext("Second") for p in s.findall(f"{tag}/Pair") if p.findtext("Second")]
        neg += [p.findtext("Second") for p in s.findall("SubjectNotExtras/Pair") if p.findtext("Second")]
        for sub in s.findall("Subjects/Subject"):
            t = sub.findtext("Type")
            if t:
                pos.append(t)
            pos += [x.text for x in sub.findall("Extra") if x.text]
            neg += [x.text for x in sub.findall("NotExtra") if x.text]
        # Option-level subject requirements gate individual choices the same way.
        opts = [eopt_idx[oz.text] for oz in s.findall("aeOptions/zValue")
                if oz.text and oz.text in eopt_idx]
        opts += s.findall("EventOptions/EventOption")
        for opt in opts:
            pos += opt_reqs(opt, POS_REQ_TAGS)
            neg += opt_reqs(opt, NEG_REQ_TAGS)
        for tok in pos:
            if tok in prereq_of:
                add(prereq_of[tok], "enables", zid)
            if tok in invalid_of:
                add(invalid_of[tok], "blocks", zid)
        for tok in neg:
            if tok in prereq_of:
                add(prereq_of[tok], "blocks", zid)
            if tok in invalid_of:
                add(invalid_of[tok], "enables", zid)
    _MEMORY_CHAIN = chain
    return chain


def memory_rewards(b: ET.Element) -> list[dict]:
    """Reward rows for a bonus's memory grants. Each carries the memory token
    (so builders can wire 'may enable' follow-up links) and, when nothing in
    the data keys off the memory, an honest note — the in-game '[Could lead to
    future Events]' hint shows for ANY memory grant, consumed or not."""
    out: list[dict] = []
    for tag, who in (("Memory", ""), ("MemoryLeader", " (leader of you)"),
                     ("MemoryAllFamilies", " (all families)"),
                     ("MemoryAllPlayers", " (all rivals)")):
        mem = b.findtext(tag)
        if not mem or mem == "NONE":
            continue
        info = memory_info().get(mem)
        label = info["label"] if info else re.sub(r"^MEMORY[A-Z]*_", "", mem).replace("_", " ").title()
        op = info["opinion"] if info else None
        turns = info["turns"] if info else None
        if op and turns:
            detail = f" ({'+' if op >= 0 else ''}{op} opinion for {turns} turns)"
        elif op:
            detail = f" ({'+' if op >= 0 else ''}{op} opinion, permanent)"
        elif turns:
            detail = f" ({turns} turns)"
        else:
            detail = ""
        r: dict = {"text": f"Remembered{who}: {label}{detail}", "memory": mem}
        ch = memory_chain().get(mem)
        if not ch or not (ch["enables"] or ch["blocks"]):
            r["note"] = "no event currently keys off this"
        out.append(r)
    return out


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
    # Flat aiGlobalYields are added AFTER getAdjustedValue (PlayerBonus.cs
    # ~5820): a fixed amount that does NOT turn-scale.
    for y, v in pairs(b, "aiGlobalYields"):
        key = y.replace("YIELD_", "").lower()
        yl = y.replace("YIELD_", "").title()
        out.append({"text": f"{'+' if v >= 0 else ''}{v} {yl}", "yield": key, "flat": v})
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
    for t in b.findall("aeRemoveTraits/zValue"):
        if t.text:
            nm = _named(text, t.text, "TRAIT_")
            tip = _trait_tip(t.text)
            out.append({"text": f"Loses trait: {nm}",
                        **({"tipTitle": f"{nm} — trait", "tip": tip} if tip else {})})
    if b.findall("aeRandomTraitDelay/zValue") or b.findall("aeRandomTrait/zValue"):
        out.append(_txt("Gain a random trait"))
    if b.findall("aeRandomLeaderRelationshipDelay/zValue") or b.findall("aeRandomLeaderRelationship/zValue"):
        out.append(_txt("Gains a random leader relationship"))

    cour = b.findtext("MakeCourtier")
    if cour:
        out.append(_txt(f"Gain a {_named(text, cour, 'COURTIER_')}"))
    if b.findtext("bRandomCourtier") == "1":
        out.append(_txt("Gain a random Courtier"))
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
    if (b.findtext("bKillCharacter") or "0") == "1":
        out.append(_txt("The character is killed"))

    # Character / religion / dynasty state changes. The i*Subject fields hold
    # an event-subject slot index (often 0) — presence is what matters.
    for tag, line in (
        ("iConvertReligionSubject", "Converts to the target religion"),
        ("iConvertedBySubject",     "The target converts to the subject's religion"),
        ("iAdoptedBySubject",       "The target is adopted"),
        ("iDivorcedBySubject",      "The marriage is dissolved"),
        ("iMoveNetworkCitySubject", "Your agent network moves to the target city"),
    ):
        if b.find(tag) is not None:
            out.append(_txt(line))
    for tag, line in (
        ("bConvertStateReligion", "Changes the state religion"),
        ("bChosenHeir",           "Becomes the chosen heir"),
        ("bRevealTerritory",      "Reveals the target player's territory"),
        ("bExposeAgentNetwork",   "Exposes a foreign agent network in the city"),
        ("bLoseAgentNetwork",     "Your agent network there is lost"),
    ):
        if (b.findtext(tag) or "0") == "1":
            out.append(_txt(line))
    hp = int(b.findtext("iHPCity") or "0")
    if hp:
        out.append(_txt(f"{'+' if hp > 0 else ''}{hp} HP to the city"))

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

    # Opinion memories — the lasting opinion shift a subject keeps (and the
    # hook future events may key off; see memory_rewards).
    out += memory_rewards(b)

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
    for tag, suffix in (("Achievement", ""),
                        ("AchievementIfHeir", " (if the target is an heir)"),
                        ("AchievementIfOtherLeader", " (if the target leads a rival nation)")):
        ach = b.findtext(tag)
        if ach and ach != "NONE":
            out.append(_txt(f"Steam achievement{suffix}: {_tok(ach, 'ACHIEVEMENT_')}"))

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


# ── Raw view ────────────────────────────────────────────────────────────────
# The humanizer launders raw weights/tokens into confident prose; for events we
# also expose the underlying XML so nothing is hidden (and so the user can spot
# where the humanizer is wrong). These emit the raw token/field payloads.
def raw_bonus_fields(b: ET.Element) -> list[str]:
    """Every non-empty effect field of a bonus, as 'tag value' lines."""
    out: list[str] = []
    for c in b:
        if c.tag in ("zType", "Name", "Description"):
            continue
        kids = list(c)
        if kids:
            parts: list[str] = []
            for p in c.findall("Pair"):
                k = p.findtext("zIndex") or p.findtext("First") or ""
                v = p.findtext("iValue") or p.findtext("Second") or ""
                sub = [f"{sp.findtext('zSubIndex')}={sp.findtext('iValue')}" for sp in p.findall("SubPair")]
                parts.append(f"{k}={v}" if v else (f"{k}[{','.join(sub)}]" if sub else k))
            parts += [z.text for z in c.findall("zValue") if z.text]
            out.append(f"{c.tag}: {', '.join(parts)}" if parts else c.tag)
        elif (c.text or "").strip():
            out.append(f"{c.tag} {c.text.strip()}")
    return out


GATE_TAGS = (
    "LeaderSubject", "LeaderSubjectAny", "LeaderSubjectNotAny",
    "PlayerSubject", "PlayerSubjectNotAny", "IndexSubject", "IndexSubjectAny",
    "IndexSubjectNotAny", "aeSubjectReqs", "SubjectReqs",
)


def option_raw(opt: ET.Element, eopt_idx: dict, bonus_idx: dict) -> dict:
    """Raw gates (every subject that qualifies the choice, incl. hidden prereqs)
    and raw bonus payloads granted by the option."""
    gates: list[dict] = []
    for tag in GATE_TAGS:
        vals = [v.text for v in opt.findall(f"{tag}/zValue") if v.text]
        if not vals:
            single = opt.findtext(tag)
            if single and single != "NONE":
                vals = [single]
        if vals:
            gates.append({"tag": tag, "values": vals})
    if (opt.findtext("bHidePrereqs") or "0") == "1":
        gates.append({"tag": "bHidePrereqs", "values": ["prereqs hidden in-game"]})

    bonuses: list[dict] = []

    def add(bid: str, weight=None, total=None):
        if not bid or bid == "NONE":
            return
        b = bonus_idx.get(bid)
        bonuses.append({"id": bid, "weight": weight,
                        "pct": (weight / total) if (weight is not None and total) else None,
                        "fields": raw_bonus_fields(b) if b is not None else ["(not in bonus tables)"]})

    prob = pairs(opt, "aiEventOptionProb")
    if prob:
        total = sum(v for _, v in prob) or 1
        for sub_id, w in prob:
            sub = eopt_idx.get(sub_id)
            if sub is not None:
                for bz in sub.findall("aeBonuses/zValue"):
                    add(bz.text or "", w, total)
            else:
                add(sub_id, w, total)
    else:
        for bz in opt.findall("aeBonuses/zValue"):
            add(bz.text or "")
        for p in opt.findall("SubjectBonuses/Pair"):
            add(p.findtext("Second") or "")
    return {"gates": gates, "bonuses": bonuses}


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
                "raw": option_raw(opt, eopt_idx, bonus_idx),
            })

        # NOTE: no "text" field — story narrative bodies stay an in-game
        # discovery; the cards render title + choices only.
        out.append({
            "id": zt,
            "name": clean_text(text.get(s.findtext("Name") or "", _tok(zt, "EVENTSTORY_"))),
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
        "text-mission.xml", "text-mission-btt.xml", "text-mission-sap.xml",
        "text-mission-wog.xml",
        "text-missionResult.xml", "text-missionResult-btt.xml",
        "text-missionResult-sap.xml", "text-missionResult-wog.xml",
        "text-infos.xml", "text-tech.xml", "text-subject.xml", "text-subject-sap.xml",
        # Event chain text: story titles/flavor, option prose, traits, units.
        "text-eventStory.xml", "text-eventStory-sap.xml", "text-eventStory-btt.xml",
        "text-eventStory-eoti.xml",
        "text-eventStoryTitle.xml", "text-eventStoryTitle-sap.xml",
        "text-eventStoryTitle-btt.xml",
        "text-eventOption.xml", "text-eventOption-sap.xml", "text-eventOption-btt.xml",
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
    story_idx = index_many("eventStory.xml", "eventStory-sap.xml", "eventStory-btt.xml",
                           "eventStory-eoti.xml", "eventStory-wd.xml", "eventStory-wog.xml")
    eopt_idx = index_many(
        "eventOption.xml", "eventOption-sap.xml", "eventOption-btt.xml",
        "eventOption-eoti.xml", "eventOption-wd.xml", "eventOption-wog.xml",
    )

    def who_label(token: str) -> str:
        """Readable 'run by' label for a SubjectCharacter token."""
        if not token:
            return ""
        if token in WHO_LABELS:
            return WHO_LABELS[token]
        t = text.get(f"TEXT_{token}")
        if t:  # text-subject entries may still carry bare link(TOKEN) markup
            return _LINK_BARE_RE.sub(_link_bare, t).strip()
        return token.replace("SUBJECT_", "").replace("_", " ").title()

    def dice_pairs(entry: ET.Element) -> list[tuple[str, int]]:
        return [(p.findtext("zIndex") or "", int(p.findtext("iValue") or "0"))
                for p in entry.findall("aiResultDie/Pair")]

    out: list[dict] = []
    for slug, mid, opts in MISSIONS:
        m = missions_idx.get(mid)
        if m is None:
            print(f"⚠ missing mission {mid}", file=sys.stderr)
            continue

        name = text.get(m.findtext("Name") or "", mid.replace("MISSION_", "").title()) \
            + opts.get("nameSuffix", "")
        desc = text.get(m.findtext("Description") or "", "")
        turns = int(m.findtext("iMissionTurns") or "0")
        turns_scaled = (m.findtext("iMissionTurnsScaled") or "0") != "0"
        tech_prereq = m.findtext("TechPrereq")
        tech_name = (
            text.get(f"TEXT_{tech_prereq}", tech_prereq.replace("TECH_", "").replace("_", " ").title())
            if tech_prereq else None
        )
        subject_disp = who_label(m.findtext("SubjectCharacter") or "")
        dlc_token = m.findtext("GameContentRequired") or ""
        dlc = DLC_LABELS.get(dlc_token, dlc_token.replace("_", " ").title()) if dlc_token else None

        def costs(tag: str) -> list[dict]:
            o = []
            for pair in m.findall(f"{tag}/Pair"):
                y = (pair.findtext("zIndex") or "").replace("YIELD_", "")
                v = int(pair.findtext("iValue") or "0")
                # Mission costs are display-scale and shown raw in-game (the cost
                # text builder passes no YIELDS_MULTIPLIER), so no /10 here.
                o.append({"yield": y.lower(), "label": y.title(), "value": v})
            return o

        cost = costs("aiYieldCost")
        # aiYieldCostOpinion is a base cost modified by the target's opinion of
        # you (PlayerEvent.cs getMissionCost) — shown as a separate chip.
        opinion_cost = costs("aiYieldCostOpinion")

        # Fold internal `_ANY`-style duplicates into this page; verify the
        # claimed dice-identity against the XML so notes can't go stale.
        folded_ids: list[str] = []
        variant_notes: list[str] = []
        for fid, same_dice, note in opts.get("folds", []):
            fm = missions_idx.get(fid)
            if fm is None:
                print(f"⚠ missing fold {fid} for {mid}", file=sys.stderr)
                continue
            identical = dice_pairs(fm) == dice_pairs(m)
            if identical != same_dice:
                print(f"⚠ fold {fid}: dice identity changed (expected "
                      f"{'identical' if same_dice else 'different'}) — update its note",
                      file=sys.stderr)
            folded_ids.append(fid)
            variant_notes.append(note)

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
                "name": clean_text(text.get(
                    (result.findtext("Name") if result is not None else "") or "",
                    rid.replace("MISSIONRESULT_", "").replace("_", " ").title(),
                )),
                "description": clean_text(text.get(
                    (result.findtext("Description") if result is not None else "") or "",
                    "",
                )),
                "rewards": [],
                "ratingModifier": [],
            }
            if result is not None:
                # Rating modifier on the result (e.g., Steal Research +24 Wisdom influence)
                for rp in result.findall("aiRatingModifier/Pair"):
                    r = (rp.findtext("zIndex") or "").replace("RATING_", "")
                    v = int(rp.findtext("iValue") or "0")
                    outcome["ratingModifier"].append({"rating": r.lower(), "label": r.title(), "value": v})

                # Resolve the bonus → structured yield rows (Base + Per turn-
                # scale; flat aiGlobalYields don't), then everything else the
                # bonus does via the shared humanizer (traits, kills,
                # conversions, memories, nested bonuses, …) as label rows.
                bonus_id = result.findtext("TargetBonus")
                bonus = bonus_idx.get(bonus_id) if bonus_id else None
                if bonus is not None:
                    outcome["rewards"] = (
                        yield_pairs(bonus, "aiGlobalYieldsBase", "aiOtherYieldsBase", "aiYieldsBase")
                        + yield_pairs(bonus, "aiGlobalYieldsPer", "aiOtherYieldsPer", "aiYieldsPer")
                        + yield_pairs(bonus, "aiGlobalYields", "aiOtherYields")
                    )
                    # The humanizer re-emits top-level Global yields; drop those
                    # duplicates (matched by their rendered text), keep the rest.
                    top_texts = set()
                    gbase = {y: v for y, v in pairs(bonus, "aiGlobalYieldsBase")}
                    gper = {y: v for y, v in pairs(bonus, "aiGlobalYieldsPer")}
                    for y in list(gbase) + [k for k in gper if k not in gbase]:
                        top_texts.add(_yld(y, base=gbase.get(y, 0), per=gper.get(y, 0))["text"])
                    for y, v in pairs(bonus, "aiGlobalYields"):
                        yl = y.replace("YIELD_", "").title()
                        top_texts.add(f"{'+' if v >= 0 else ''}{v} {yl}")
                    for r in humanize_bonus(bonus_id, bonus_idx, text):
                        if r["text"] in top_texts:
                            continue
                        lbl = r["text"] + (f" ({r['note']})" if r.get("note") else "")
                        outcome["rewards"].append({"label": lbl, "value": None, "scope": "Special"})

                # Bonuses applied to a mission SUBJECT (slot-indexed list) —
                # e.g. the imprisoned character's family resents you.
                for bz in result.findall("SubjectBonuses/zValue"):
                    for r in humanize_bonus(bz.text or "", bonus_idx, text):
                        lbl = r["text"] + (f" ({r['note']})" if r.get("note") else "")
                        outcome["rewards"].append({"label": lbl, "value": None, "scope": "Special"})

            outcomes.append(outcome)

        # Reward scaling for the calculator. Only honest when the non-event
        # outcomes agree on a single Base(+Per) reward along ONE city axis;
        # otherwise skip it and explain why (scalingNote).
        scaling = None
        scaling_note = opts.get("scalingNote")
        candidates = []
        mixed = False
        for o in outcomes:
            if o["id"].endswith("_EVENT"):
                continue
            s = scaling_from_outcome(o)
            if s == "mixed":
                mixed = True
            elif s:
                candidates.append(s)
        uniq = {(c["yield"], c["rawBase"], c["rawPer"], c["citiesLabel"]) for c in candidates}
        if mixed:
            scaling_note = scaling_note or (
                "This mission's reward scales with both your city count and the "
                "rival's, which the single-axis calculator can't chart — the "
                "outcome cards above carry the exact base + per-city values.")
            print(f"  ⚠ {slug}: two-axis reward scaling — calculator skipped", file=sys.stderr)
        elif len(uniq) == 1:
            scaling = candidates[0]
            scaling["cap"] = gint.get(f"MAX_{scaling['yield'].upper()}")  # raw cap, or None
            scaling["inflationTurns"] = inflation_turns
            scaling_note = None
        elif len(uniq) > 1:
            scaling_note = scaling_note or (
                "Different outcomes scale differently with empire size — the "
                "outcome cards above carry each one's base + per-city values.")
            print(f"  ⚠ {slug}: outcomes scale differently — calculator skipped", file=sys.stderr)

        # Event chains: any outcome whose result id has stories hanging off
        # EVENTTRIGGER_MISSION_FINISHED gets a group (usually the *_EVENT
        # result, but e.g. Tutor's rating results fire follow-ups too).
        event_groups = []
        for o in outcomes:
            evs = build_events(o["id"], story_idx, eopt_idx, bonus_idx, text)
            if evs:
                event_groups.append({
                    "outcomeId": o["id"],
                    "outcomeName": o["name"],
                    "weight": o["weight"],
                    "total": total_weight,
                    "probability": o["probability"],
                    "isEventResult": o["id"].endswith("_EVENT"),
                    "events": evs,
                })

        out.append({
            "slug": slug,
            "id": mid,
            "dedicated": bool(opts.get("dedicated")),
            "path": slug if opts.get("dedicated") else f"missions/{slug}",
            "foldedIds": folded_ids,
            "variantNotes": variant_notes,
            "name": name,
            "description": desc,
            "turns": turns,
            "turnsScaled": turns_scaled,
            "subject": subject_disp,
            "dlc": dlc,
            "techPrereq": (
                {"id": tech_prereq, "label": tech_name, "slug": tech_prereq.replace("TECH_", "").lower().replace("_", "-")}
                if tech_prereq else None
            ),
            "cost": cost,
            "opinionCost": opinion_cost,
            "outcomes": outcomes,
            "totalDiceWeight": total_weight,
            "scaling": scaling,
            "scalingNote": scaling_note,
            "eventGroups": event_groups,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(out)} missions")
    for m in out:
        cost_str = ", ".join(f"{c['value']} {c['label']}" for c in m["cost"]) or "—"
        stories = sum(len(g["events"]) for g in m["eventGroups"])
        print(f"  · {m['name']:24} {m['turns']}t · {len(m['outcomes'])} outcomes · "
              f"{stories:3d} stories · cost {cost_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
