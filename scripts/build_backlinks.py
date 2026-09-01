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


# Where each entity TYPE's overview page lives (with per-item #slug anchors), so
# a backlink lands on the referring item. Differs from the entity's own `page`
# (which may be a detail route) — backlinks want the anchored overview.
BACKLINK_PAGE = {
    "law": "laws", "tech": "technologies", "unit": "units", "wonder": "wonders",
    "theology": "theologies", "shrine": "shrines", "archetype": "archetypes",
    "family": "families", "project": "projects", "promotion": "promotions",
    "tribe": "tribes", "resource": "resources", "improvement": "urban-improvements",
    "trait": "traits", "nation": "nations",
}
TYPE_LABEL = {
    "law": "Law", "tech": "Technology", "unit": "Unit", "wonder": "Wonder",
    "theology": "Theology", "shrine": "Shrine", "archetype": "Archetype",
    "family": "Family", "project": "Project", "promotion": "Promotion",
    "tribe": "Tribe", "resource": "Resource", "improvement": "Improvement",
}

# Content data files to scan for cross-references. Any record carrying an `id`
# that's in the registry becomes a "referrer"; aliases found anywhere in that
# record's JSON become backlinks pointing at it. Nations get richer per-cell
# contexts via scan_nations, so they're excluded here.
CONTENT_FILES = [
    "laws.json", "technologies.json", "units.json", "wonders.json",
    "theologies.json", "shrines.json", "traits.json", "archetypes.json",
    "families.json", "projects.json", "rural_improvements.json",
    "urban_improvements.json", "promotions.json", "tribes.json",
    "resources.json", "specialists.json",
]


def scan_hints(hints_payload: dict, reg: dict, backlinks) -> None:
    """Hints carry the game's own link() targets in `refs`, so their backlinks
    are exact — no alias matching needed."""
    if not hints_payload:
        return
    for h in hints_payload.get("hints", []):
        label = f"Hint {h['num']}" + (f" · {h['dlc']}" if h["dlc"] else "")
        for tid in h.get("refs", []):
            if tid in reg:
                backlinks[tid].append({
                    "page": "hints", "anchor": h["slug"],
                    "context": label, "text": h["text"],
                })
    for i in hints_payload.get("improvementHints", []):
        for tid in i.get("refs", []):
            if tid in reg and tid != i["id"]:
                backlinks[tid].append({
                    "page": "hints", "anchor": f"hint-{i['slug']}",
                    "context": f"{i['name']} hint", "text": i["text"],
                })


def walk_and_scan(node, reg: dict, pat, alias_to_id, backlinks) -> None:
    """Recursively find registry-id records; scan each for OTHER entity aliases
    and record a backlink to that record's overview page."""
    if isinstance(node, dict):
        eid = node.get("id")
        ref = reg.get(eid) if isinstance(eid, str) else None
        if ref and ref["type"] in BACKLINK_PAGE:
            text = json.dumps(node, ensure_ascii=False)
            page = BACKLINK_PAGE[ref["type"]]
            for tid in scan_text(text, pat, alias_to_id):
                if tid == eid:
                    continue  # don't backlink an item to itself
                backlinks[tid].append({
                    "page": page,
                    "anchor": ref["slug"],
                    "context": ref["name"],
                    "text": TYPE_LABEL.get(ref["type"], ""),
                })
        for v in node.values():
            walk_and_scan(v, reg, pat, alias_to_id, backlinks)
    elif isinstance(node, list):
        for v in node:
            walk_and_scan(v, reg, pat, alias_to_id, backlinks)


def main() -> int:
    entities_payload = load("entities.json")
    if not entities_payload:
        print("✗ entities.json missing — run build_entities.py first")
        return 1

    nations = load("nations.json") or []

    pat, alias_to_id = build_alias_pattern(entities_payload)
    backlinks: defaultdict[str, list[dict]] = defaultdict(list)

    scan_nations(nations, pat, alias_to_id, backlinks)

    # Comprehensive cross-reference scan across all content data files.
    reg = {e["id"]: e for e in entities_payload["entities"]}
    for fname in CONTENT_FILES:
        data = load(fname)
        if data is not None:
            walk_and_scan(data, reg, pat, alias_to_id, backlinks)

    scan_hints(load("hints.json"), reg, backlinks)

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
