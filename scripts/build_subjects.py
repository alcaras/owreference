#!/usr/bin/env python3
"""Build src/data/subjects.json from reference/XML/Infos/subject.xml.

What "Subjects" actually are
----------------------------
Despite the name, subject.xml does NOT model vassal states. It is the
event system's *casting* layer: every event story / mission / occurrence
slots its actors ("the leader", "an adult heir we dislike", "a rival
city on a river") from this catalog of ~2k Subject templates. Each
Subject is a class (Character, Player, City, Tile, …) plus a stack of
prerequisite filters (age, traits, opinions, diplomacy, terrain, …).
subjectClass.xml lists the 15 classes; subjectRelation.xml defines the
named relation predicates (SUBJECTRELATION_PLAYER_WAR, …) that Subjects
reference via RelationUs / RelationLeader.

Vassalage itself lives elsewhere (EVENTSTORY_VASSALAGE_* chains and
MISSION_VASSALIZE_TRIBE) — those event stories *use* these subjects.

For each subject we emit:
  - id / class / in-game label (GenderedName → genderedText → text key)
  - the designer's comment= note from the XML (priceless documentation)
  - humanized requirement chips (short text + schema-comment tooltip)
  - usage count across eventStory/eventOption/mission/goal/occurrence/
    globalsType XMLs, and an inferred DLC tag when a subject's label or
    usage exists only in DLC-suffixed files (-sap, -btt, -eoti, -wd, -wog)

Quirk (verified): subject yield thresholds are DISPLAY-scale, not the
usual ×10 internal scale — SUBJECT_PLAYER_MIN_200_MONEY carries
iValue=200, not 2000. Do not divide by 10 here.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "subjects.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import load_xml_indexes, load_text, _first_form  # noqa: E402

# File-name suffix → DLC / content pack. Same set build_events.py reads.
SUFFIX_DLC = {
    "sap": "Sacred & the Profane",
    "btt": "Behind the Throne",
    "eoti": "Empires of the Indus",
    "wd": "Wonders & Dynasties",
    "wog": "Wrath of Gods",
}

# Files that can reference SUBJECT_* ids (consumers, not definitions).
USE_GLOBS = ["eventStory*.xml", "eventOption*.xml"]
USE_FILES = ["mission.xml", "goal.xml", "occurrence.xml", "globalsType.xml"]


# ───────────────────────── label helpers ─────────────────────────

def _load_globals_int() -> dict[str, str]:
    p = XML_DIR / "globalsInt.xml"
    out: dict[str, str] = {}
    if p.exists():
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            if k:
                out[k] = (e.findtext("iValue") or "").strip()
    return out


GLOBALS_INT = _load_globals_int()


def _clean_text(s: str) -> str:
    """Strip the game's remaining text templates out of resolved strings:
    {singular_0:Unit:Units} → Units (we always render counted/plural),
    int(MIN_TREATY_TURNS) → its globalsInt value, icon(...) → dropped,
    {0_character} → 'the character'."""
    s = re.sub(r"\{singular_\d+:[^:}]+:([^}]+)\}", r"\1", s)
    s = re.sub(r"int\(([A-Z_]+)\)", lambda m: GLOBALS_INT.get(m.group(1), m.group(1)), s)
    s = re.sub(r"icon\([A-Z_]+\)\s*", "", s)
    s = re.sub(r"\{\d+_([a-z_]+)\}", lambda m: "the " + m.group(1).replace("_", " "), s)
    return re.sub(r"\s+", " ", s).strip()


def _camel_words(s: str) -> str:
    """NoRelationshipLeader → 'No Relationship Leader'."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)


def _tok_words(token: str, drop_first: bool = True) -> str:
    parts = token.split("_")
    if drop_first and len(parts) > 1:
        parts = parts[1:]
    return " ".join(p.title() for p in parts)


