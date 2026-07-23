#!/usr/bin/env python3
"""Build src/data/event-search.json — the ONE global event search index.

The events on the site live across five pages, each with its own builder:
  · /events/<category>   story events           src/data/story-events/search.json
  · /expedition-events   EVENTCLASS_EXPLORING    src/data/events.json (key=expeditions)
  · /ruin-events         RUINS_EXPLORED + chain  src/data/events.json (key=ruins)
  · /harvest-events      EVENTCLASS_HARVESTING   src/data/harvest_events.json
  · /study-events        EVENTCLASS_STUDY        src/data/study_events.json

The Story Events page's own search only covered the first bucket, so an event
that lives on a dedicated page (e.g. "The Ant's Gold") was unfindable from there.
This merges ALL of them into a single title index with a fully-resolved href
(relative to BASE_URL) per event, so one search box finds anything and links
straight to the card on whatever page it actually renders.

Entry shape: { i: id, n: name, g: group label, h: href-without-base }.
Titles only — story prose stays an in-game discovery (matches the other indexes).

Reads already-generated JSON, so it MUST run after build_story_events.py,
build_events.py, build_harvest_events.py and build_study_events.py (the Makefile
data: target orders them so).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
OUT = DATA / "event-search.json"


def main() -> int:
    rows: list[dict] = []
    seen: set[str] = set()

    def add(eid: str, name: str, group: str, href: str) -> None:
        if not eid or eid in seen or not name:
            return
        seen.add(eid)
        rows.append({"i": eid, "n": name, "g": group, "h": href})

    # ── Story events (already a search index: i, n, s=part slug, g=category) ──
    story = json.loads((DATA / "story-events" / "search.json").read_text())
    for e in story:
        add(e["i"], e["n"], e["g"], f"events/{e['s']}#{e['i']}")

    # ── Ruins + Expeditions (events.json sections anchor cards by id) ────────
    # Family events are a non-exclusive cross-cut (already indexed via their
    # primary page), so they're intentionally absent here.
    PAGE_FOR = {"ruins": ("ruin-events", "Ruin Event"),
                "expeditions": ("expedition-events", "Expedition Event"),
                "wonders": ("wonder-events", "Wonder Event"),
                "projects": ("project-events", "Project Event"),
                "buildings": ("building-events", "Building Event")}
    sections = json.loads((DATA / "events.json").read_text())
    for sec in sections:
        page, label = PAGE_FOR.get(sec.get("key", ""), (None, None))
        if not page:
            continue
        for ev in sec["events"]:
            add(ev["id"], ev["name"], label, f"{page}#{ev['id']}")

    # ── Harvest (flat list, anchored on the page by slug) ────────────────────
    for ev in json.loads((DATA / "harvest_events.json").read_text()):
        add(ev["id"], ev["title"], "Harvest Event", f"harvest-events#{ev['slug']}")

    # ── Study (flat list, anchored on the page by slug) ──────────────────────
    for ev in json.loads((DATA / "study_events.json").read_text()):
        add(ev["id"], ev["title"], "Study Event", f"study-events#{ev['slug']}")

    rows.sort(key=lambda r: (r["n"].lower(), r["i"]))
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")) + "\n"
    OUT.write_text(payload)

    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(rows)} events, "
          f"{len(payload) / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
