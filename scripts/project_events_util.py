"""Shared definition of "project events" — decision pop-ups that fire when a
city finishes a production Project (Trigger=EVENTTRIGGER_PRODUCTION_PROJECT).

Used by build_events.py (renders them on the Project Events page) and
build_story_events.py (excludes them from the story-events category pages so
they don't double-list).

Two flavours, distinguished by the project's iMaxCount:
  · one-time building projects (Archive, Forum, Walls, Treasury, Sangam,
    Opulence) — build it once, fire a specific decision, like a wonder event.
  · repeatable projects (Festival, Hunt, Olympiad) — event generators: each
    time you run one it rolls one story from a weighted pool.

Only stories offering a real choice (2+ options) count; the 1-option
"achievement" pop-ups grant nothing in-game and stay off the page.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_TRIGGER = "EVENTTRIGGER_PRODUCTION_PROJECT"

PROJECT_FILES = ("project.xml", "project-event.xml", "project-event-sap.xml",
                 "project-event-wog.xml", "project-event-eoti.xml",
                 "project-event-wd.xml")


def option_count(s: ET.Element) -> int:
    n = sum(1 for z in s.findall("aeOptions/zValue") if (z.text or "").strip())
    n += len(s.findall("EventOptions/EventOption"))
    return n


def is_project_event(s: ET.Element) -> bool:
    return (s.findtext("Trigger") or "") == PROJECT_TRIGGER and option_count(s) >= 2


def project_index(xml_dir: Path) -> dict[str, ET.Element]:
    """zType → project Entry across every project file (first wins)."""
    out: dict[str, ET.Element] = {}
    for fn in PROJECT_FILES:
        p = xml_dir / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            zt = e.findtext("zType")
            if zt and zt not in out:
                out[zt] = e
    return out


def is_one_time(project_entry: ET.Element | None) -> bool:
    """A project is one-time if it caps at a single production (iMaxCount=1);
    repeatable projects leave it blank/0."""
    if project_entry is None:
        return False
    return (project_entry.findtext("iMaxCount") or "").strip() == "1"
