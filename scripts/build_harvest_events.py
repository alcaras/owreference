#!/usr/bin/env python3
"""
Build src/data/harvest_events.json from eventStory*.xml + eventOption*.xml
+ text-eventStoryTitle*.xml + text-eventStory*.xml + text-eventOption*.xml.

A "Harvest Event" is any EventStory with Class=EVENTCLASS_HARVESTING.
For each we capture title, narrative body, the resource that triggered it
(if encoded in SubjectRelations), and each player option's text.
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
OUT = ROOT / "src" / "data" / "harvest_events.json"


EVENTSTORY_FILES = [
    "eventStory.xml",
    "eventStory-btt.xml",
    "eventStory-eoti.xml",
    "eventStory-sap.xml",
    "eventStory-wd.xml",
    "eventStory-wog.xml",
]

EVENTOPTION_FILES = [
    "eventOption.xml",
    "eventOption-btt.xml",
    "eventOption-eoti.xml",
    "eventOption-sap.xml",
    "eventOption-wd.xml",
    "eventOption-wog.xml",
]

TEXT_FILES = [
    "text-eventStory.xml",
    "text-eventStory-btt.xml",
    "text-eventStory-eoti.xml",
    "text-eventStory-sap.xml",
    "text-eventStoryTitle.xml",
    "text-eventStoryTitle-btt.xml",
    "text-eventStoryTitle-sap.xml",
    "text-eventStoryTitle-hittite.xml",
    "text-eventOption.xml",
    "text-eventOption-btt.xml",
    "text-eventOption-sap.xml",
    "text-eventOption-hittite.xml",
    "text-eventStory-hittite.xml",
    "text-eventStory-hittite-2.xml",
]


def load_texts() -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in TEXT_FILES:
        p = XML_DIR / fn
        if not p.exists():
            continue
        try:
            for entry in ET.parse(p).getroot().findall("Entry"):
                k = entry.findtext("zType") or ""
                en = (entry.findtext("en-US") or "").split("~")[0].strip()
                if k:
                    out.setdefault(k, en)
        except ET.ParseError:
            continue
    return out


# Match game placeholders like {CITY-1}, {UNIT-1,2}, {RESOURCE_GOLD}, etc.
_PLACEHOLDER_RE = re.compile(r"\{([A-Z][A-Z0-9_]*)(?:[-,][^{}]*)?\}")


def clean_event_text(s: str) -> str:
    """Drop link templates, normalize {CITY-1}, {YIELD_FOOD}, etc."""
    s = _strip_link_templates(s)
    # Replace {CITY-1} → "our City", {RESOURCE_X} → "Resource X"
    def repl(m):
        tok = m.group(1)
        if tok.startswith("CITY"):
            return "our city"
        if tok.startswith("PLAYER"):
            return "our people"
        if tok.startswith("UNIT"):
            return "our scouts"
        if tok.startswith("LEADER"):
            return "our leader"
        if tok.startswith("CAPITAL"):
            return "our capital"
        if tok.startswith("CHARACTER"):
            return "the subject"
        if tok.startswith("FAMILY"):
            return "the family"
        if tok.startswith("YIELD_"):
            return tok.replace("YIELD_", "").title()
        if tok.startswith("RESOURCE_"):
            return tok.replace("RESOURCE_", "").replace("_", " ").title()
        return tok.replace("_", " ").title()
    s = _PLACEHOLDER_RE.sub(repl, s)
    return s


def parse_xml(name: str) -> ET.Element | None:
    p = XML_DIR / name
    if not p.exists():
        return None
    try:
        return ET.parse(p).getroot()
    except ET.ParseError:
        return None


def load_eventstories() -> list[tuple[str, ET.Element]]:
    """Return list of (zType, entry) for all harvest events across files."""
    out: list[tuple[str, ET.Element]] = []
    for fn in EVENTSTORY_FILES:
        root = parse_xml(fn)
        if root is None:
            continue
        for entry in root.findall("Entry"):
            zt = entry.findtext("zType") or ""
            cls = entry.findtext("Class") or ""
            if zt and cls == "EVENTCLASS_HARVESTING":
                out.append((zt, entry))
    return out


def load_options() -> dict[str, ET.Element]:
    out: dict[str, ET.Element] = {}
    for fn in EVENTOPTION_FILES:
        root = parse_xml(fn)
        if root is None:
            continue
        for entry in root.findall("Entry"):
            zt = entry.findtext("zType") or ""
            if zt:
                out.setdefault(zt, entry)
    return out


def main() -> int:
    texts = load_texts()
    options_idx = load_options()
    stories = load_eventstories()

    items: list[dict] = []
    for zt, entry in stories:
        title_key = entry.findtext("Name") or ""
        body_key = entry.findtext("Text") or ""
        title = clean_event_text(texts.get(title_key, "")) or zt.replace("EVENTSTORY_HARVEST_", "").replace("_", " ").title()
        body = clean_event_text(texts.get(body_key, ""))

        # Trigger resource: scan aeSubjects for SUBJECT_RESOURCE_X
        resource = ""
        for sv in entry.findall("aeSubjects/zValue"):
            t = sv.text or ""
            if t.startswith("SUBJECT_RESOURCE_"):
                resource = t.replace("SUBJECT_RESOURCE_", "").replace("_", " ").title()
                break

        # Author
        author = entry.findtext("zAuthor") or ""

        # Background
        bg = entry.findtext("zBackgroundName") or ""

        # Options — legacy schema: <aeOptions><zValue>EVENTOPTION_...</zValue></aeOptions>
        # New schema (EOTI / Hittite): inline <EventOption>...</EventOption> elements.
        option_objs: list[dict] = []
        for ov in entry.findall("aeOptions/zValue"):
            opt_id = ov.text or ""
            if not opt_id:
                continue
            opt_entry = options_idx.get(opt_id)
            if opt_entry is None:
                continue
            opt_text_key = opt_entry.findtext("Text") or ""
            opt_text = clean_event_text(texts.get(opt_text_key, "")) or opt_id.split("_OPTION_")[-1]
            bonuses = [b.text or "" for b in opt_entry.findall("aeBonuses/zValue") if (b.text or "").strip()]
            option_objs.append({
                "id": opt_id,
                "text": opt_text,
                "bonuses": bonuses,
            })
        # Inline (newer DLC) schema: <EventOptions><EventOption>...
        for oe in entry.findall("EventOptions/EventOption") + entry.findall("EventOption"):
            opt_text_key = oe.findtext("Text") or ""
            opt_text = clean_event_text(texts.get(opt_text_key, "")) or opt_text_key
            bonuses: list[str] = []
            for pair in oe.findall("SubjectBonuses/Pair"):
                second = pair.findtext("Second") or ""
                if second:
                    bonuses.append(second)
            option_objs.append({
                "id": opt_text_key,
                "text": opt_text,
                "bonuses": bonuses,
            })

        slug = zt.replace("EVENTSTORY_HARVEST_", "").lower()
        items.append({
            "id": zt,
            "slug": slug,
            "title": title,
            "body": body,
            "resource": resource,
            "author": author,
            "background": bg,
            "options": option_objs,
        })

    items.sort(key=lambda x: x["title"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(items)} harvest events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
