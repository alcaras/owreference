#!/usr/bin/env python3
"""
Build src/data/diplomacy.json — diplomatic states, war states/war score,
and the diplomacy actions (state-changing missions) for the /diplomacy tab.

Sources (reference/XML/Infos):
  diplomacy.xml    — the 4 diplomatic states (War/Truce/Peace/Team) with their
                     opinion side-effects (iOpinion, iOpinionEnemy,
                     iOpinionEthnicity, iOpinionReligion, iWarModifier)
  warState.xml     — the 5 war-score bands (Routed…Triumphant) with iThreshold,
                     iTruceModifier, iDiplomacyMoneyPercent
  mission.xml      — the diplomacy missions (Declare War, Truce, Peace,
                     Alliance, Break Peace, Demand Tribute, third-party wars)
  color.xml        — COLOR_DIPLOMACY_* hex (in-game colors only)
  globalsInt.xml   — MIN_TREATY_TURNS, TRIBUTE_TURNS, TRIBUTE_OPINION_PLAYER, …
  text-*.xml       — names + helptext

War-score mechanics are underspecified by XML; the deltas and band semantics
come from the local game source (reference/Source/Base/Game/GameCore):
  InfoHelpers.getWarState — band = smallest iThreshold >= score diff
                            (Triumphant has no threshold → everything above)
  City.cs  setPlayer      — capture player city: +100 team war score
                            (tribe-owned flips use ±200, the doubled tribe scale)
  Unit.cs  doCityCapture  — breach a player city (falls to anarchy): +50
                            (tribe breaching a player city: +100)
  Unit.cs  kill           — kill an enemy unit: +10 (tribe scale: ±10/20)
  Unit.cs  pillage/burn   — pillage or burn an improvement: +5
  PlayerAI.getDiplomacyMoney — iDiplomacyMoneyPercent scales the money the AI
                            offers/demands in war diplomacy by war state
  Tribe.getTrucePercent   — iTruceModifier modifies the chance a tribe offers
                            or accepts a truce
  PlayerEvent.getMissionCost — aiYieldCostOpinion is modified by the
                            performing character's opinion of you
                            (opinionCharacter.xml iMissionCostModifier)
  Player.isMinTreatyTurns — MIN_TREATY_TURNS gates re-declarations after a
                            war/peace change (and the first turns of the game)

Mission costs are STOCKPILE costs stored 1:1 (same convention as
build_mission_catalog.py) — Peace really costs 200 Civics.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import _strip_link_templates, load_xml_indexes, render_bonus  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "diplomacy.json"

# yield-icon tokens like {YIELD_MONEY} left over after link() stripping
_ICON_TOKEN_RE = re.compile(r"\{[A-Z][A-Z0-9_]*\}")
# int(MIN_TREATY_TURNS)-style global substitutions in helptext
_INT_TOKEN_RE = re.compile(r"int\(([A-Z][A-Z0-9_]*)\)")
# plural link forms: link(CONCEPT_NATION,2) → "Nations" (the shared stripper
# drops the count and would render the singular)
_LINK_PLURAL_RE = re.compile(r"\{?(?:lowercase:)?link\(([A-Z_]+),([2-9])\)\}?")

_GLOBALS_INT: dict[str, int] = {}


def _pluralize(word: str) -> str:
    if word.endswith("y"):
        return word[:-1] + "ies"
    return word + "s"


def _link_plural(m: re.Match) -> str:
    parts = m.group(1).split("_")
    if len(parts) > 1:
        parts = parts[1:]
    words = [p.title() for p in parts]
    words[-1] = _pluralize(words[-1])
    return " ".join(words)


def clean(s: str) -> str:
    s = _LINK_PLURAL_RE.sub(_link_plural, s)
    s = _strip_link_templates(s)
    s = _INT_TOKEN_RE.sub(lambda m: str(_GLOBALS_INT.get(m.group(1), m.group(0))), s)
    return _ICON_TOKEN_RE.sub("", s).replace("  ", " ").strip()


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def index(name: str) -> dict[str, ET.Element]:
    p = XML_DIR / name
    if not p.exists():
        return {}
    return {e.findtext("zType"): e for e in ET.parse(p).getroot().findall("Entry")
            if e.findtext("zType")}


def load_text(*filenames: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").split("~")[0].strip()
            if k and k not in out:
                out[k] = clean(en)
    return out


def gi(e: ET.Element, tag: str, default: int = 0) -> int:
    t = e.findtext(tag)
    try:
        return int(t) if t not in (None, "") else default
    except ValueError:
        return default


# ── Diplomatic states ──────────────────────────────────────────────────────

# Help text key per state. TEAM has no LINK_HELP entry — its meaning (same
# team, permanent peace) is the rule itself, so we curate one line.
STATE_HELP_KEY = {
    "DIPLOMACY_WAR": "TEXT_HELPTEXT_LINK_HELP_DIPLOMACY_WAR",
    "DIPLOMACY_TRUCE": "TEXT_HELPTEXT_LINK_HELP_DIPLOMACY_TRUCE",
    "DIPLOMACY_PEACE": "TEXT_HELPTEXT_LINK_HELP_DIPLOMACY_PEACE_PLAYER",
}
STATE_HELP_TRIBE_KEY = {
    "DIPLOMACY_PEACE": "TEXT_HELPTEXT_LINK_HELP_DIPLOMACY_PEACE_TRIBE",
}
TEAM_HELP = ("Members of the same team. Permanent — always at Peace, share "
             "war and peace, and can never change diplomatic state with "
             "each other.")


def build_states(text: dict[str, str]) -> list[dict]:
    colors = {}
    for e in parse("color.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        hexv = e.findtext("zHexValue") or ""
        if z.startswith("COLOR_DIPLOMACY") and hexv:
            colors[z] = "#" + hexv.lstrip("#")[:6]  # drop alpha

    out = []
    for order, e in enumerate(parse("diplomacy.xml").findall("Entry")):
        z = e.findtext("zType")
        if not z:
            continue
        help_key = STATE_HELP_KEY.get(z)
        out.append({
            "id": z,
            "slug": z.replace("DIPLOMACY_", "").lower(),
            "order": order,
            "name": text.get(e.findtext("Name") or "", z),
            "color": colors.get(e.findtext("zColor") or "", None),
            "hostile": gi(e, "bHostile") == 1,
            "peace": gi(e, "bPeace") == 1,
            # Opinion side-effects (see PlayerOpinion.cs for exact semantics)
            "opinion": gi(e, "iOpinion"),                  # their opinion of you while in this state
            "opinionEnemy": gi(e, "iOpinionEnemy"),        # per third party hostile to them you share this state with
            "opinionEthnicity": gi(e, "iOpinionEthnicity"),  # your characters of that nation's ethnicity
            "opinionReligion": gi(e, "iOpinionReligion"),  # that nation's religion's opinion of you
            "warModifier": gi(e, "iWarModifier"),          # modifies AI chance to declare war on you
            "help": text.get(help_key, "") if help_key else TEAM_HELP,
            "helpTribe": text.get(STATE_HELP_TRIBE_KEY.get(z, ""), "") or None,
        })
    return out


# ── War states ──────────────────────────────────────────────────────────────

def build_war_states(text: dict[str, str]) -> list[dict]:
    entries = [e for e in parse("warState.xml").findall("Entry") if e.findtext("zType")]
    # InfoWarState.miThreshold defaults to int.MaxValue (Triumphant has none).
    # Band = smallest threshold >= score diff (InfoHelpers.getWarState).
    out = []
    prev_threshold: int | None = None
    for order, e in enumerate(entries):
        z = e.findtext("zType")
        t = e.findtext("iThreshold")
        threshold = int(t) if t not in (None, "") else None
        if threshold is None:
            rng = f"{prev_threshold + 1:+d} and above"
        elif prev_threshold is None:
            rng = f"{threshold:+d} and below"
        else:
            rng = f"{prev_threshold + 1:+d} to {threshold:+d}"
        out.append({
            "id": z,
            "order": order,
            "name": text.get(e.findtext("Name") or "", z),
            "threshold": threshold,
            "range": rng,
            "truceModifier": gi(e, "iTruceModifier"),
            "diplomacyMoneyPercent": gi(e, "iDiplomacyMoneyPercent"),
        })
        prev_threshold = threshold
    return out


# War-score deltas, curated from game source (see module docstring).
WAR_SCORE = {
    "note": ("War score is tracked per pair of teams; your war state against an "
             "opponent comes from the score difference. Tribal wars use a "
             "doubled scale."),
    "nations": [
        {"event": "Kill an enemy unit", "delta": 10,
         "source": "Unit.cs (kill)"},
        {"event": "Pillage or burn an improvement in their territory", "delta": 5,
         "source": "Unit.cs (pillage / burn)"},
        {"event": "Breach an enemy city (it falls into anarchy)", "delta": 50,
         "source": "Unit.cs doCityCapture"},
        {"event": "Take ownership of an enemy city", "delta": 100,
         "source": "City.cs setPlayer"},
    ],
    "tribes": [
        {"event": "You kill a tribal unit", "delta": 10,
         "source": "Unit.cs (kill), tribe score −10"},
        {"event": "A tribe kills one of your units", "delta": -20,
         "source": "Unit.cs (kill), tribe score +20"},
        {"event": "You pillage a tribal improvement", "delta": 5,
         "source": "Unit.cs (pillage), tribe score −5"},
        {"event": "You capture a tribal settlement", "delta": 200,
         "source": "City.cs setPlayer, tribe score −200"},
        {"event": "A tribe breaches one of your cities", "delta": -100,
         "source": "Unit.cs doCityCapture, tribe score +100"},
        {"event": "A tribe takes ownership of one of your cities", "delta": -200,
         "source": "City.cs setPlayer, tribe score +200"},
    ],
}


# ── Diplomacy actions (missions) ────────────────────────────────────────────

# Readable labels for the subject requirements used by the diplomacy missions.
# Derived from subject.xml + subjectRelation.xml (RelationUs ranges, opinion
# minimums, alliance flags) and opinionPlayer/opinionTribe.xml thresholds:
# Pleased band starts at +100, Friendly at +200, Cautious at 0.
SUBJECT_TARGET_LABEL = {
    "SUBJECT_PLAYER_WAR": "a Nation you are at War with",
    "SUBJECT_PLAYER_TRUCE": "a Nation you have a Truce with",
    "SUBJECT_PLAYER_PEACE": "a Nation you are at Peace with",
    "SUBJECT_PLAYER_ALLIANCE": "your allied Nation",
    "SUBJECT_PLAYER_TRADING": "a Nation you are trading with",
    "SUBJECT_PLAYER_CAN_ALLIANCE": "a Nation able to form an Alliance (neither side already allied)",
    "SUBJECT_PLAYER_NOT_TEAM_HUMAN_OR_AI": "any other Nation",
    "SUBJECT_PLAYER_WAR_HUMAN_OR_AI": "a Nation at War with you",
    "SUBJECT_TRIBE_WAR": "a Tribe you are at War with",
    "SUBJECT_TRIBE_TRUCE": "a Tribe you have a Truce with",
    "SUBJECT_TRIBE_PEACE": "a Tribe you are at Peace with",
    "SUBJECT_TRIBE_ALLIANCE": "your allied Tribe",
    "SUBJECT_TRIBE_CAN_ALLIANCE": "a Tribe able to form an Alliance (you have no tribal ally, it has no ally)",
    "SUBJECT_TRIBE_NO_ALLIANCE_TEAM": "a Tribe not allied with your team",
}
SUBJECT_REQ_LABEL = {
    # aeSubjectTargetEnabled / aeSubjectCharacterEnabled
    "SUBJECT_PLAYER_MIN_PLEASED": "Their opinion of you is at least Pleased (+100)",
    "SUBJECT_PLAYER_MIN_CAUTIOUS": "Their opinion of you is at least Cautious (0)",
    "SUBJECT_PLAYER_PEACE_FRIENDLY": "At Peace with them and their opinion of you is Friendly (+200)",
    "SUBJECT_PLAYER_NOT_MIN_CONFLICT_TURNS":
        "At least 5 turns since your last war/peace change with them (Min Treaty Turns)",
    "SUBJECT_TRIBE_MIN_PLEASED": "The Tribe's opinion of you is at least Pleased (+100)",
    "SUBJECT_TRIBE_NOT_MIN_CONFLICT_TURNS":
        "At least 5 turns since your last war/peace change with the Tribe (Min Treaty Turns)",
    "SUBJECT_TRIBE_PEACE": "At Peace with the Tribe",
    "SUBJECT_PLAYER_NO_ALLIANCE": "They are not in an Alliance",
    "SUBJECT_TRIBE_NO_ALLIANCE_TEAM": "The Tribe is not allied with your team",
    "SUBJECT_PLAYER_SCHEMER": "Your leader is a Schemer",
}
SUBJECT_BLOCK_LABEL = {
    # aeSubjectTargetDisabled / aeSubjectCharacterDisabled
    "SUBJECT_PLAYER_DEMANDED_TRIBUTE": "You already demanded Tribute from them recently",
    "SUBJECT_LEADER_ALLIANCE": "That leader is already in an Alliance",
}
RELATION_REQ_LABEL = {
    # aeSubjectRelationOn / aeSubjectRelationEnabled
    "SUBJECTRELATION_CAN_END_WAR": "The war can be ended (not locked in by an Alliance)",
    "SUBJECTRELATION_PLAYER_PEACE_OR_TRUCE": "They are at Peace or Truce with you (not at War)",
    "SUBJECTRELATION_TRIBE_PEACE_OR_TRUCE": "The Tribe is at Peace or Truce with them",
    "SUBJECTRELATION_TRIBE_NO_ALLIANCE_TEAM": "The Tribe is not their ally",
    "SUBJECTRELATION_PLAYER_NO_ALLIANCE": "They are not allied with the target",
    "SUBJECTRELATION_MIN_CONFLICT_TURNS":
        "At least 5 turns since the last war/peace change between the two (Min Treaty Turns)",
}
RELATION_BLOCK_LABEL = {
    # aeSubjectRelationDisabled
    "SUBJECTRELATION_TRIBE_WAR_ALLIANCE": "The Tribe is at War alongside its ally",
    "SUBJECTRELATION_PLAYER_MIN_PLEASED": "Their opinion of the target is already Pleased or better",
}
PERFORMER_LABEL = {
    "SUBJECT_AMBASSADOR": "Ambassador (council seat)",
    "SUBJECT_LEADER_DIPLOMAT": "Your leader, Diplomat archetype",
    "SUBJECT_LEADER_US": "Your leader",
    "SUBJECT_CHARACTER_US": "Any of your characters",
    "SUBJECT_LEADER_PEACE_OR_TRUCE": "Another Nation's leader (at Peace or Truce with you)",
    "SUBJECT_LEADER_TRIBE_PEACE_OR_TRUCE": "A Tribe's leader (Tribe at Peace or Truce with you)",
}

# The player-facing diplomacy actions, in display order. Variants list the
# AI/MP/no-characters plumbing entries folded into each (counted, not shown).
ACTION_GROUPS = [
    {
        "id": "nations",
        "label": "With Nations",
        "blurb": ("Changing your diplomatic state with another Nation. Truce "
                  "and Peace offers are run by your Ambassador; Alliances "
                  "need a Diplomat leader."),
        "actions": [
            {"id": "MISSION_PLAYER_DECLARE_WAR", "name": "Declare War",
             "variants": ["MISSION_PLAYER_DECLARE_WAR_HUMAN"],
             "summary": "Truce → War. No cost — war only needs the treaty-turn gate."},
            {"id": "MISSION_PLAYER_TRUCE", "name": "Negotiate Truce",
             "variants": ["MISSION_PLAYER_TRUCE_HUMAN", "MISSION_PLAYER_TRUCE_NO_CHARACTERS"],
             "summary": ("War → Truce. Opens negotiation with three options "
                         "(below); diplomacy with the target is blocked while "
                         "the mission runs."),
             "options": [
                 {"id": "MISSION_PLAYER_TRUCE_OFFER_TRIBUTE", "name": "Offer Tribute for Truce",
                  "summary": "Sweeten the deal — you pay them Tribute for 40 turns."},
                 {"id": "MISSION_PLAYER_TRUCE_NO_TRIBUTE", "name": "Ask for Truce",
                  "summary": "A plain white peace offer."},
                 {"id": "MISSION_PLAYER_TRUCE_DEMAND_TRIBUTE", "name": "Demand Tribute for Truce",
                  "summary": "Press your advantage — they pay you Tribute for 40 turns."},
             ]},
            {"id": "MISSION_PLAYER_PEACE", "name": "Make Peace",
             "variants": ["MISSION_PLAYER_PEACE_HUMAN", "MISSION_PLAYER_PEACE_NO_CHARACTERS"],
             "summary": "Truce → Peace. Needs them at least Pleased with you."},
            {"id": "MISSION_PLAYER_BREAK_PEACE", "name": "Break Peace",
             "variants": ["MISSION_PLAYER_BREAK_PEACE_HUMAN"],
             "summary": "Peace → Truce. The step back down before any new war."},
            {"id": "MISSION_TEAM_ALLIANCE", "name": "National Alliance",
             "variants": ["MISSION_TEAM_ALLIANCE_HUMAN"],
             "summary": ("Allied Nations share visibility and join each "
                         "other's defensive wars; you can move and attack "
                         "with allied units. One Alliance per Nation.")},
            {"id": "MISSION_PLAYER_END_ALLIANCE", "name": "End Alliance",
             "variants": ["MISSION_PLAYER_END_ALLIANCE_HUMAN"],
             "summary": "Dissolve your National Alliance."},
            {"id": "MISSION_PLAYER_CANCEL_TRADE", "name": "Cancel All Trade",
             "variants": [],
             "summary": "End all trade routes with a trading partner."},
            {"id": "MISSION_DEMAND_TRIBUTE", "name": "Demand Tribute",
             "variants": ["MISSION_DEMAND_TRIBUTE_ANY"],
             "summary": ("Demand a Tribute payment (lasts 40 turns) from a "
                         "Nation you are not at war with. Refusal can mean "
                         "war; one demand at a time.")},
        ],
    },
    {
        "id": "tribes",
        "label": "With Tribes",
        "blurb": ("The same ladder against the barbarian Tribes — but tribal "
                  "diplomacy is paid in Training, not Civics."),
        "actions": [
            {"id": "MISSION_TRIBE_DECLARE_WAR", "name": "Declare War (Tribe)",
             "variants": [],
             "summary": "Truce → War with a Tribe."},
            {"id": "MISSION_TRIBE_TRUCE", "name": "Tribal Truce",
             "variants": ["MISSION_TRIBE_TRUCE_NO_CHARACTERS"],
             "summary": "War → Truce with a Tribe."},
            {"id": "MISSION_TRIBE_PEACE", "name": "Tribal Peace",
             "variants": ["MISSION_TRIBE_PEACE_NO_CHARACTERS"],
             "summary": ("Truce → Peace. The Tribe stops targeting your "
                         "cities with raiders and can heal in your territory.")},
            {"id": "MISSION_TRIBE_ALLIANCE", "name": "Tribal Alliance",
             "variants": [],
             "summary": ("Move and attack with the Tribe's units, and settle "
                         "near their sites without the ×2 Money surcharge. "
                         "One tribal ally at a time; Diplomat leaders only.")},
            {"id": "MISSION_TRIBE_BREAK_PEACE", "name": "Break Peace (Tribe)",
             "variants": [],
             "summary": "Peace → Truce with a Tribe."},
            {"id": "MISSION_TRIBE_END_ALLIANCE", "name": "End Alliance (Tribe)",
             "variants": ["MISSION_TRIBE_END_ALLIANCE_NO_CHARACTERS"],
             "summary": "Dissolve your Tribal Alliance."},
        ],
    },
    {
        "id": "third-party",
        "label": "Third-party Wars",
        "blurb": ("Paying other powers to fight your battles. These target "
                  "the other ruler directly rather than your own council."),
        "actions": [
            {"id": "MISSION_PLAYER_PLAYER_WAR", "name": "Ask a Nation to Declare War",
             "variants": [],
             "summary": ("Schemer leaders only: pay another ruler to declare "
                         "War on a third Nation.")},
            {"id": "MISSION_PLAYER_JOIN_PLAYER_WAR", "name": "Ask a Nation to Join Your War",
             "variants": [],
             "summary": "Bring another Nation into a war you are already fighting."},
            {"id": "MISSION_PLAYER_TRIBE_WAR", "name": "Ask a Nation to Attack a Tribe",
             "variants": [],
             "summary": "Pay another ruler to declare War on a Tribe."},
            {"id": "MISSION_TRIBE_PLAYER_WAR", "name": "Ask a Tribe to Attack a Nation",
             "variants": [],
             "summary": "Pay a friendly Tribe to declare War on a Nation."},
        ],
    },
]


def build_actions(missions: dict[str, ET.Element], text: dict[str, str],
                  indexes: dict) -> tuple[list[dict], int]:
    diplo_names = {
        "DIPLOMACY_WAR": "War", "DIPLOMACY_TRUCE": "Truce",
        "DIPLOMACY_PEACE": "Peace", "DIPLOMACY_TEAM": "Team",
    }

    def costs(m: ET.Element, tag: str) -> list[dict]:
        out = []
        for pair in m.findall(f"{tag}/Pair"):
            y = (pair.findtext("zIndex") or "").replace("YIELD_", "")
            v = int(pair.findtext("iValue") or "0")
            out.append({"yield": y.lower(), "label": y.title(), "value": v})
        return out

    def subjects(m: ET.Element, tag: str) -> list[str]:
        return [v.text for v in m.findall(f"{tag}/zValue") if v.text]

    def build_one(spec: dict) -> dict:
        mid = spec["id"]
        m = missions.get(mid)
        if m is None:
            raise SystemExit(f"build_diplomacy: mission {mid} not found in mission.xml")

        requirements: list[str] = []
        blocked: list[str] = []

        if gi(m, "bRequireContact") == 1:
            requirements.append("Contact with the target")
        tech = m.findtext("TechPrereq")
        if tech:
            tech_label = text.get(f"TEXT_{tech}",
                                  tech.replace("TECH_", "").replace("_", " ").title())
            requirements.append(f"Requires {tech_label} technology")

        target = m.findtext("SubjectTarget") or ""
        # aeSubjectPlayerOn (e.g. Schemer leader for Ask-to-Declare-War)
        for s in subjects(m, "aeSubjectPlayerOn"):
            requirements.append(SUBJECT_REQ_LABEL.get(s, s))
        for tag in ("aeSubjectTargetEnabled", "aeSubjectCharacterEnabled"):
            for s in subjects(m, tag):
                requirements.append(SUBJECT_REQ_LABEL.get(s, s))
        for tag in ("aeSubjectRelationOn", "aeSubjectRelationEnabled"):
            for s in subjects(m, tag):
                requirements.append(RELATION_REQ_LABEL.get(s, s))
        for tag in ("aeSubjectTargetDisabled", "aeSubjectCharacterDisabled"):
            for s in subjects(m, tag):
                blocked.append(SUBJECT_BLOCK_LABEL.get(s, s))
        for s in subjects(m, "aeSubjectRelationDisabled"):
            blocked.append(RELATION_BLOCK_LABEL.get(s, s))

        # Character XP bonus on completion (BONUS_XP_CHARACTER_SMALL etc.) —
        # rendered through the shared humanizer; iXPCharacter isn't covered
        # by render_bonus yet, so fall back to reading it directly.
        effects: list[str] = []
        bonus_id = m.findtext("SubjectCharacterBonus")
        if bonus_id:
            bonus_entry = indexes.get("bonus.xml", {}).get(bonus_id)
            if bonus_entry is not None:
                rendered = render_bonus(bonus_entry, indexes)
                if not rendered and gi(bonus_entry, "iXPCharacter"):
                    rendered = [f"+{gi(bonus_entry, 'iXPCharacter')} XP"]
                effects.extend(f"Envoy gains {r.lstrip('+').strip()}" if r.endswith("XP")
                               else f"Envoy: {r}" for r in rendered)

        performer = m.findtext("SubjectCharacter") or ""
        diplo = m.findtext("Diplomacy") or ""
        turns = gi(m, "iMissionTurns")
        return {
            "id": mid,
            "slug": mid.replace("MISSION_", "").lower().replace("_", "-"),
            "name": spec["name"],
            "gameName": text.get(m.findtext("Name") or "", spec["name"]),
            "summary": spec["summary"],
            "performer": PERFORMER_LABEL.get(performer, None) if performer else None,
            "target": SUBJECT_TARGET_LABEL.get(target, None) if target else None,
            "resultState": diplo_names.get(diplo) if diplo else None,
            "turns": turns or None,
            "blocksDiplomacy": gi(m, "bBlockDiplomacy") == 1,
            "costs": costs(m, "aiYieldCost"),
            "costsOpinion": costs(m, "aiYieldCostOpinion"),
            "requirements": requirements,
            "blocked": blocked,
            "effects": effects,
            "options": [build_one(o) for o in spec.get("options", [])],
            "variantCount": len(spec.get("variants", [])),
        }

    groups = []
    n_actions = 0
    for g in ACTION_GROUPS:
        actions = [build_one(spec) for spec in g["actions"]]
        n_actions += len(actions) + sum(len(a["options"]) for a in actions)
        groups.append({
            "id": g["id"], "label": g["label"], "blurb": g["blurb"],
            "actions": actions,
        })
    return groups, n_actions


# ── Constants ────────────────────────────────────────────────────────────────

CONSTANT_SPECS = [
    ("MIN_TREATY_TURNS", "Min Treaty Turns",
     "Turns you must wait after any war/peace change with a power before "
     "declaring war on them again (also no declarations this early in the game)."),
    ("TRIBUTE_TURNS", "Tribute Duration",
     "How many turns a Tribute payment (offered or demanded) keeps flowing."),
    ("TRIBUTE_OPINION_PLAYER", "Tribute Opinion",
     "Opinion bonus with a Nation while you are paying them Tribute."),
    ("FOUND_CITY_TRIBE_COST_BASE", "Tribal Site Cost (base Money)",
     "Money cost to found a city on a tribe-claimed site (+ the per-purchase "
     "increase below; modified by the Tribe's opinion of you)."),
    ("FOUND_CITY_TRIBE_COST_PER", "Tribal Site Cost (per prior purchase)",
     "Added to the base cost for every tribal site your team has already bought."),
    ("NON_TRIBAL_ALLIANCE_SETTLE_COST_MULTIPLIER", "Non-ally Settle Multiplier (%)",
     "The tribal-site cost is multiplied by this (×2) when the Tribe is "
     "not your ally."),
]


def build_constants() -> list[dict]:
    vals = {}
    for e in parse("globalsInt.xml").findall("Entry"):
        z = e.findtext("zType")
        if z:
            vals[z] = gi(e, "iValue")
    out = []
    for key, label, note in CONSTANT_SPECS:
        if key in vals:
            out.append({"id": key, "label": label, "value": vals[key], "note": note})
    return out


def main() -> int:
    # Fill the int(TOKEN) substitution table before any text is cleaned.
    for e in parse("globalsInt.xml").findall("Entry"):
        z = e.findtext("zType")
        if z:
            _GLOBALS_INT[z] = gi(e, "iValue")

    text = load_text("text-infos.xml", "text-helptext.xml", "text-helptext-sap.xml",
                     "text-mission.xml", "text-tech.xml")
    missions = index("mission.xml")
    indexes = load_xml_indexes(XML_DIR)

    states = build_states(text)
    war_states = build_war_states(text)
    action_groups, n_actions = build_actions(missions, text, indexes)
    constants = build_constants()
    n_variants = sum(a["variantCount"] for g in action_groups for a in g["actions"])

    data = {
        "states": states,
        "warStates": war_states,
        "warScore": WAR_SCORE,
        "actionGroups": action_groups,
        "constants": constants,
        "counts": {
            "states": len(states),
            "warStates": len(war_states),
            "actions": n_actions,
            "variants": n_variants,
            "constants": len(constants),
        },
    }

    OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(states)} states, "
          f"{len(war_states)} war states, {n_actions} actions "
          f"(+{n_variants} internal variants), {len(constants)} constants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
