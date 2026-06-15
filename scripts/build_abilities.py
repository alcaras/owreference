#!/usr/bin/env python3
"""
Build src/data/abilities.json from units.json.

Every named special ability a unit can carry (Disarm, Testudo, Rout, Splash …)
becomes one entry with: its humanized description lines (from
build_unit_damage's describe_effect), its icon, and the roster of units that
have it — so each ability gets a detail page and the unit pages can link to it.

Abilities are derived from units.json (the `abilities` field), which already
filtered out pure stat-extra effects (e.g. EXTRA_VISION). This script just
groups them and attaches the unit backlinks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNITS = ROOT / "src" / "data" / "units.json"
OUT = ROOT / "src" / "data" / "abilities.json"


def main() -> int:
    units = json.loads(UNITS.read_text())

    by_slug: dict[str, dict] = {}
    for u in units:
        for a in u.get("abilities", []):
            slug = a["slug"]
            entry = by_slug.get(slug)
            if entry is None:
                entry = by_slug[slug] = {
                    "slug": slug,
                    "id": a["id"],
                    "label": a["label"],
                    "icon": a.get("icon"),
                    "lines": a.get("lines", []),
                    "units": [],
                }
            # Keep the richest description seen (some units share an effect id
            # but the lines are identical; this is just defensive).
            if len(a.get("lines", [])) > len(entry["lines"]):
                entry["lines"] = a["lines"]
            entry["units"].append({
                "id": u["id"],
                "slug": u["slug"],
                "name": u["name"],
                "iconSlug": u["iconSlug"],
                "nationLabel": u.get("nationLabel", ""),
                "category": u.get("category", "normal"),
                "era": u.get("era", ""),
                "source": u.get("source", "Base game"),
            })

    abilities = sorted(by_slug.values(), key=lambda a: a["label"].lower())
    for a in abilities:
        a["units"].sort(key=lambda x: (x["category"] != "unique", x["nationLabel"], x["name"]))

    out = {
        "abilities": abilities,
        "totals": {
            "abilities": len(abilities),
            "described": sum(1 for a in abilities if a["lines"]),
        },
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(abilities)} abilities "
          f"({out['totals']['described']} described)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
