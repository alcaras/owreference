"""Shared definition of "building events" — decision pop-ups that fire when a
city finishes a NON-wonder improvement/building (Trigger=
EVENTTRIGGER_IMPROVEMENT_FINISHED, TriggerData a real improvement that is not a
Wonder). Wonders get their own page (see wonder_events_util); this is the
sibling for ordinary buildings — Barracks, Library, Market, Quarry, Temple, …

Used by build_events.py (renders them on the Building Events page) and
build_story_events.py (excludes them from the story-events category pages).

Only stories offering a real choice (2+ options) and not hidden count — the
1-option/hidden pop-ups are Steam-achievement or announcement stubs.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

IMPROVEMENT_TRIGGER = "EVENTTRIGGER_IMPROVEMENT_FINISHED"

IMPROVEMENT_FILES = ("improvement.xml", "improvement-event.xml",
                     "improvement-event-sap.xml")


def improvement_index(xml_dir: Path) -> dict[str, ET.Element]:
    out: dict[str, ET.Element] = {}
    for fn in IMPROVEMENT_FILES:
        p = xml_dir / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            zt = e.findtext("zType")
            if zt and zt not in out:
                out[zt] = e
    return out


def improvement_ids(xml_dir: Path) -> set[str]:
    return set(improvement_index(xml_dir).keys())


def clean_improvement_name(raw: str) -> str:
    """text-improvement entries can carry an `icon(RELIGION_X)` prefix and
    `~`-separated gender/plural forms — take the first, unprefixed form."""
    first = (raw or "").split("~")[0]
    if first.startswith("icon("):
        end = first.find(")")
        if end != -1:
            first = first[end + 1:]
    return first.strip()


def option_count(s: ET.Element) -> int:
    n = sum(1 for z in s.findall("aeOptions/zValue") if (z.text or "").strip())
    n += len(s.findall("EventOptions/EventOption"))
    return n


def is_building_event(s: ET.Element, wonders: set[str], improvements: set[str]) -> bool:
    td = s.findtext("TriggerData") or ""
    return (
        (s.findtext("Trigger") or "") == IMPROVEMENT_TRIGGER
        and td in improvements
        and td not in wonders
        and (s.findtext("bHidden") or "") != "1"
        and option_count(s) >= 2
    )
