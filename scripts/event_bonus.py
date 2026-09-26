#!/usr/bin/env python3
"""Event-bonus lines the reward humanizer (build_missions.humanize_bonus) did
not cover: occurrences, nationwide state changes, and effects aimed at one of
the event's subjects.

Why this exists. An event's own aeBonuses fire the moment it opens, one bonus
per subject slot, before the player sees the options
(PlayerEvent.doEventStory, PlayerEvent.cs:13818), and an option's aeBonuses do
the same per slot once it is picked. The game prints them in the event popup
through HelpText.buildBonusHelpRolePlaying (HelpText.Bonus.cs:15), a renderer
the helptext registry extraction never enumerated, so the occurrence starts and
ends ("Starts Era of Peace", "Ends Civil War") and several other lines were
silently dropped from every event card on the site.

Phrasing follows the game's own TEXT templates (recorded per field in
scripts/data/helptext_registry.json). A bonus that targets "subject N" is
resolved against the event's subject list, so "Seizes the Throne of +0"
becomes "Seizes the throne of you".

Each line is a reward dict: {"text", "kind"?, "href"?, "tip"?, "tipTitle"?}.
kind = "occurrence" or "nationwide" marks the lines that change the whole
nation (the card highlights them and adds a badge); plain lines have no kind.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OCC_JSON = ROOT / "src" / "data" / "occurrences.json"

_ICON_RE = re.compile(r"\{?icon\([A-Z0-9_]+(?:,\d+)?\)\}?")
_LINK_RE = re.compile(r"\{?(?:lowercase:)?link\(([A-Z0-9_]+)(?:,\d+)?\)\}?")


def _tok(token: str, prefix: str) -> str:
    return token.replace(prefix, "", 1).replace("_", " ").title()


_NAME_KEYS: dict[str, str] | None = None


def name_key(token: str) -> str:
    """zType → its Name/Text/GenderedName TEXT key, across every Infos file
    (memories name themselves through Text, most entries through Name)."""
    global _NAME_KEYS
    if _NAME_KEYS is None:
        _NAME_KEYS = {}
        for p in sorted(XML_DIR.glob("*.xml")):
            if p.name.startswith("text"):
                continue
            try:
                root = ET.parse(p).getroot()
            except ET.ParseError:
                continue
            for e in root.findall("Entry"):
                z = e.findtext("zType")
                if not z or z in _NAME_KEYS:
                    continue
                k = e.findtext("Name") or e.findtext("Text") or e.findtext("aeTitles/Pair/zValue") or ""
                if not k and e.findtext("GenderedName"):
                    k = (e.findtext("GenderedName") or "").replace("GENDERED_TEXT_", "TEXT_")
                if k:
                    _NAME_KEYS[z] = k
    return _NAME_KEYS.get(token, "")


_ALL_TEXT: dict[str, str] | None = None


def all_text() -> dict[str, str]:
    """Every en-US string (the callers' text maps load only the event files)."""
    global _ALL_TEXT
    if _ALL_TEXT is None:
        _ALL_TEXT = {}
        for p in sorted(XML_DIR.glob("text-*.xml")):
            for e in ET.parse(p).getroot().findall("Entry"):
                k = e.findtext("zType")
                if k and k not in _ALL_TEXT:
                    _ALL_TEXT[k] = e.findtext("en-US") or ""
    return _ALL_TEXT


@dataclass
class Ctx:
    """Where a bonus fires: the event's subjects and which slot it lands on."""
    text: dict
    subjects: list[str] = field(default_factory=list)   # SUBJECT_* ids, by index
    slot: int | None = None                              # subject index this bonus targets

    def name(self, token: str, prefix: str) -> str:
        keys = ("TEXT_" + token, name_key(token), token)
        raw = next((t.get(k) for t in (self.text, all_text()) for k in keys if k and t.get(k)), "") or ""
        raw = raw.split("~")[0]
        raw = _ICON_RE.sub("", raw)
        raw = _LINK_RE.sub(lambda m: _tok(m.group(1), m.group(1).split("_")[0] + "_"), raw).strip()
        return raw or _tok(token, prefix)

    def subj(self, k: int | str | None) -> str:
        """Phrase for subject index k of the event."""
        try:
            k = int(k)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return "the target"
        if 0 <= k < len(self.subjects):
            return subject_phrase(self.subjects[k])
        return "the target"

    def who(self) -> str:
        return self.subj(self.slot) if self.slot is not None else "the target"

    def sid(self) -> str:
        if self.slot is not None and 0 <= self.slot < len(self.subjects):
            return self.subjects[self.slot]
        return ""

    def nation(self) -> str:
        """The nation behind the slot: diplomacy acts on a player even when the
        slot holds one of its characters or cities."""
        sid = self.sid()
        cls = subject_class(sid)
        if cls in ("PLAYER", "TRIBE"):
            return self.who()
        words = sid.split("_")
        if "TRIBE" in words or "TRIBAL" in words:
            return "the tribe"
        if "US" in words and "THEM" not in words:
            return "you"
        return "the rival nation"


def says(phrase: str, verb3: str) -> str:
    """'you' + 'declares' → 'You declare'; anything else keeps the -s form."""
    if phrase == "you":
        irregular = {"has": "have", "goes": "go", "is": "are"}
        if verb3 in irregular:
            base = irregular[verb3]
        elif verb3.endswith("ies"):
            base = verb3[:-3] + "y"
        elif verb3.endswith("es") and verb3[:-2].endswith(("sh", "ch", "ss", "x", "zz")):
            base = verb3[:-2]
        else:
            base = verb3[:-1]
        return f"You {base}"
    return f"{phrase[:1].upper()}{phrase[1:]} {verb3}"


def poss(phrase: str) -> str:
    """'you' → 'your'; 'the rival nation' → "the rival nation's"."""
    return "your" if phrase == "you" else f"{phrase}'s"


_SUBJECT_CLASS: dict[str, str] | None = None


def subject_class(sid: str) -> str:
    """subject.xml Class of a SUBJECT_* token ('' when it has none)."""
    global _SUBJECT_CLASS
    if _SUBJECT_CLASS is None:
        _SUBJECT_CLASS = {}
        for p in sorted(XML_DIR.glob("subject*.xml")):
            for e in ET.parse(p).getroot().findall("Entry"):
                z = e.findtext("zType")
                if z:
                    _SUBJECT_CLASS[z] = (e.findtext("Class") or "").replace("SUBJECTCLASS_", "")
    return _SUBJECT_CLASS.get(sid, "")


# Character roles, most specific first. A subject token names its filter
# (SUBJECT_SPOUSE_OF_LEADER_US, SUBJECT_FAMILY_HEAD_US …); the role is the
# first of these words it contains.
_ROLES = (
    ("SPOUSE_OF_LEADER", "leader's spouse"), ("CHILD_OF_LEADER", "leader's child"),
    ("FAMILY_HEAD", "family head"), ("HEAD_OF_FAMILY", "family head"),
    ("RELIGION_HEAD", "religion head"), ("HEAD_OF_RELIGION", "religion head"),
    ("WAS_LEADER", "former leader"), ("LEADER", "leader"), ("HEIR", "heir"),
    ("SUCCESSION", "successor"), ("SPOUSE", "spouse"), ("SUITOR", "suitor"),
    ("CHILD", "child"), ("SIBLING", "sibling"), ("PARENT", "parent"), ("COURTIER", "courtier"),
    ("GOVERNOR", "governor"), ("GENERAL", "general"), ("AGENT", "agent"), ("TUTOR", "tutor"),
    ("MINISTER", "minister"), ("CLERGY", "cleric"), ("LOVER", "lover"), ("RIVAL", "rival"),
)
_NOUNS = {
    "FAMILY": "family", "CITY": "city", "TECH": "tech", "RELIGION": "religion", "LAW": "law",
    "TILE": "tile", "UNIT": "unit", "GOAL": "ambition", "OCCURRENCE": "occurrence",
    "RESOURCE": "resource", "TRAIT": "trait", "THEOLOGY": "theology",
}


def subject_phrase(sid: str) -> str:
    """How an event subject reads in a sentence, from its class and the role
    words in its token: SUBJECT_PLAYER_US → 'you', SUBJECT_PLAYER_THEM →
    'the rival nation', SUBJECT_HEIR_US → 'your heir', SUBJECT_TRIBE → 'the tribe'."""
    t = sid.replace("SUBJECT_", "")
    words = t.split("_")
    ours = "US" in words and "THEM" not in words
    theirs = "THEM" in words and "US" not in words
    cls = subject_class(sid)
    if cls == "PLAYER":
        return "you" if ours else "the rival nation"
    if cls == "TRIBE":
        return "the tribe"
    if cls == "CHARACTER":
        role = next((r for key, r in _ROLES if key in t), None)
        if "TRIBE" in words or "TRIBAL" in words:
            return f"the tribe's {role or 'chief'}"
        if role:
            return f"your {role}" if ours else (f"their {role}" if theirs else f"the {role}")
        if "DEAD" in words:
            return "the late character"
        return "your character" if ours else ("their character" if theirs else "the character")
    noun = _NOUNS.get(cls, "target")
    if cls == "RELIGION" and "STATE" in words:
        return "your state religion"
    if cls == "CITY" and "CAPITAL" in words:
        return "your capital" if ours else "the capital"
    return f"your {noun}" if ours else (f"their {noun}" if theirs else f"the {noun}")


# ── occurrences ────────────────────────────────────────────────────────────
_OCC: dict | None = None


def occurrence_info() -> dict:
    """occurrence id → {name, href, tip, delay}. Anchors come from the
    occurrences page's own dataset (never re-derived here)."""
    global _OCC
    if _OCC is None:
        _OCC = {}
        anchors = json.loads(OCC_JSON.read_text()).get("anchors", {}) if OCC_JSON.exists() else {}
        delays = {}
        p = XML_DIR / "occurrence.xml"
        if p.exists():
            for e in ET.parse(p).getroot().findall("Entry"):
                z = e.findtext("zType")
                if z:
                    delays[z] = int(e.findtext("iDelayTurns") or 0)
        for oid, a in anchors.items():
            _OCC[oid] = {**a, "delay": delays.get(oid, 0)}
        for oid, d in delays.items():
            _OCC.setdefault(oid, {"name": _tok(oid, "OCCURRENCE_"), "href": "", "tip": [], "delay": d})
    return _OCC


def _occ_line(verb: str, oid: str, ctx: Ctx, *, player: bool, delay_turns: int = 0) -> dict:
    info = occurrence_info().get(oid, {"name": _tok(oid, "OCCURRENCE_"), "href": "", "tip": []})
    s = f"{verb} {info['name']}"
    if player:
        # Only name who it is for when the slot is a party (a player, or one
        # of its characters/cities); an occurrence-class or unknown slot reads
        # plainly, as the game's own "{true_1: for {2_player}:}" drops it.
        cls = subject_class(ctx.sid())
        if cls in ("PLAYER", "TRIBE", "CHARACTER", "CITY", "FAMILY", "UNIT"):
            s += f" for {ctx.nation()}"
    if delay_turns:
        s += f" in {delay_turns} turn{'s' if delay_turns != 1 else ''}"
    r: dict = {"text": s, "kind": "occurrence", "occurrence": oid, "occurrenceVerb": verb.lower()}
    if info.get("href"):
        r["href"] = info["href"]
    if info.get("tip"):
        r["tip"] = info["tip"]
        r["tipTitle"] = info["name"]
    return r


def _flag(b: ET.Element, tag: str) -> bool:
    return (b.findtext(tag) or "0").strip() == "1"


def _occurrences(b: ET.Element, ctx: Ctx) -> list[dict]:
    """PlayerBonus.cs:5357-5480 (doBonus) and HelpText.Bonus.cs:380-540."""
    out: list[dict] = []
    ignore_delay = _flag(b, "bIgnoreDelayTurns")
    pending = _flag(b, "bOccurrenceSetPending")

    def delay(oid: str) -> int:
        return 0 if ignore_delay else occurrence_info().get(oid, {}).get("delay", 0)

    for tag, player in (("OccurrenceStart", False), ("OccurrenceStartPlayer", True)):
        oid = (b.findtext(tag) or "").strip()
        if oid:
            if pending:
                out.append({**_occ_line("Readies", oid, ctx, player=player), "note": "held back until a later event sets it off"})
            else:
                out.append(_occ_line("Starts", oid, ctx, player=player, delay_turns=delay(oid)))
    for tag, player in (("OccurrenceForce", False), ("OccurrenceForcePlayer", True)):
        oid = (b.findtext(tag) or "").strip()
        if oid:
            out.append(_occ_line("Starts", oid, ctx, player=player))
    for tag, player in (("OccurrenceEnd", False), ("OccurrenceEndPlayer", True)):
        oid = (b.findtext(tag) or "").strip()
        if oid:
            out.append(_occ_line("Ends", oid, ctx, player=player))
    # The event's own occurrence (passed in from its trigger/subject, not
    # named in the bonus): the forewarned calamity or the one the event is about.
    if _flag(b, "bOccurrenceStartPending"):
        out.append({"text": "The forewarned calamity strikes now", "kind": "occurrence",
                    "href": "occurrences#calamities"})
    elif _flag(b, "bOccurrenceStart") or b.find("iOccurrenceTargetSubject") is not None:
        where = b.findtext("iOccurrenceTargetSubject")
        s = "Starts this event's occurrence"
        if where not in (None, "", "-1"):
            s += f" on {ctx.subj(where)}"
        out.append({"text": s, "kind": "occurrence", "href": "occurrences"})
    elif pending and not out:
        out.append({"text": "Readies this event's occurrence", "kind": "occurrence",
                    "note": "held back until a later event sets it off"})
    return out


# ── nationwide state changes and subject-aimed effects ─────────────────────
NATIONWIDE = "nationwide"


def _dip(ctx: Ctx, tok: str) -> str:
    return ctx.name(tok, "DIPLOMACY_")


_HOSTILE: set[str] | None = None


def hostile(tok: str) -> bool:
    """diplomacy.xml bHostile (only DIPLOMACY_WAR today)."""
    global _HOSTILE
    if _HOSTILE is None:
        p = XML_DIR / "diplomacy.xml"
        _HOSTILE = {e.findtext("zType") for e in ET.parse(p).getroot().findall("Entry")
                    if e.findtext("bHostile") == "1"} if p.exists() else {"DIPLOMACY_WAR"}
    return tok in _HOSTILE


def _state(b: ET.Element, ctx: Ctx) -> list[dict]:
    out: list[dict] = []

    def add(text: str, kind: str | None = NATIONWIDE, **kw) -> None:
        r = {"text": text, **kw}
        if kind:
            r["kind"] = kind
        out.append(r)

    v = b.findtext
    # Diplomacy (templates: TEXT_HELPTEXT_BONUS_DIPLOMACY_*).
    # PlayerBonus.cs:5543-5570: "To" = the target sets its diplomacy toward
    # you, "From" = you set yours toward the target; hostile (bHostile, only
    # DIPLOMACY_WAR) reads as a declaration, anything else as a new status.
    if v("DiplomacyPlayerTo"):
        d = v("DiplomacyPlayerTo")
        add(f"{says(ctx.nation(), 'declares')} war on you" if hostile(d)
            else f"{_dip(ctx, d)} with {ctx.nation()}")
    if v("DiplomacyPlayerFrom"):
        d = v("DiplomacyPlayerFrom")
        add(f"You declare war on {ctx.nation()}" if hostile(d) else f"{_dip(ctx, d)} with {ctx.nation()}")
    if v("DiplomacyTribe"):
        d = v("DiplomacyTribe")
        add(f"{ctx.nation().capitalize()} declare war on you" if hostile(d) else f"{_dip(ctx, d)} with {ctx.nation()}")
    if v("DiplomacyAllPlayers"):
        add(f"{_dip(ctx, v('DiplomacyAllPlayers'))} with every nation")
    for tag in ("DiplomacySubjects", "DiplomacyReverse"):
        for p in b.findall(f"{tag}/Pair"):
            d, k = p.findtext("First") or "", p.findtext("Second")
            a, c = (ctx.nation(), ctx.subj(k)) if tag == "DiplomacySubjects" else (ctx.subj(k), ctx.nation())
            if a == c:
                c = "another " + c.removeprefix("the ")
            add(f"{says(a, 'goes')} to war with {c}" if hostile(d) else f"{_dip(ctx, d)} between {a} and {c}")
    if _flag(b, "bPeaceOffer"):
        add(f"{says(ctx.nation(), 'offers')} peace")
    if _flag(b, "bTruceOffer"):
        add(f"{says(ctx.nation(), 'offers')} a truce")
    if _flag(b, "bTeamAlliance") or _flag(b, "bTribeAlliance"):
        add(f"Alliance with {ctx.nation()}")
    if _flag(b, "bTeamAllianceEnd") or _flag(b, "bTribeAllianceEnd"):
        add(f"Alliance with {ctx.nation()} ends")
    if v("iAllianceSubject") not in (None, ""):
        add(f"{says(ctx.nation(), 'allies')} with {ctx.subj(v('iAllianceSubject'))}")
    if _flag(b, "bTribeInvade"):
        add(f"{ctx.nation().capitalize()} invade" if ctx.nation() == "the tribe" else f"{says(ctx.nation(), 'invades')}")
    if _flag(b, "bTribeRaid"):
        add("A tribe raids")
    if _flag(b, "bDistantRaid"):
        add("A distant tribe raids")
    if v("iAttackCitySubject") not in (None, ""):
        add(f"{says(ctx.subj(v('iAttackCitySubject')), 'prepares')} to attack {ctx.who()}")
    if _flag(b, "bCancelTrade"):
        add(f"Trade with {ctx.nation()} is cancelled")
    if _flag(b, "bCancelTribute"):
        add(f"Tribute with {ctx.nation()} is cancelled")
    if v("iContactSubject") not in (None, ""):
        add(f"Make contact with {ctx.subj(v('iContactSubject'))}", None)

    # Throne and succession.
    if v("iSeizeThroneSubject") not in (None, ""):
        add(f"{says(ctx.who(), 'seizes')} {poss(ctx.subj(v('iSeizeThroneSubject')))} throne")
    if _flag(b, "bAbdicate"):
        add(f"{says(ctx.who(), 'abdicates')} the throne")
    if v("iRegentOfSubject") not in (None, ""):
        add(f"{says(ctx.who(), 'becomes')} regent of {ctx.subj(v('iRegentOfSubject'))}")
    if _flag(b, "bChangeSuccession"):
        add("Succession law changes")

    # Religion and law at the nation level.
    if _flag(b, "bStateReligion") or _flag(b, "bAdoptReligion"):
        add("Adopts the event's religion as state religion")
    if _flag(b, "bSetFamilySupremacy"):
        add(f"{says(ctx.who(), 'gains')} family supremacy")
    if _flag(b, "bStateReligionEnd"):
        add("State religion ends")
    if v("FoundReligion"):
        add(f"Found {ctx.name(v('FoundReligion'), 'RELIGION_')}")
    if _flag(b, "bFoundReligionCity"):
        add("Found a world religion in the city")
    if _flag(b, "bFoundReligion"):
        add("Found the event's religion")
    for tag, verb in (("StartLaw", "Start law"), ("EndLaw", "End law")):
        if v(tag):
            add(f"{verb}: {ctx.name(v(tag), 'LAW_')}")
    if _flag(b, "bStartLaw"):
        add("Start the event's law")
    if _flag(b, "bEndLaw"):
        add("End the event's law")
    if v("Victory"):
        add(f"{ctx.name(v('Victory'), 'VICTORY_')} victory")

    # Cities.
    if _flag(b, "bRazeCity"):
        add("The city is razed")
    if _flag(b, "bAbandonCity"):
        add("The city is abandoned")
    if _flag(b, "bCapitalCity"):
        add("The city becomes the capital")
    return out


def _subject_aimed(b: ET.Element, ctx: Ctx) -> list[dict]:
    """Effects whose object is 'event subject N' (i*Subject indices)."""
    out: list[dict] = []
    v = b.findtext
    w = ctx.who()

    def idx(tag: str) -> str | None:
        t = v(tag)
        return t if t not in (None, "") else None

    table = (
        ("iSpreadToSubject",        lambda k: f"The religion spreads to {ctx.subj(k)}"),
        ("iRemoveFromSubject",      lambda k: f"The religion is removed from {ctx.subj(k)}"),
        # PlayerBonus.cs:6379/6470: subject k is the new head, the slot the religion/family.
        ("iHeadReligionSubject",    lambda k: f"{says(ctx.subj(k), 'becomes')} head of {w}"),
        ("iHeadFamilySubject",      lambda k: f"{says(ctx.subj(k), 'becomes')} head of {w}"),
        ("iGovernorOfSubject",      lambda k: f"{says(w, 'becomes')} governor of {ctx.subj(k)}"),
        ("iGeneralOfSubject",       lambda k: f"{says(w, 'becomes')} general of {ctx.subj(k)}"),
        ("iAgentCitySubject",       lambda k: f"{says(ctx.subj(k), 'becomes')} agent in {w}"),
        ("iExplorerOfSubject",      lambda k: f"{says(w, 'leads')} {ctx.subj(k)} as explorer"),
        ("iJoinSubject",            lambda k: f"{says(w, 'joins')} the nation of {ctx.subj(k)}"),
        ("iJoinReverse",            lambda k: f"{says(ctx.subj(k), 'joins')} the nation of {w}"),
        ("iPolyMarrySubject",       lambda k: f"{says(w, 'marries')} {ctx.subj(k)}"),
        ("iMarryAwaySubject",       lambda k: f"{says(w, 'marries')} {ctx.subj(k)}"),
        ("iBirthWithSubject",       lambda k: f"{says(w, 'has')} a child with {ctx.subj(k)}"),
        ("iAddTraitSubject",        lambda k: f"{says(ctx.subj(k), 'gains')} {w}"),
        ("iRemoveTraitSubject",     lambda k: f"{says(ctx.subj(k), 'loses')} {w}"),
        ("iAcquireTechSubject",     lambda k: f"{says(ctx.subj(k), 'acquires')} {w}"),
        ("iAddTechToDiscardSubject", lambda k: f"{w.capitalize()} goes to {poss(ctx.subj(k))} discard pile"),
        ("iTradeCitySubject",       lambda k: f"{says(ctx.subj(k), 'gains')} {w}"),
        ("iConvertUnitSubject",     lambda k: f"{w.capitalize()} converts to {ctx.subj(k)}"),
        ("iAmbitionFamilySubject",  lambda k: f"Starts an ambition for {ctx.subj(k)}"),
        ("iAmbitionReligionSubject", lambda k: f"Starts an ambition for {ctx.subj(k)}"),
        ("iTradeResourceToSubject", lambda k: f"Send {w} to {ctx.subj(k)} as a luxury"),
        ("iTradeResourceFromSubject", lambda k: f"{says(ctx.subj(k), 'sends')} {w} as a luxury"),
    )
    for tag, fn in table:
        k = idx(tag)
        if k is not None:
            out.append({"text": fn(k)})

    # Relationship pairs: First = RELATIONSHIP_*, Second = subject index. The
    # relationship's own text carries the object slot ("Endeared to {0}").
    def rel(tok: str, obj: str) -> str:
        raw = ctx.text.get("TEXT_" + tok, "") or ""
        raw = _ICON_RE.sub("", raw.split("~")[0])
        if "{0" in raw:
            return re.sub(r"\{0[^}]*\}", obj, raw)
        return f"{_tok(tok, 'RELATIONSHIP_')} {obj}"

    for tag, reverse, remove in (("AddRelationshipSubjects", False, False), ("AddRelationshipReverse", True, False),
                                 ("RemoveRelationshipSubjects", False, True), ("RemoveRelationshipReverse", True, True),
                                 ("RemoveRelationshipSubjectsOption", False, True),
                                 ("RemoveRelationshipReverseOption", True, True)):
        for p in b.findall(f"{tag}/Pair"):
            r, k = p.findtext("First") or "", p.findtext("Second")
            a, o = (ctx.subj(k), w) if reverse else (w, ctx.subj(k))
            out.append({"text": f"{a.capitalize()}: {'no longer ' if remove else ''}{rel(r, o)}"})
    rl = v("RemoveLeaderRelationship")
    if rl:
        out.append({"text": f"Your leader: no longer {rel(rl, ctx.who())}"})

    # Trait odds (TEXT_HELPTEXT_BONUS_TRAIT_PROB[_DELAY]).
    for tag, later in (("aiTraitProb", ""), ("aiTraitProbDelay", " next turn")):
        for p in b.findall(f"{tag}/Pair"):
            t, pr = p.findtext("zIndex") or "", p.findtext("iValue") or "0"
            out.append({"text": f"{pr}% chance{later}: becomes {ctx.name(t, 'TRAIT_')}"})
    return out


def _goals(b: ET.Element, ctx: Ctx) -> list[dict]:
    out: list[dict] = []
    v = b.findtext
    for tag, verb in (("GoalAdd", "Starts goal"), ("GoalForce", "Starts goal"),
                      ("FinishGoal", "Completes goal"), ("FailGoal", "Fails goal"),
                      ("AmbitionFamily", "Starts ambition"), ("AmbitionReligion", "Starts ambition")):
        if v(tag):
            out.append({"text": f"{verb}: {ctx.name(v(tag), 'GOAL_')}"})
    if _flag(b, "bAddAmbition"):
        out.append({"text": "Starts the event's ambition"})
    if v("Mission"):
        s = f"Carries out {ctx.name(v('Mission'), 'MISSION_')}"
        if v("iMissionSubject") not in (None, ""):
            s += f" on {ctx.subj(v('iMissionSubject'))}"
        if _flag(b, "bMissionFree"):
            s += " (free)"
        out.append({"text": s})
    return out


def _tribute(b: ET.Element, ctx: Ctx) -> list[dict]:
    """Tribute / send / trade yield lists (HelpText.Bonus.cs:27-175)."""
    out: list[dict] = []
    turns = int(b.findtext("iTributeTurns") or 0)

    def ylist(prefix: str) -> list[str]:
        parts: list[str] = []
        for suffix, note in (("Base", ""), ("", ""), ("PerUs", " per our city"), ("PerThem", " per their city")):
            for p in b.findall(f"{prefix}{suffix}/Pair"):
                y, val = p.findtext("zIndex") or "", int(p.findtext("iValue") or 0)
                if val:
                    parts.append(f"{'+' if val > 0 else ''}{val} {_tok(y, 'YIELD_')}{note}")
        return parts

    for prefix, head in (("aiYieldsTribute", f"Tribute from {ctx.who()}"),
                         ("aiYieldsSend", f"Send to {ctx.who()}"),
                         ("aiYieldsTrade", f"Trade with {ctx.who()}"),
                         ("aiOtherYields", f"Gain from {ctx.who()}")):
        parts = ylist(prefix)
        if parts and prefix == "aiYieldsTribute" and all(x.startswith("-") for x in parts):
            # A negative tribute is one you pay (HelpText TRIBUTE_TO wording).
            head, parts = f"Tribute to {ctx.who()}", [x[1:] for x in parts]
        if parts:
            tail = f" for {turns} turns" if prefix == "aiYieldsTribute" and turns else ""
            out.append({"text": f"{head}: {', '.join(parts)}{tail}"})
    return out


# Fields this module renders (or folds into another field's line).
CURATED_FIELDS = frozenset({
    # occurrences
    "OccurrenceStart", "OccurrenceStartPlayer", "OccurrenceForce", "OccurrenceForcePlayer",
    "OccurrenceEnd", "OccurrenceEndPlayer", "bOccurrenceStart", "bOccurrenceStartPending",
    "bOccurrenceSetPending", "iOccurrenceTargetSubject", "bIgnoreDelayTurns",
    # nationwide
    "DiplomacyPlayerTo", "DiplomacyPlayerFrom", "DiplomacyTribe", "DiplomacyAllPlayers",
    "DiplomacySubjects", "DiplomacyReverse", "bPeaceOffer", "bTruceOffer", "bTeamAlliance",
    "bTeamAllianceEnd", "bTribeAlliance", "bTribeAllianceEnd", "iAllianceSubject", "bTribeInvade",
    "bTribeRaid", "bDistantRaid", "iAttackCitySubject", "bCancelTrade", "bCancelTribute",
    "iContactSubject", "iSeizeThroneSubject", "bAbdicate", "iRegentOfSubject", "bChangeSuccession",
    "bStateReligion", "bStateReligionEnd", "FoundReligion", "bFoundReligionCity", "StartLaw",
    "EndLaw", "bStartLaw", "bEndLaw", "Victory", "bRazeCity", "bAbandonCity", "bCapitalCity",
    # subject-aimed
    "iSpreadToSubject", "iRemoveFromSubject", "iHeadReligionSubject", "iHeadFamilySubject",
    "iGovernorOfSubject", "iGeneralOfSubject", "iAgentCitySubject", "iExplorerOfSubject",
    "iJoinSubject", "iJoinReverse", "iPolyMarrySubject", "iMarryAwaySubject", "iBirthWithSubject",
    "iAddTraitSubject", "iRemoveTraitSubject", "iAcquireTechSubject", "iAddTechToDiscardSubject",
    "iTradeCitySubject", "iConvertUnitSubject", "iAmbitionFamilySubject", "iAmbitionReligionSubject",
    "iTradeResourceToSubject", "iTradeResourceFromSubject", "iTradeTurns",
    "AddRelationshipSubjects", "AddRelationshipReverse", "RemoveRelationshipSubjects",
    "RemoveRelationshipReverse", "RemoveRelationshipSubjectsOption", "RemoveRelationshipReverseOption",
    "RemoveLeaderRelationship", "aiTraitProb", "aiTraitProbDelay",
    # goals / missions
    "GoalAdd", "GoalForce", "FinishGoal", "FailGoal", "AmbitionFamily", "AmbitionReligion",
    "bAddAmbition", "Mission", "iMissionSubject", "iMissionReverse", "bMissionFree",
    # tribute / send / trade
    "aiYieldsTributeBase", "aiYieldsTributePerUs", "aiYieldsTributePerThem", "iTributeTurns",
    "aiYieldsSend", "aiYieldsSendBase", "aiYieldsSendPerUs", "aiYieldsSendPerThem",
    "aiYieldsTradeBase", "aiYieldsTradePerUs", "aiYieldsTradePerThem",
    "aiOtherYieldsBase", "aiOtherYieldsPer",
    # misc
    "aiStats", "iDestroyImprovements", "iBorderGrowth", "iRevealRange", "iXPUnit", "iHPUnit",
    "iHPCityPercent", "iSpreadUnits", "Council", "SetArchetype", "AddTraitReligion",
    "RemoveTraitReligion", "bFreeLaw", "bFreeTheology", "bChangeTheology", "aeEffectUnits",
    "aeCultureProject", "Forget", "UnitName", "SetName", "CharacterName", "SetNickname", "SetTitle",
    "bAddCharacter", "bAddAmbitionIgnoreEligible", "AddCourtierOther", "bAdoptReligion", "bSetFamilySupremacy", "bFoundReligion",
    # folded into build_missions' unit line
    "bMercenaryUnit",
})


def _misc(b: ET.Element, ctx: Ctx) -> list[dict]:
    """Fields whose registry template does not fill cleanly on its own."""
    out: list[dict] = []
    v = b.findtext
    w = ctx.who()

    def num(tag: str) -> int:
        try:
            return int(v(tag) or 0)
        except ValueError:
            return 0

    def signed(n: int) -> str:
        return f"{'+' if n > 0 else ''}{n}"

    for p in b.findall("aiStats/Pair"):
        st, n = p.findtext("zIndex") or "", int(p.findtext("iValue") or 0)
        if n:
            out.append({"text": f"Leader stat {ctx.name(st, 'STAT_')}: {signed(n)}"})
    if num("iDestroyImprovements"):
        n = num("iDestroyImprovements")
        out.append({"text": f"{n} improvement{'s' if n != 1 else ''} destroyed"})
    if num("iBorderGrowth"):
        n = num("iBorderGrowth")
        out.append({"text": f"{signed(n)} border tile{'s' if abs(n) != 1 else ''}"})
    if num("iRevealRange"):
        out.append({"text": f"Reveals the map within {num('iRevealRange')} tiles"})
    if num("iXPUnit"):
        out.append({"text": f"{signed(num('iXPUnit'))} XP to the unit"})
    if num("iHPUnit"):
        out.append({"text": f"{signed(num('iHPUnit'))} HP to the unit"})
    if num("iHPCityPercent"):
        out.append({"text": f"{signed(num('iHPCityPercent'))}% HP to the city"})
    if num("iSpreadUnits"):
        out.append({"text": f"+{num('iSpreadUnits')} Disciples of the religion"})
    if v("Council"):
        out.append({"text": f"{ctx.who().capitalize()} joins the council as {ctx.name(v('Council'), 'COUNCIL_')}"})
    if v("SetArchetype"):
        out.append({"text": f"Archetype becomes {ctx.name(v('SetArchetype'), 'TRAIT_')}"})
    if b.find("AddTraitReligion/Pair") is not None:
        out.append({"text": f"{ctx.who().capitalize()} becomes clergy of their religion"})
    if b.find("RemoveTraitReligion/Pair") is not None:
        out.append({"text": f"{ctx.who().capitalize()} is no longer clergy of their religion"})
    if _flag(b, "bFreeLaw"):
        out.append({"text": "Free law: the event's law"})
    if _flag(b, "bFreeTheology"):
        out.append({"text": "Free theology: the event's theology"})
    if _flag(b, "bChangeTheology"):
        out.append({"text": "Changes a theology to the event's theology"})
    effs = [ctx.name(z.text, "EFFECTUNIT_") for z in b.findall("aeEffectUnits/zValue") if z.text]
    if effs:
        out.append({"text": f"The unit gains {', '.join(effs)}"})
    if b.find("aeCultureProject/Pair") is not None:
        out.append({"text": "Starts the festival that matches the city's culture level"})
    if v("Forget"):
        out.append({"text": f"{says(w, 'forgets')}: {ctx.name(v('Forget'), 'MEMORY')}"})
    for tag, verb in (("UnitName", "The unit is renamed"), ("SetName", f"{w.capitalize()} is renamed"),
                      ("CharacterName", f"{w.capitalize()} is renamed"), ("SetNickname", f"{w.capitalize()} is now known as"),
                      ("SetTitle", f"{w.capitalize()} is granted the title")):
        if v(tag):
            out.append({"text": f"{verb} {ctx.name(v(tag), tag.upper() + '_')}"})
    for p in b.findall("AddCourtierOther/Pair"):
        c = p.findtext("First") or ""
        if c:
            out.append({"text": f"{says(ctx.nation(), 'gains')} a new courtier: {ctx.name(c, 'COURTIER_')}"})
    if _flag(b, "bAddCharacter"):
        out.append({"text": "A new character joins your nation"})
    if _flag(b, "bAddAmbitionIgnoreEligible"):
        out.append({"text": "Starts the event's ambition"})
    return out


def render(b: ET.Element, ctx: Ctx) -> list[dict]:
    return (_occurrences(b, ctx) + _state(b, ctx) + _subject_aimed(b, ctx) + _goals(b, ctx)
            + _tribute(b, ctx) + _misc(b, ctx))


def occurrence_refs(bonus_id: str, bonus_idx: dict, _seen: set | None = None) -> list[tuple[str, str]]:
    """(verb, occurrence id) pairs a bonus reaches, recursively — for backlinks."""
    _seen = _seen or set()
    if not bonus_id or bonus_id in _seen or bonus_id not in bonus_idx:
        return []
    _seen.add(bonus_id)
    b = bonus_idx[bonus_id]
    out: list[tuple[str, str]] = []
    for tag, verb in (("OccurrenceStart", "starts"), ("OccurrenceStartPlayer", "starts"),
                      ("OccurrenceForce", "starts"), ("OccurrenceForcePlayer", "starts"),
                      ("OccurrenceEnd", "ends"), ("OccurrenceEndPlayer", "ends")):
        oid = (b.findtext(tag) or "").strip()
        if oid:
            out.append(("readies" if verb == "starts" and _flag(b, "bOccurrenceSetPending") else verb, oid))
    for tag in ("aeBonuses", "aeAllCityBonuses", "aeFamilyBonuses"):
        for z in b.findall(f"{tag}/zValue"):
            out += occurrence_refs(z.text or "", bonus_idx, _seen)
    for p in b.findall("aeReligionBonuses/Pair"):
        out += occurrence_refs(p.findtext("Second") or "", bonus_idx, _seen)
    return out
