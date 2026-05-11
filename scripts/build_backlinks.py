#!/usr/bin/env python3
"""
Scan all generated data JSON for entity references; produce
src/data/backlinks.json keyed by entity id.

Each backlink entry: { page, context, text }
  - page: slug of the referring page (e.g. "nations")
  - context: short location label (e.g. "Assyria · Bonus 1")
  - text: the surrounding text that mentioned the entity (for preview)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
OUT = DATA / "backlinks.json"


def load(name: str):
    p = DATA / name
    if not p.exists():
        return None
    return json.loads(p.read_text())


def build_alias_pattern(entities_payload: dict) -> tuple[re.Pattern[str], dict[str, str]]:
    alias_to_id: dict[str, str] = {}
    for item in entities_payload["aliasIndex"]:
        alias_to_id.setdefault(item["alias"], item["id"])
    escaped = sorted(alias_to_id.keys(), key=lambda s: -len(s))
    pat = re.compile(
        r"(?<![A-Za-z0-9])(" + "|".join(re.escape(a) for a in escaped) + r")(?![A-Za-z0-9])"
    )
    return pat, alias_to_id


def scan_text(text: str, pat: re.Pattern[str], alias_to_id: dict[str, str]) -> set[str]:
    if not text:
        return set()
    return {alias_to_id[m.group(1)] for m in pat.finditer(text) if m.group(1) in alias_to_id}


def scan_nations(nations: list[dict], pat, alias_to_id, backlinks: defaultdict) -> None:
    # Build per-cell contexts: "Aksum · Bonus 1", etc.
    targets = [
        ("bonuses", "Bonus"),
        ("shrines", "Shrine"),
        ("startingTech", "Tech"),
        ("startingLaw", "Law"),
    ]
    for n in nations:
        nation_name = n["name"]
        slug = n.get("slug", "")
        # link to the nation itself (column header anchor)
        for field, label_prefix in targets:
            for i, val in enumerate(n.get(field, []) or []):
                if not val:
                    continue
                ctx = f"{nation_name} · {label_prefix} {i + 1}"
                for eid in scan_text(str(val), pat, alias_to_id):
                    backlinks[eid].append({
                        "page": "nations", "anchor": slug,
                        "context": ctx, "text": str(val)[:120],
                    })
        # UU
        uu = n.get("uniqueUnit") or {}
        for k, v in uu.items():
            if not v:
                continue
            ctx = f"{nation_name} · UU {k}"
            for eid in scan_text(str(v), pat, alias_to_id):
                backlinks[eid].append({
                    "page": "nations", "anchor": slug,
                    "context": ctx, "text": str(v)[:120],
                })
        # Families
        for fam in n.get("families", []) or []:
            ctx = f"{nation_name} · Family {fam.get('class', '')}"
            for eid in scan_text(str(fam.get("name", "")) + " " + str(fam.get("class", "")),
                                 pat, alias_to_id):
                backlinks[eid].append({
                    "page": "nations", "anchor": slug,
                    "context": ctx, "text": f"{fam.get('class')} ({fam.get('name')})",
                })
        # Leader
        leader = n.get("leader") or {}
        for k, v in leader.items():
            if v:
                for eid in scan_text(str(v), pat, alias_to_id):
                    backlinks[eid].append({
                        "page": "nations", "anchor": slug,
                        "context": f"{nation_name} · {k}",
                        "text": str(v)[:120],
                    })


def main() -> int:
    entities_payload = load("entities.json")
    if not entities_payload:
        print("✗ entities.json missing — run build_entities.py first")
        return 1

    nations = load("nations.json") or []

    pat, alias_to_id = build_alias_pattern(entities_payload)
    backlinks: defaultdict[str, list[dict]] = defaultdict(list)

    scan_nations(nations, pat, alias_to_id, backlinks)

    # Dedupe (same page, context, text)
    deduped: dict[str, list[dict]] = {}
    for eid, refs in backlinks.items():
        seen = set()
        unique = []
        for r in refs:
            k = (r["page"], r["context"], r["text"])
            if k in seen:
                continue
            seen.add(k)
            unique.append(r)
        deduped[eid] = unique

    OUT.write_text(json.dumps(deduped, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — backlinks for {len(deduped)} entities")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