# Short labels for reference-valued fields (value is another TOKEN).
REF_LABELS = {
    "RelationUs": "Relation to us",
    "NoRelationUs": "Not relation to us",
    "RelationLeader": "Relation to leader",
    "NoRelationLeader": "Not relation to leader",
    "Religion": "Religion",
    "Tech": "Tech",
    "Law": "Law",
    "Theology": "Theology",
    "Resource": "Resource",
    "Goal": "Ambition",
    "Character": "Character",
    "CityName": "City name",
    "ActiveAmbition": "Active ambition",
    "ActiveQuest": "Active quest",
    "Occurrence": "Occurrence",
    "Trait": "Trait",
    "MemoryPrereq": "Memory",
    "MemoryInvalid": "No memory",
    "MemoryTeamPrereq": "Team memory",
    "MemoryTeamInvalid": "No team memory",
    "NationPrereq": "Nation",
    "DynastyPrereq": "Dynasty",
    "TechPrereq": "Has tech",
    "TechInvalid": "Lacks tech",
    "LawPrereq": "Law active",
    "TribePrereq": "Tribe",
    "HasFamilyClass": "Has family class",
    "FamilyClassPrereq": "Family class",
    "FamilyPrereq": "Family",
    "GenderPrereq": "Gender",
    "CouncilPrereq": "Council seat",
    "CourtierPrereq": "Courtier",
    "CouncilNotSet": "Vacant council seat",
    "TerrainClaimed": "Claimed terrain",
    "TerrainHeightClaimed": "Claimed height",
    "VegetationClaimed": "Claimed vegetation",
    "TraitNone": "No character with trait",
    "TraitPrereq": "Trait",
    "TraitInvalid": "Not trait",
    "CognomenPrereq": "Cognomen",
    "MinCultureLevel": "Culture level ≥",
    "MaxCultureLevel": "Culture level ≤",
    "ProjectPrereq": "City project",
    "ImprovementCity": "City has improvement",
    "ImprovementTile": "Tile improvement",
    "ImprovementTileAny": "Tile improvement (any state)",
    "ImprovementClassCity": "City has improvement class",
    "ImprovementClassTile": "Tile improvement class",
    "UnitType": "Unit",
    "UnitTrait": "Unit trait",
    "UnitEffect": "Unit effect",
    "UnitTerrain": "Unit on terrain",
    "TerrainTarget": "Terrain target",
    "CityLuxury": "City luxury",
}

# Hand-tuned short labels for the most common boolean filters; anything
# missing falls back to camel-splitting the field name (still readable:
# bNonRoyal → "Non Royal"). The schema comment rides along as a tooltip.
BOOL_LABELS = {
    "bIsUs": "Our nation",
    "bIsNotUs": "Another nation",
    "bIsUsOrThem": "Us or another nation",
    "bIsAnyone": "Anyone (incl. tribes)",
    "bIsSameTeam": "Teammate (other player)",
    "bHuman": "Human player",
    "bHumanOrAI": "Human or AI",
    "bNotMe": "Not our leader",
    "bLeader": "Is the leader",
    "bWasLeader": "Is or was the leader",
    "bNonLeader": "Not the leader",
    "bHeir": "Direct heir",
    "bNonHeir": "Not the heir",
    "bSuccession": "In line of succession",
    "bNonSuccession": "Not in succession",
    "bCapital": "Capital",
    "bNoDiplomacy": "No diplomacy (rebels/barbarians)",
    "bNoContact": "Not yet contacted",
    "bHasPlayer": "Belongs to a player",
    "bNoPlayer": "Tribe-owned (no player)",
    "bDisabled": "Never valid (disabled)",
    "bHidden": "Hidden in prereq lists",
    "bIgnoreRandom": "First valid (not random)",
    "bTriggerAdjacent": "Adjacent to trigger subject",
    "bMissionTarget": "Mission target",
}

# Pair-list fields: (label template per pair). Values verified display-scale.
PAIR_FIELDS = {
    "aiMinRating": ("{k} ≥ {v}", ("RATING_",)),
    "aiMaxRating": ("{k} ≤ {v}", ("RATING_",)),
    "aiMinYield": ("{k} stockpile ≥ {v}", ("YIELD_",)),
    "aiMaxYield": ("{k} stockpile ≤ {v}", ("YIELD_",)),
    "aiMinYieldLevels": ("{k} level ≥ {v}", ("YIELD_",)),
    "aiMaxYieldLevels": ("{k} level ≤ {v}", ("YIELD_",)),
    "aiMinEffectCity": ("{k} ≥ {v}", ("EFFECTCITY_",)),
    "aiMaxEffectCity": ("{k} ≤ {v}", ("EFFECTCITY_",)),
    "aiMinImprovementsFinished": ("{k} finished ≥ {v}", ("IMPROVEMENT_",)),
    "aiMaxImprovementsFinished": ("{k} finished ≤ {v}", ("IMPROVEMENT_",)),
    "aiMinNationEthnicity": ("{k} ethnicity ≥ {v}%", ("NATION_",)),
    "aiMinTribeEthnicity": ("{k} ethnicity ≥ {v}%", ("TRIBE_",)),
    "aiMinStats": ("{k} ≥ {v}", ("STAT_",)),
    "aiMaxStats": ("{k} ≤ {v}", ("STAT_",)),
}

