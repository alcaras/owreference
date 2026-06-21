#!/usr/bin/env python3
"""
Structured, human-readable diff between two generated-data trees.

Unlike changelog.py (which emits exhaustive markdown for the full CHANGELOG),
this yields compact per-entry records suited to the patch-notes page:

    {"file": "technologies", "entity": "Aristocracy", "kind": "changed",
     "detail": "cost: 150 → 160", "text": "technologies aristocracy cost 150 160"}

`text` is a lowercased bag of words used to correlate a record against an
official patch-note line. Derived registries (entities/backlinks/search) and the
event-search index are skipped — they re-derive from the primary datasets.
"""
from __future__ import annotations

import json
from pathlib import Path

ID_KEYS = ("id", "key", "slug", "label", "name")
SKIP = {
    "entities.json", "backlinks.json", "event-search.json", "event-chains.json",
    "patchnotes.json", "continent-maps.json",
}


def _label(item) -> str:
    if isinstance(item, dict):
        for k in ("name", "label", "deity", "title", "id", "key", "slug"):
            v = item.get(k)
            if isinstance(v, (str, int)) and str(v).strip():
                return str(v).replace("EVENTSTORY_", "").replace("_", " ")
        return ""  # an unlabelled object — caller renders it as "an entry"
    return str(item)


def _short(v) -> str:
    if isinstance(v, dict):
        return _label(v) or "an entry"
    if isinstance(v, list):
        return ", ".join(_short(x) for x in v[:3]) + ("…" if len(v) > 3 else "")
    s = str(v)
    return s if len(s) <= 60 else s[:57] + "…"


def _pick_id_key(items: list) -> str | None:
    rows = [it for it in items if isinstance(it, dict)]
    if not rows:
        return None
    for k in ID_KEYS:
        vals = [it.get(k) for it in rows if k in it]
        if len(vals) == len(rows) and all(isinstance(v, (str, int)) for v in vals) and len(set(vals)) == len(vals):
            return k
    return None


def _diff_entity(file: str, entity: str, p: dict, c: dict, out: list) -> None:
    """Field-level diff of one entity dict → records."""
    for k in sorted(set(p) | set(c)):
        pv, cv = p.get(k), c.get(k)
        if pv == cv:
            continue
        if isinstance(pv, list) and isinstance(cv, list):
            added = [x for x in cv if x not in pv]
            removed = [x for x in pv if x not in cv]
            if len(added) == 1 and len(removed) == 1:
                # A single value swapped — show before → after (e.g. a cost).
                la, lb = _short(removed[0]), _short(added[0])
                detail = f"{k}: {la} updated" if la == lb else f"{k}: {la} → {lb}"
                out.append(_rec(file, entity, "changed", detail))
            else:
                # Pair by label: same label both sides = edited; otherwise add/remove.
                add_by = {_short(a): a for a in added}
                rem_by = {_short(r): r for r in removed}
                for lbl in sorted(add_by.keys() & rem_by.keys()):
                    out.append(_rec(file, entity, "changed", f"{k}: {lbl} updated"))
                for lbl in sorted(add_by.keys() - rem_by.keys()):
                    out.append(_rec(file, entity, "added", f"{k}: {lbl}"))
                for lbl in sorted(rem_by.keys() - add_by.keys()):
                    out.append(_rec(file, entity, "removed", f"{k}: {lbl}"))
        elif isinstance(pv, dict) and isinstance(cv, dict):
            _diff_entity(file, f"{entity} · {k}", pv, cv, out)
        else:
            out.append(_rec(file, entity, "changed", f"{k}: {_short(pv)} → {_short(cv)}"))


def _rec(file: str, entity: str, kind: str, detail: str) -> dict:
    text = f"{file} {entity} {detail}".lower()
    return {"file": file, "entity": entity, "kind": kind, "detail": detail, "text": text}


def _diff_value(file: str, name: str, prev, cur, out: list) -> None:
    """Top-level value diff (list-of-dicts indexed by id, or nested dict)."""
    if isinstance(prev, list) and isinstance(cur, list):
        idk = _pick_id_key(cur) or _pick_id_key(prev)
        if not idk:
            return
        p = {it[idk]: it for it in prev if isinstance(it, dict) and idk in it}
        c = {it[idk]: it for it in cur if isinstance(it, dict) and idk in it}
        for eid in sorted(set(c) - set(p), key=str):
            out.append(_rec(file, _label(c[eid]), "added", "new entry"))
        for eid in sorted(set(p) - set(c), key=str):
            out.append(_rec(file, _label(p[eid]), "removed", "removed entry"))
        for eid in sorted(set(p) & set(c), key=str):
            _diff_entity(file, _label(c[eid]), p[eid], c[eid], out)
    elif isinstance(prev, dict) and isinstance(cur, dict):
        _diff_entity(file, name, prev, cur, out)


def diff_dirs(before: Path, after: Path) -> list[dict]:
    out: list[dict] = []
    for path in sorted(after.glob("*.json")):
        if path.name in SKIP:
            continue
        prev_path = before / path.name
        if not prev_path.exists():
            continue
        try:
            prev = json.loads(prev_path.read_text())
            cur = json.loads(path.read_text())
        except Exception:
            continue
        if prev == cur:
            continue
        _diff_value(path.stem, path.stem, prev, cur, out)
    return out


if __name__ == "__main__":
    import sys
    recs = diff_dirs(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(recs, indent=2, ensure_ascii=False))
    print(f"\n{len(recs)} records", file=sys.stderr)
