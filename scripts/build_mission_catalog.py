#!/usr/bin/env python3
"""
Build src/data/mission-catalog.json — the FULL catalog of every mission
in the game (114), for the /missions reference tab.

Distinct from build_missions.py, which emits the deep dice-outcome
breakdown for just three missions (Rally / Hold Court / Steal Research)
and feeds their dedicated pages. We deliberately don't touch that file.

Per mission we surface what a player reference needs:
  - name (text-mission*.xml, link-templates stripped)
  - who performs it (SubjectCharacter → readable role)
  - cost (aiYieldCost — direct; aiYieldCostOpinion — paid in opinion/money)
  - time (iMissionTurns, +scaled flag) and cooldown
  - requirements: tech prereq, DLC, required diplomacy state, game-option
  - outcome names (from missionResult*.xml) + count
  - a functional category (curated — the XML's 2-value Class is too coarse)
  - an `internal` flag for the AI/UI plumbing variants
    (_HUMAN / _NO_CHARACTERS / _ANY / war-resolution) so the page can
    fold them away by default.

Game stores yields ×10 for display, except Orders which are 1:1.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import _strip_link_templates  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "mission-catalog.json"

# ── "Who performs it" — SubjectCharacter has no clean game text for the
# bare roles, so we curate readable labels. Council/agent roles that DO
# resolve via text-subject.xml link() templates are handled dynamically;
# this map is the fallback + the proper-noun leader abilities.
WHO_LABELS = {
    "SUBJECT_LEADER_US": "Leader",
    "SUBJECT_LEADER": "Leader",
    "SUBJECT_LEADER_OR_DESCENDANT": "Leader or descendant",
    "SUBJECT_LEADER_DIPLOMAT": "Leader (Diplomat)",
    "SUBJECT_LEADER_JUDGE": "Leader (Judge)",
    "SUBJECT_LEADER_SCHOLAR": "Leader (Scholar)",
    "SUBJECT_LEADER_SCHEMER": "Leader (Schemer)",
    "SUBJECT_LEADER_PEACE_OR_TRUCE": "Leader",
    "SUBJECT_LEADER_TRIBE_PEACE_OR_TRUCE": "Leader",
    "SUBJECT_NON_LEADER_US": "Any non-leader character",
    "SUBJECT_CHARACTER_US": "Any character",
    "SUBJECT_CAN_MARRY": "Any marriageable character",
    "SUBJECT_AGENT": "Agent",
    "SUBJECT_ENVOY": "Envoy",
    "SUBJECT_COURTIER": "Courtier",
    "SUBJECT_COUNCIL": "Council member",
    "SUBJECT_DICTATOR": "Dictator",
    "SUBJECT_TUTOR_US": "Tutor",
    "SUBJECT_RELIGION_HEAD_US": "Religion head",
    "SUBJECT_FAMILY_HEAD_US": "Family head",
    "SUBJECT_BASTARD": "Bastard",
    "SUBJECT_FUGITIVE": "Fugitive",
    "SUBJECT_IMPRISONED": "Imprisoned character",
    "SUBJECT_CAPTURED": "Captured character",
    "SUBJECT_INFECTED": "Infected character",
    "SUBJECT_CLERGY_PAGAN": "Pagan clergy",
    "SUBJECT_CLERGY_ZOROASTRIAN": "Zoroastrian clergy",
    "SUBJECT_CLERGY_JEWISH": "Jewish clergy",
    "SUBJECT_CLERGY_CHRISTIAN": "Christian clergy",
    "SUBJECT_CLERGY_MANICAHEAN": "Manichaean clergy",
    "SUBJECT_CLERGY_HINDUISM": "Hindu clergy",
    "SUBJECT_CLERGY_BUDDHISM": "Buddhist clergy",
    "SUBJECT_CHARACTER_STEWARD_OF_THE_LAND_ADULT": "Steward of the Land",
    # Proper-noun leader / DLC unique abilities
    "SUBJECT_CHARACTER_MENTUHOTEP_II": "Mentuhotep II",
    "SUBJECT_CHARACTER_HANNO_II": "Hanno II",
    "SUBJECT_LEADER_HANNO_NAVIGATOR": "Hanno the Navigator",
    "SUBJECT_CHARACTER_BARDIYA_GAUMATA": "Bardiya / Gaumata",
    "SUBJECT_CHARACTER_STATEIRA_LEADER": "Stateira",
    "SUBJECT_OLYMPIAS_ALEXANDER": "Olympias",
    "SUBJECT_CHARACTER_PTOLEMY": "Ptolemy",
    "SUBJECT_CHARACTER_GUDIT": "Gudit",
    "SUBJECT_LEADER_HAMMURABI": "Hammurabi",
    "SUBJECT_LEADER_SHAMMURAMAT_HERO": "Shammuramat",
    "SUBJECT_LEADER_SHAMMURAMAT_BUILDER": "Shammuramat",
    "SUBJECT_AUGUSTUS_DYNASTY_LEADER_US": "Augustus dynasty leader",
}

# ── Performer grouping. The reference is organized by WHO can run the
# mission (the SubjectCharacter role), not by what it does. Proper-noun /
# dynasty-specific scripted powers are pulled out into their own bucket
# at the end so they don't clutter the general roles.
PERFORMER_ORDER = [
    "Leader",
    "Ambassador",
    "Chancellor",
    "Spymaster",
    "Agent",
    "Family Head",
    "Religious Head & Clergy",
    "Any Character",
    "Situational",
    "Unique Leader Powers",
    "Other",
]

PERFORMER_BLURB = {
    "Leader": "Run by the ruler (incl. Diplomat/Judge/Scholar/Schemer leader variants and the Dictator).",
    "Ambassador": "Your council Ambassador — diplomacy, synods, trade.",
    "Chancellor": "Your council Chancellor.",
    "Spymaster": "Your council Spymaster — the espionage network.",
    "Agent": "Spy network Agents operating in the field.",
    "Family Head": "The head of a family (matters under Oligarchy).",
    "Religious Head & Clergy": "The religion head or its clergy, by faith.",
    "Any Character": "Any eligible courtier — non-leaders, tutors, envoys, marriageable characters.",
    "Situational": "Characters in a particular state — imprisoned, captured, fugitive, bastard, infected.",
    "Unique Leader Powers": "Scripted abilities tied to specific named leaders / dynasties (DLC).",
    "Other": "Uncategorized.",
}


# Subject-noun → Leader Powers (unique scripted abilities). Anything whose
# SubjectCharacter is a proper-noun leader falls here unless already mapped.
LEADER_POWER_SUBJECTS = {
    "SUBJECT_CHARACTER_MENTUHOTEP_II", "SUBJECT_CHARACTER_HANNO_II",
    "SUBJECT_LEADER_HANNO_NAVIGATOR", "SUBJECT_CHARACTER_BARDIYA_GAUMATA",
    "SUBJECT_CHARACTER_STATEIRA_LEADER", "SUBJECT_OLYMPIAS_ALEXANDER",
    "SUBJECT_CHARACTER_PTOLEMY", "SUBJECT_CHARACTER_GUDIT",
    "SUBJECT_LEADER_HAMMURABI", "SUBJECT_LEADER_SHAMMURAMAT_HERO",
    "SUBJECT_LEADER_SHAMMURAMAT_BUILDER", "SUBJECT_AUGUSTUS_DYNASTY_LEADER_US",
}
LEADER_POWER_IDS = {
    "MISSION_LEGENDARY_FOUNDER_TO_HERO", "MISSION_REAL_HERO_TO_BUILDER",
    "MISSION_COURT_OF_THE_DIVINE_KING", "MISSION_LAND_GRANTS_HANNO_II",
    "MISSION_TRIBE_ALLIANCE_HANNO_NAVIGATOR", "MISSION_FAMILY_GIFT_MENTUHOTEP_II",
    "MISSION_PACIFY_CITY_MENTUHOTEP_II", "MISSION_IMPRISON_MENTUHOTEP_II",
    "MISSION_BOOST_LEGITIMACY_BARDIYA", "MISSION_SPAWN_MILITIA_STATEIRA",
}

# Internal / plumbing variants — same mechanic, different actor context.
INTERNAL_SUFFIXES = ("_HUMAN", "_NO_CHARACTERS", "_NO_CHARACTER", "_ANY",
                     "_OFFER_TRIBUTE", "_NO_TRIBUTE", "_DEMAND_TRIBUTE")
INTERNAL_EXACT = {
    "MISSION_TRIBE_PLAYER_WAR", "MISSION_PLAYER_TRIBE_WAR",
    "MISSION_PLAYER_PLAYER_WAR", "MISSION_PLAYER_JOIN_PLAYER_WAR",
    "MISSION_PLAYER_DECLARE_WAR", "MISSION_PLAYER_BREAK_PEACE",
    "MISSION_PLAYER_END_ALLIANCE", "MISSION_PLAYER_CANCEL_TRADE",
    "MISSION_TRIBE_DECLARE_WAR", "MISSION_TRIBE_BREAK_PEACE",
}

DLC_LABELS = {
    "AKSUM": "Aksum",
    "CALAMITIES": "Calamities",
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus",
    "EVENTPACK_RELIGION": "Religion Event Pack",
    "EVENTPACK_SCANDAL": "Scandal Event Pack",
    "WONDERS_DYNASTIES": "Wonders & Dynasties",
    "BEHIND_THE_THRONE": "Behind the Throne",
    "SACRED_AND_PROFANE": "Sacred & Profane",
}


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
    p = XML_DIR / name
    if not p.exists():
        return {}
    return {e.findtext("zType"): e for e in ET.parse(p).getroot().findall("Entry") if e.findtext("zType")}


_ROMAN = re.compile(r"^(?=[IVXLC]+$)(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3})$", re.I)


def humanize_const(token: str, prefix: str) -> str:
    if not token:
        return ""
    words = token.replace(prefix, "").replace("_", " ").title().split()
    return " ".join(w.upper() if _ROMAN.match(w) else w for w in words)


_ANY_CHARACTER_SUBJECTS = {
    "SUBJECT_CHARACTER_US", "SUBJECT_NON_LEADER_US", "SUBJECT_COURTIER",
    "SUBJECT_TUTOR_US", "SUBJECT_ENVOY", "SUBJECT_COUNCIL", "SUBJECT_CAN_MARRY",
}
_SITUATIONAL_SUBJECTS = {
    "SUBJECT_IMPRISONED", "SUBJECT_CAPTURED", "SUBJECT_FUGITIVE",
    "SUBJECT_BASTARD", "SUBJECT_INFECTED",
    "SUBJECT_CHARACTER_STEWARD_OF_THE_LAND_ADULT",
}


def performer(mid: str, subject: str, internal: bool) -> str:
    """Bucket a mission by WHO can run it."""
    # Dynasty / proper-noun scripted powers go to their own section.
    if mid in LEADER_POWER_IDS or subject in LEADER_POWER_SUBJECTS:
        return "Unique Leader Powers"
    if subject == "SUBJECT_AMBASSADOR":
        return "Ambassador"
    if subject == "SUBJECT_CHANCELLOR":
        return "Chancellor"
    if subject == "SUBJECT_SPYMASTER":
        return "Spymaster"
    if subject == "SUBJECT_AGENT":
        return "Agent"
    if subject == "SUBJECT_FAMILY_HEAD_US":
        return "Family Head"
    if subject == "SUBJECT_RELIGION_HEAD_US" or subject.startswith("SUBJECT_CLERGY"):
        return "Religious Head & Clergy"
    # Dictator is the ruler under a tyrannical government → Leader.
    if subject == "SUBJECT_DICTATOR" or subject.startswith("SUBJECT_LEADER"):
        return "Leader"
    if subject in _ANY_CHARACTER_SUBJECTS:
        return "Any Character"
    if subject in _SITUATIONAL_SUBJECTS:
        return "Situational"
    # No SubjectCharacter: AI/UI diplomacy plumbing if internal, otherwise
    # a player/leader-level decision (e.g. Adopt/Leave Religion).
    if not subject:
        return "Other" if internal else "Leader"
    return "Other"


def is_internal(mid: str) -> bool:
    if mid in INTERNAL_EXACT:
        return True
    return any(mid.endswith(sfx) for sfx in INTERNAL_SUFFIXES)


def main() -> int:
    text = load_text(
        "text-mission.xml", "text-mission-btt.xml", "text-mission-sap.xml",
        "text-mission-wog.xml", "text-missionResult.xml", "text-missionResult-btt.xml",
        "text-missionResult-sap.xml", "text-missionResult-wog.xml", "text-subject.xml",
        "text-subject-sap.xml", "text-infos.xml", "text-tech.xml",
        "text-trait.xml",
    )
    missions = index("mission.xml")
    results = index("missionResult.xml") | index("missionResult-btt.xml") \
        | index("missionResult-sap.xml") | index("missionResult-wog.xml")
    subjects = index("subject.xml")
    traits = index("trait.xml")

    def role_req(subject: str) -> dict | None:
        """The role/archetype a character must be to run this — e.g.
        SUBJECT_LEADER_JUDGE requires the Judge archetype trait."""
        s = subjects.get(subject)
        if s is None:
            return None
        tp = s.findtext("TraitPrereq")
        if tp:
            tr = traits.get(tp)
            label = text.get(f"TEXT_{tp}", humanize_const(tp, "TRAIT_").replace(" Archetype", ""))
            spr = (tr.findtext("zIconName") if tr is not None else "") or ""
            # zIconName routes the same way extract_art.py does:
            #   TRAIT_JUDGE        → icons/traits/judge.png
            #   RELIGION_CHRISTIAN → icons/religions/christianity.png
            icon = None
            if spr.startswith("TRAIT_"):
                icon = f"icons/traits/{spr[len('TRAIT_'):].lower()}"
            elif spr.startswith("RELIGION_"):
                icon = f"icons/religions/{spr[len('RELIGION_'):].lower()}"
            kind = "faith" if (spr.startswith("RELIGION_")) else "archetype"
            return {"kind": kind, "label": label, "icon": icon}
        cp = s.findtext("CouncilPrereq")
        if cp:
            return {"kind": "council",
                    "label": humanize_const(cp, "COUNCIL_"), "icon": None}
        return None

    def who_label(subject: str) -> str:
        if not subject:
            return "—"
        if subject in WHO_LABELS:
            return WHO_LABELS[subject]
        # Council/agent roles resolve through text-subject.xml link() form
        t = text.get(f"TEXT_{subject}")
        if t:
            return t.strip()
        s = subjects.get(subject)
        if s is not None:
            cp = s.findtext("CouncilPrereq")
            if cp:
                return humanize_const(cp, "COUNCIL_")
        return humanize_const(subject, "SUBJECT_")

    out: list[dict] = []
    for mid, m in missions.items():
        if not mid.startswith("MISSION_"):
            continue

        name = text.get(m.findtext("Name") or "",
                         humanize_const(mid, "MISSION_"))
        desc = text.get(m.findtext("Description") or "", "")
        subject = m.findtext("SubjectCharacter") or ""
        target = m.findtext("SubjectTarget") or ""

        # Mission costs are STOCKPILE costs, stored 1:1 — not the ×10
        # rate-yield encoding used for per-turn nation bonuses. Hold Court
        # really costs 100 Training; Rally Troops 100 Civics. Display raw.
        def costs(tag: str) -> list[dict]:
            o = []
            for pair in m.findall(f"{tag}/Pair"):
                y = (pair.findtext("zIndex") or "").replace("YIELD_", "")
                v = int(pair.findtext("iValue") or "0")
                o.append({"yield": y.lower(), "label": y.title(), "value": v})
            return o

        tech = m.findtext("TechPrereq")
        dlc = m.findtext("GameContentRequired")
        diplo = m.findtext("Diplomacy")
        game_opt = m.findtext("GameOptionPrereq")

        # Outcomes
        outcome_names = []
        for p in m.findall("aiResultDie/Pair"):
            rid = p.findtext("zIndex") or ""
            r = results.get(rid)
            nm = text.get(
                (r.findtext("Name") if r is not None else "") or "",
                humanize_const(rid, "MISSIONRESULT_"),
            )
            outcome_names.append(nm)

        internal = is_internal(mid)
        out.append({
            "id": mid,
            "slug": mid.replace("MISSION_", "").lower().replace("_", "-"),
            "name": name,
            "description": desc,
            "performer": performer(mid, subject, internal),
            "who": who_label(subject),
            "whoId": subject,
            "roleReq": role_req(subject),
            "target": humanize_const(target, "SUBJECT_") if target else "",
            "cost": costs("aiYieldCost"),
            "opinionCost": costs("aiYieldCostOpinion"),
            "turns": int(m.findtext("iMissionTurns") or "0"),
            "turnsScaled": m.findtext("iMissionTurnsScaled") == "1",
            "cooldown": int(m.findtext("iCooldown") or "0"),
            "techPrereq": (
                {"id": tech, "label": text.get(f"TEXT_{tech}", humanize_const(tech, "TECH_")),
                 "slug": tech.replace("TECH_", "").lower().replace("_", "-")}
                if tech else None
            ),
            "dlc": DLC_LABELS.get(dlc, dlc.replace("_", " ").title()) if dlc else None,
            "diplomacy": humanize_const(diplo, "DIPLOMACY_") if diplo else None,
            "gameOption": humanize_const(game_opt, "GAMEOPTION_") if game_opt else None,
            "encyclopedia": m.findtext("bEncyclopedia") == "1",
            "internal": internal,
            "outcomes": outcome_names,
            "outcomeCount": len(outcome_names),
        })

    out.sort(key=lambda x: (PERFORMER_ORDER.index(x["performer"]), x["name"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    by_cat: dict[str, int] = {}
    internal_n = 0
    for mm in out:
        by_cat[mm["performer"]] = by_cat.get(mm["performer"], 0) + 1
        internal_n += 1 if mm["internal"] else 0
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(out)} missions ({internal_n} internal)")
    for c in PERFORMER_ORDER:
        if by_cat.get(c):
            print(f"  · {c:26} {by_cat[c]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