LIST_FIELDS = {
    "aeTraitAny": "Has any trait: {vals}",
    "aeTraitNone": "Has no trait: {vals}",
    "aeRelationshipNone": "No relationship: {vals}",
    "aeYieldNegative": "Negative {vals} rate",
}

SKIP_FIELDS = {"zType", "GenderedName", "Class"}


def parse_schema_comments(root: ET.Element) -> dict[str, str]:
    """First <Entry> documents every field via comment= attributes."""
    out: dict[str, str] = {}
    first = root.find("Entry")
    if first is None:
        return out
    for child in first:
        c = child.get("comment")
        if c:
            out[child.tag] = re.sub(r"\s+", " ", c).strip()
    return out


class Resolver:
    """Token → display name, via entity Name fields and the merged text index."""

    def __init__(self, indexes: dict):
        self.indexes = indexes
        self.text = indexes.get("__text__", {})

    def name(self, token: str, strip: tuple[str, ...] = ()) -> str:
        if not token:
            return ""
        # 1. an entry in any loaded info file with a Name → text key
        for fname, idx in self.indexes.items():
            if fname == "__text__":
                continue
            e = idx.get(token)
            if e is not None:
                t = self.text.get(e.findtext("Name") or "", "")
                if t:
                    return t
        # 2. direct text key conventions
        for key in (f"TEXT_{token}", token):
            t = self.text.get(key, "")
            if t:
                return t
        # 3. strip a known prefix, else drop the first underscore segment
        for p in strip:
            if token.startswith(p):
                return _tok_words(token[len(p):], drop_first=False)
        return _tok_words(token)


def render_reqs(entry: ET.Element, schema: dict[str, str], resolve: Resolver) -> list[dict]:
    """Humanize every prerequisite field on a subject entry into chips."""
    reqs: list[dict] = []

    def add(text: str, field: str) -> None:
        chip = {"text": _clean_text(text)}
        tip = schema.get(field, "")
        if tip:
            chip["tip"] = tip
        reqs.append(chip)

    for child in entry:
        tag, val = child.tag, (child.text or "").strip()
        if tag in SKIP_FIELDS:
            continue

        if tag in PAIR_FIELDS:
            tmpl, strip = PAIR_FIELDS[tag]
            for p in child.findall("Pair"):
                k = resolve.name(p.findtext("zIndex") or "", strip)
                add(tmpl.format(k=k, v=p.findtext("iValue") or "0"), tag)
            continue

        if tag in LIST_FIELDS:
            vals = [resolve.name(v.text or "") for v in child.findall("zValue")]
            add(LIST_FIELDS[tag].format(vals=", ".join(vals)), tag)
            continue

        if tag.startswith("b"):
            if val == "1":
                add(BOOL_LABELS.get(tag, _camel_words(tag[1:])), tag)
            continue

        if tag.startswith("i"):
            if not val:
                continue
            body = _camel_words(tag[1:])
            if body.startswith("Min "):
                add(f"{body[4:]} ≥ {val}", tag)
            elif body.startswith("Max "):
                add(f"{body[4:]} ≤ {val}", tag)
            else:
                add(f"{body} = {val}", tag)
            continue

        # Reference-valued single fields (may repeat: findall on same tag is
        # implicit since we iterate children — each occurrence lands here).
        if val:
            label = REF_LABELS.get(tag, _camel_words(tag))
            pretty = resolve.name(val, ("SUBJECTRELATION_",))
            if label.endswith("≥") or label.endswith("≤"):
                add(f"{label} {pretty}", tag)
            else:
                add(f"{label}: {pretty}", tag)

    return reqs


