#!/usr/bin/env python3
"""
Build src/data/study_events.json from eventStory*.xml + eventOption*.xml +
bonus*.xml.

Filters all entries with Class=EVENTCLASS_STUDY across the base game and the
btt/sap/wd/wog DLC packs, joins them with their event options and the bonus
each option grants, and emits a flat list of:
  • event title (resolved from text-eventStoryTitle*.xml)
  • prerequisites (subject extras: e.g., SUBJECT_HIGH_CHARISMA, SUBJECT_TEENAGER)
  • options, each with a humanized outcome (trait gained, rating bump, …)
  • weight, probability, repeat

The spreadsheet's Study Events tab lists each event and the choice landscape;
this gives the same view, derived from XML.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_missions import clean_text  # noqa: E402  shared game-text cleaner
import build_events as bev  # noqa: E402  cm_ineligible + class-folded timing

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "study_events.json"
COURSES_OUT = ROOT / "src" / "data" / "study_courses.json"

# The four heir-education courses a tutor can set (TRAIT_STUDY_* in trait.xml).
COURSES = ["PHILOSOPHY", "POLITICS", "TACTICS", "COMMERCE"]


RATING_LABELS: dict[str, str] = {
    "RATING_WISDOM":     "Wisdom",
    "RATING_CHARISMA":   "Charisma",
    "RATING_COURAGE":    "Courage",
    "RATING_DISCIPLINE": "Discipline",
}

# A royal child's tutor sets a course of study; each EVENTCLASS_STUDY event is
# gated to one (or to "Any") via a SUBJECT_STUDY_* subject-extra. This is the
# axis the Tutor Events tab groups on.
STUDY_LABELS: dict[str, str] = {
    "SUBJECT_STUDY_TACTICS":    "Tactics",
    "SUBJECT_STUDY_COMMERCE":   "Commerce",
    "SUBJECT_STUDY_PHILOSOPHY": "Philosophy",
    "SUBJECT_STUDY_POLITICS":   "Politics",
    "SUBJECT_STUDY_ANY":        "Any",
    "SUBJECT_STUDY_ANY_HIDDEN": "Any",
}

# Nation-locked study events (Rome's Bulla, Greece's Agoge, …). The gate is a
# SUBJECT_PLAYER_<NATION> (or SUBJECT_CHARACTER_<NATION>) subject-extra.
NATION_SUBJECTS: dict[str, str] = {
    "SUBJECT_PLAYER_ROME":      "Rome",
    "SUBJECT_PLAYER_BABYLONIA": "Babylonia",
    "SUBJECT_PLAYER_GREECE":    "Greece",
    "SUBJECT_PLAYER_HITTITE":   "Hittites",
    "SUBJECT_PLAYER_ASSYRIA":   "Assyria",
    "SUBJECT_PLAYER_KUSH":      "Kush",
    "SUBJECT_PLAYER_EGYPT":     "Egypt",
    "SUBJECT_CHARACTER_EGYPT":  "Egypt",
    "SUBJECT_PLAYER_PERSIA":    "Persia",
    "SUBJECT_PLAYER_CARTHAGE":  "Carthage",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text_all() -> dict[str, str]:
    """Merge every text-*.xml file into a single zType → en-US (first form) map."""
    out: dict[str, str] = {}
    for p in XML_DIR.glob("text-*.xml"):
        try:
            for e in ET.parse(p).getroot().findall("Entry"):
                k = e.findtext("zType") or ""
                en = (e.findtext("en-US") or "").split("~")[0].strip()
                if k and en and k not in out:
                    out[k] = en
        except ET.ParseError:
            continue
    return out


def index_all(stem: str) -> dict[str, ET.Element]:
    """Read base + every DLC variant of a stem (e.g. eventStory) and merge."""
    idx: dict[str, ET.Element] = {}
    base = XML_DIR / f"{stem}.xml"
    if base.exists():
        for e in ET.parse(base).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            if k:
                idx.setdefault(k, e)
    for p in XML_DIR.glob(f"{stem}-*.xml"):
        try:
            for e in ET.parse(p).getroot().findall("Entry"):
                k = e.findtext("zType") or ""
                if k:
                    idx.setdefault(k, e)
        except ET.ParseError:
            continue
    return idx


def humanize_bonus(b: ET.Element, indexes: dict, text: dict) -> list[str]:
    """Render a bonus entry as a list of one-line outcome strings."""
    out: list[str] = []

    # Rating changes (BONUS_GAIN_CHARISMA_1 → +1 Charisma)
    for pair in b.findall("aiRatings/Pair"):
        rating = RATING_LABELS.get(pair.findtext("zIndex") or "", "")
        v = int(pair.findtext("iValue") or "0")
        if v:
            sign = "+" if v > 0 else ""
            out.append(f"{sign}{v} {rating}")

    # Yields (aiYields, aiYieldStockpile, aiGlobalYields)
    for tag in ("aiYieldStockpile", "aiGlobalYields", "aiYields"):
        for pair in b.findall(f"{tag}/Pair"):
            y = (pair.findtext("zIndex") or "").replace("YIELD_", "").title()
            v = int(pair.findtext("iValue") or "0")
            if v:
                sign = "+" if v > 0 else ""
                out.append(f"{sign}{v} {y}")

    # Traits added/removed
    for t in b.findall("aeAddTraits/zValue"):
        if t.text:
            nm = text.get(f"TEXT_{t.text}", t.text.replace("TRAIT_", "").replace("_", " ").title())
            out.append(f"Gain {nm}")
    for t in b.findall("aeRemoveTraits/zValue"):
        if t.text:
            nm = text.get(f"TEXT_{t.text}", t.text.replace("TRAIT_", "").replace("_", " ").title())
            out.append(f"Lose {nm}")

    # Relationships (BONUS_LEADER_LOVER_OF → "Becomes Lover of Leader")
    for tag in ("AddLeaderRelationship", "AddSubjectRelationship"):
        v = b.findtext(tag) or ""
        if v:
            rel = v.replace("RELATIONSHIP_", "").replace("_", " ").title()
            out.append(f"Add Relationship: {rel}")

    return out


def subject_label(token: str) -> str:
    """SUBJECT_HIGH_CHARISMA → 'High Charisma'."""
    s = token.replace("SUBJECT_", "")
    return s.replace("_", " ").title()


def build_study_courses(option_idx: dict[str, ET.Element],
                        bonus_idx: dict[str, ET.Element]) -> list[dict]:
    """Per-course metadata for the Jobs at-a-glance matrix.

    Two XML facts per course:
    - The rating bump granted when the tutor sets the course:
      bonus-event.xml BONUS_EVENTOPTION_STUDY_<COURSE> → aiRatings
      (Philosophy +1 Wisdom, Politics +1 Charisma, …).
    - The archetype pool offered at graduation:
      eventOption.xml EVENTOPTION_STUDY_<COURSE>_ARCHETYPES → aiEventOptionProb
      lists the EVENTOPTION_ARCHETYPE_<X> choices (all weight 1000). The same
      pools are mirrored in TEXT_TRAIT_STUDY_<COURSE>_DESCRIPTION.
    """
    courses: list[dict] = []
    for course in COURSES:
        rating, value = "", 0
        b = bonus_idx.get(f"BONUS_EVENTOPTION_STUDY_{course}")
        if b is not None:
            for pair in b.findall("aiRatings/Pair"):
                rating = RATING_LABELS.get(pair.findtext("zIndex") or "", "")
                value = int(pair.findtext("iValue") or "0")
        archetypes: list[str] = []
        opt = option_idx.get(f"EVENTOPTION_STUDY_{course}_ARCHETYPES")
        if opt is not None:
            for pair in opt.findall("aiEventOptionProb/Pair"):
                ref = pair.findtext("zIndex") or ""
                if ref.startswith("EVENTOPTION_ARCHETYPE_"):
                    # EVENTOPTION_ARCHETYPE_TACTICIAN → "Tactician" (single-word
                    # names; matches archetypes.json "name")
                    archetypes.append(ref.removeprefix("EVENTOPTION_ARCHETYPE_").title())
        courses.append({
            "course": course.title(),
            "rating": rating,
            "ratingBonus": value,
            "archetypes": archetypes,
        })
    return courses


def main() -> int:
    text = load_text_all()

    event_idx     = index_all("eventStory")
    option_idx    = index_all("eventOption")
    bonus_idx     = index_all("bonus")
    # Also fold in bonus-event-*.xml entries (shared shape)
    for p in XML_DIR.glob("bonus-event*.xml"):
        try:
            for e in ET.parse(p).getroot().findall("Entry"):
                k = e.findtext("zType") or ""
                if k:
                    bonus_idx.setdefault(k, e)
        except ET.ParseError:
            continue

    events: list[dict] = []

    for zid, entry in event_idx.items():
        if (entry.findtext("Class") or "") != "EVENTCLASS_STUDY":
            continue

        title_key = entry.findtext("Name") or ""
        title = clean_text(text.get(title_key, zid.replace("EVENTSTORY_", "").replace("_", " ").title()))

        # Subject extras = prerequisites about the event subjects (e.g. SUBJECT_TEENAGER)
        prereqs: list[str] = []
        study = ""
        nation = ""
        for pair in entry.findall("SubjectExtras/Pair"):
            sub = pair.findtext("Second") or ""
            if sub:
                prereqs.append(subject_label(sub))
                if not study and sub in STUDY_LABELS:
                    study = STUDY_LABELS[sub]
                if not nation and sub in NATION_SUBJECTS:
                    nation = NATION_SUBJECTS[sub]
        # Deduplicate while preserving order
        seen: set[str] = set()
        prereqs = [p for p in prereqs if not (p in seen or seen.add(p))]

        options: list[dict] = []
        for opt_ref in entry.findall("aeOptions/zValue"):
            opt_id = opt_ref.text or ""
            if not opt_id:
                continue
            opt = option_idx.get(opt_id)
            if opt is None:
                continue
            opt_text_key = opt.findtext("Text") or ""
            opt_text = text.get(opt_text_key, opt_id.replace("EVENTOPTION_", "").replace("_", " ").title())
            outcomes: list[str] = []
            for b_ref in opt.findall("aeBonuses/zValue"):
                b_id = b_ref.text or ""
                if not b_id:
                    continue
                b = bonus_idx.get(b_id)
                if b is None:
                    continue
                outcomes.extend(humanize_bonus(b, bonus_idx, text))
            options.append({
                "id": opt_id,
                "text": opt_text,
                "outcomes": outcomes,
            })

        weight = int(entry.findtext("iWeight") or "0")
        prob = int(entry.findtext("iProb") or "0")
        repeat = entry.findtext("iRepeatTurns") or ""

        events.append({
            "id": zid,
            "slug": zid.replace("EVENTSTORY_STUDY_", "").lower(),
            "title": title,
            "study": study,
            "nation": nation,
            "prereqs": prereqs,
            "options": options,
            "weight": weight,
            "prob": prob,
            "repeat": repeat,
            "author": entry.findtext("zAuthor") or "",
            # Earliest fire turn (own iMinTurns; STUDY class has no floor) and
            # Competitive-Mode eligibility — same markers as the other events.
            "minTurns": bev.timing(entry).get("minTurns"),
            "cmEligible": False if bev.cm_ineligible(entry) else None,
        })

    events.sort(key=lambda e: e["title"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(events, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(events)} study events")

    courses = build_study_courses(option_idx, bonus_idx)
    COURSES_OUT.write_text(json.dumps(courses, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {COURSES_OUT.relative_to(ROOT)} — {len(courses)} study courses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
