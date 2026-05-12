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

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "study_events.json"


RATING_LABELS: dict[str, str] = {
    "RATING_WISDOM":     "Wisdom",
    "RATING_CHARISMA":   "Charisma",
    "RATING_COURAGE":    "Courage",
    "RATING_DISCIPLINE": "Discipline",
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
        title = text.get(title_key, zid.replace("EVENTSTORY_", "").replace("_", " ").title())

        # Subject extras = prerequisites about the event subjects (e.g. SUBJECT_TEENAGER)
        prereqs: list[str] = []
        for pair in entry.findall("SubjectExtras/Pair"):
            sub = pair.findtext("Second") or ""
            if sub:
                prereqs.append(subject_label(sub))
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
            "prereqs": prereqs,
            "options": options,
            "weight": weight,
            "prob": prob,
            "repeat": repeat,
            "author": entry.findtext("zAuthor") or "",
        })

    events.sort(key=lambda e: e["title"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(events, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(events)} study events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