def scan_usage() -> tuple[Counter, dict[str, set]]:
    """Count >SUBJECT_X< references across consumer XMLs; track source files."""
    files: list[Path] = []
    for g in USE_GLOBS:
        files.extend(sorted(XML_DIR.glob(g)))
    files.extend(XML_DIR / f for f in USE_FILES)
    pat = re.compile(r">(SUBJECT_[A-Z0-9_]+)<")
    counts: Counter = Counter()
    sources: dict[str, set] = {}
    for p in files:
        if not p.exists():
            continue
        suffix = ""
        m = re.match(r"^[a-zA-Z]+-([a-z]+)\.xml$", p.name)
        if m and m.group(1) in SUFFIX_DLC:
            suffix = m.group(1)
        for tok in pat.findall(p.read_text(encoding="utf-8")):
            counts[tok] += 1
            sources.setdefault(tok, set()).add(suffix or "base")
    return counts, sources


def main() -> None:
    indexes = load_xml_indexes(XML_DIR)
    resolve = Resolver(indexes)
    text_all = indexes["__text__"]

    # Which TEXT_SUBJECT_* / GENDERED keys ship only in the SaP text pack →
    # lets us tag SaP-introduced subjects (subject.xml has no GameContent).
    sap_text = set(load_text(XML_DIR, "text-subject-sap.xml").keys())
    base_text = set(load_text(XML_DIR, "text-subject.xml").keys())
    sap_only_text = sap_text - base_text

    # GENDERED_TEXT_X → masculine TEXT key (first Pair) for label resolution.
    gendered: dict[str, str] = {}
    for fn in ("genderedText.xml", "genderedText-sap.xml"):
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            first = e.find("Texts/Pair/zValue")
            if k and first is not None and first.text:
                gendered.setdefault(k, first.text)

    # Class order + display names from subjectClass.xml.
    class_order: list[str] = []
    class_names: dict[str, str] = {}
    for e in ET.parse(XML_DIR / "subjectClass.xml").getroot().findall("Entry"):
        cid = e.findtext("zType") or ""
        if not cid:
            continue
        class_order.append(cid)
        class_names[cid] = text_all.get(e.findtext("Name") or "", "") or _tok_words(cid)

    sroot = ET.parse(XML_DIR / "subject.xml").getroot()
    schema = parse_schema_comments(sroot)
    uses, use_sources = scan_usage()

    subjects: list[dict] = []
    for e in sroot.findall("Entry"):
        sid = e.findtext("zType") or ""
        if not sid:
            continue  # the two schema/divider entries
        cls = e.findtext("Class") or ""

        # In-game label: GenderedName → gendered → text; else direct text key.
        label = ""
        gkey = e.findtext("GenderedName") or ""
        tkey = gendered.get(gkey, "") if gkey else ""
        if not tkey:
            tkey = "TEXT_" + sid  # TEXT_SUBJECT_X convention
        label = text_all.get(tkey, "")
        if label:
            label = _clean_text(_first_form(label))

        comment = re.sub(r"\s+", " ", e.get("comment") or "").strip()
        reqs = render_reqs(e, schema, resolve)

        # DLC inference: label text shipped only by SaP, or every consumer
        # reference comes from one DLC's files.
        dlc = None
        if tkey in sap_only_text or gkey in sap_only_text:
            dlc = SUFFIX_DLC["sap"]
        else:
            srcs = use_sources.get(sid)
            if srcs and "base" not in srcs and len(srcs) == 1:
                dlc = SUFFIX_DLC[next(iter(srcs))]

        subjects.append({
            "id": sid,
            "class": cls,
            "label": label or None,
            "name": label or _tok_words(sid),
            "comment": comment or None,
            "reqs": reqs,
            "hidden": e.findtext("bHidden") == "1",
            "disabled": e.findtext("bDisabled") == "1",
            "dlc": dlc,
            "uses": uses.get(sid, 0),
        })

    cls_counts = Counter(s["class"] for s in subjects)
    rank = {c: i for i, c in enumerate(class_order)}
    subjects.sort(key=lambda s: (rank.get(s["class"], 99), s["id"]))

    out = {
        "classes": [
            {"id": c, "name": class_names.get(c, _tok_words(c)), "count": cls_counts[c]}
            for c in class_order if cls_counts.get(c)
        ],
        "subjects": subjects,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(subjects)} subjects, "
          f"{len(out['classes'])} classes, "
          f"{sum(1 for s in subjects if s['label'])} labeled, "
          f"{sum(1 for s in subjects if s['dlc'])} DLC-tagged, "
          f"{sum(s['uses'] for s in subjects)} references")


if __name__ == "__main__":
    main()
