#!/usr/bin/env python3
"""Build src/data/occurrence_events.json — for every occurrence, the events that
start or end it, and whether that happens as the event opens (before any
choice) or only if a particular option is picked.

An event's own aeBonuses fire as it opens (PlayerEvent.doEventStory,
PlayerEvent.cs:13818); an option's fire when it is chosen, including each
weighted sub-option of an aiEventOptionProb roll. Bonuses nest, so the walk is
recursive (event_bonus.occurrence_refs). Links use each event's own page and
anchor from event-search.json (never a re-derived slug).

Run after build_event_search.py; the /occurrences page renders the lists.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_missions as m  # noqa: E402
import build_story_events as bse  # noqa: E402
import event_bonus as evb  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEARCH = ROOT / "src" / "data" / "event-search.json"
OUT = ROOT / "src" / "data" / "occurrence_events.json"


def main() -> int:
    bonus_idx = m.bonus_index()
    eopt_idx = m.index_many(*sorted(p.name for p in m.XML_DIR.glob("eventOption*.xml")))
    story_idx, _packs = bse.load_stories()
    hrefs = {e["i"]: e for e in json.loads(SEARCH.read_text())}
    text = m.load_text(*bse.TEXT_FILES)

    out: dict[str, list[dict]] = {}

    def add(oid: str, verb: str, sid: str, when: str) -> None:
        hit = hrefs.get(sid)
        s = story_idx[sid]
        name = hit["n"] if hit else m.clean_text(text.get(s.findtext("Name") or "", m._tok(sid, "EVENTSTORY_")))
        row = {"id": sid, "name": name, "href": hit["h"] if hit else "", "verb": verb, "when": when}
        rows = out.setdefault(oid, [])
        if row not in rows:
            rows.append(row)

    for sid, s in story_idx.items():
        for bz in s.findall("aeBonuses/zValue"):
            for verb, oid in evb.occurrence_refs(bz.text or "", bonus_idx):
                add(oid, verb, sid, "opens")
        opts = [eopt_idx[z.text] for z in s.findall("aeOptions/zValue") if z.text in eopt_idx]
        for opt in opts:
            subs = [eopt_idx[k] for k, _w in m.pairs(opt, "aiEventOptionProb") if k in eopt_idx]
            for o in [opt] + subs:
                for bz in o.findall("aeBonuses/zValue"):
                    for verb, oid in evb.occurrence_refs(bz.text or "", bonus_idx):
                        add(oid, verb, sid, "choice")
        for opt in s.findall("EventOptions/EventOption"):
            for p in opt.findall("SubjectBonuses/Pair"):
                for verb, oid in evb.occurrence_refs(p.findtext("Second") or "", bonus_idx):
                    add(oid, verb, sid, "choice")

    for rows in out.values():
        rows.sort(key=lambda r: (r["verb"] != "starts", r["when"] != "opens", r["name"]))
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    n = sum(len(v) for v in out.values())
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {n} event links across {len(out)} occurrences")
    return 0


if __name__ == "__main__":
    sys.exit(main())
