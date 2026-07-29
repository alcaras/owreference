#!/usr/bin/env python3
"""Build public/data/search-index.json — the header's site-wide search.

One light index, lazy-fetched by the header on first focus:
  { n: name, t: type label, u: site-relative url, a: aliases (lower, joined),
    g: group/subtitle (events), c: icon path }
Sources: the page catalog (tabs.ts), the entity registry, and the event search
index the events pages already build (which carries the page#anchor for every
event). Runtime-fetched, so it lives under public/ like overlay-cards.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
OUT = ROOT / "public" / "data" / "search-index.json"

TYPE_LABEL = {
    "unit": "Unit", "tech": "Technology", "trait": "Trait", "archetype": "Archetype",
    "family": "Family", "shrine": "Shrine", "resource": "Resource", "law": "Law",
    "wonder": "Wonder", "improvement": "Improvement", "yield": "Yield",
    "nation": "Nation", "tribe": "Tribe", "theology": "Theology",
    "promotion": "Promotion", "project": "Project",
}


def clean(name: str) -> str:
    return re.sub(r"\s{2,}", " ", re.sub(r"\{[^}]*\}", "", name or "")).strip()


def main() -> int:
    out: list[dict] = []

    # ── the pages themselves (tabs.ts is the single source of truth) ─────────
    tabs_src = (DATA / "tabs.ts").read_text()
    for block in re.split(r"(?m)^  \{$", tabs_src)[1:]:
        slug = re.search(r"slug: '([^']+)'", block)
        label = re.search(r"label: '([^']+)'", block)
        status = re.search(r"status: '([^']+)'", block)
        if slug and label and status and status.group(1) == "built":
            out.append({"n": label.group(1), "t": "Page", "u": slug.group(1)})

    # ── entities (icons via overlay-cards.json, which resolved one per id) ───
    cards = json.loads((ROOT / "public" / "data" / "overlay-cards.json").read_text())
    reg = json.loads((DATA / "entities.json").read_text())
    for e in reg["entities"]:
        name = clean(e.get("name") or "")
        page = e.get("page") or ""
        if not name or not page:
            continue
        entry = {"n": name, "t": TYPE_LABEL.get(e["type"], e["type"].title()), "u": page}
        aliases = " ".join(sorted({clean(a).lower() for a in e.get("aliases") or []
                                   if clean(a) and clean(a).lower() != name.lower()}))
        if aliases:
            entry["a"] = aliases
        icon = e.get("icon") or (cards.get(e["id"]) or {}).get("icon") or ""
        if icon:
            entry["c"] = icon
        out.append(entry)

    # ── events (page#anchor already resolved by the events build) ────────────
    for ev in json.loads((DATA / "event-search.json").read_text()):
        name = clean(ev.get("n") or "")
        if not name or not ev.get("h"):
            continue
        entry = {"n": name, "t": "Event", "u": ev["h"]}
        if ev.get("g"):
            entry["g"] = ev["g"]
        out.append(entry)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n")
    n_pages = sum(1 for x in out if x["t"] == "Page")
    n_events = sum(1 for x in out if x["t"] == "Event")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(out)} entries "
          f"({n_pages} pages, {len(out) - n_pages - n_events} entities, {n_events} events), "
          f"{OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
