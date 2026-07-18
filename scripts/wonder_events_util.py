"""Shared definition of "wonder decision events" — used by build_events.py
(which renders them on the Wonder Events page), build_story_events.py (which
excludes them from the story-events category pages so they don't double-list)
and build_wonders.py (which cross-links each wonder to its event).

A wonder decision event is an eventStory that:
  · fires on Trigger=EVENTTRIGGER_IMPROVEMENT_FINISHED,
  · whose TriggerData is a wonder (improvement.xml bWonder=1),
  · is not hidden (bHidden excludes the historical-city Steam-achievement
    events, which grant nothing in-game), and
  · offers 2+ options (a real decision).

The 1-option "wonder finished" announcements (+Legitimacy by wonder tier) are
NOT in this set: they carry bMultiples=1, so they always fire *in addition to*
whatever wins the weighted event roll (PlayerEvent.cs seEventMultiples) and
stay on the story-events pages.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

WONDER_TRIGGER = "EVENTTRIGGER_IMPROVEMENT_FINISHED"


def wonder_ids(xml_dir: Path) -> set[str]:
    """zTypes of all wonder improvements (improvement.xml bWonder=1)."""
    out: set[str] = set()
    for e in ET.parse(xml_dir / "improvement.xml").getroot().findall("Entry"):
        if (e.findtext("bWonder") or "") == "1":
            zt = e.findtext("zType")
            if zt:
                out.add(zt)
    return out


def option_count(s: ET.Element) -> int:
    """Number of options a story offers, across both option syntaxes."""
    n = sum(1 for z in s.findall("aeOptions/zValue") if (z.text or "").strip())
    n += len(s.findall("EventOptions/EventOption"))
    return n


def is_wonder_decision_event(s: ET.Element, wonders: set[str]) -> bool:
    return (
        (s.findtext("Trigger") or "") == WONDER_TRIGGER
        and (s.findtext("TriggerData") or "") in wonders
        and (s.findtext("bHidden") or "") != "1"
        and option_count(s) >= 2
    )
