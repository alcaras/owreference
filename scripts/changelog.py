#!/usr/bin/env python3
"""
Diff the current src/data/*.json against the most recent snapshot in
data/snapshots/, then:
  1. Save the new snapshot tagged with the current patch version
  2. Prepend a section to CHANGELOG.md describing what changed, grouped by file

Tracks EVERY generated dataset automatically — a new build_*.py output joins
the changelog the first time `make changelog` runs after it exists.

Run after `make data`.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "src" / "data"
SNAPS = ROOT / "data" / "snapshots"
PATCH_JSON = ROOT / "data" / "patch.json"
CHANGELOG = ROOT / "CHANGELOG.md"

# Derived registries: diffing entry-by-entry is pure noise (they re-derive from
# the other files), so only report count-level changes for these.
SUMMARY_ONLY = {"entities.json", "backlinks.json", "continent-maps.json"}

# Keys we try (in order) to index a list-of-dicts dataset by.
ID_KEYS = ("id", "key", "slug", "label", "name")

# Per-file cap on changelog lines so one reworked dataset can't drown the rest.
MAX_LINES_PER_FILE = 120


def tracked_files() -> list[str]:
    return sorted(p.name for p in DATA_DIR.glob("*.json"))


def load_patch_meta() -> dict:
    if PATCH_JSON.exists():
        return json.loads(PATCH_JSON.read_text())
    return {"version": "unknown", "syncedAt": datetime.now(timezone.utc).isoformat()}


def load_previous() -> tuple[str | None, Path | None]:
    """Return (version, dir) of the most recent snapshot, or (None, None)."""
    if not SNAPS.exists():
        return None, None
    snaps = sorted([p for p in SNAPS.iterdir() if p.is_dir()])
    if not snaps:
        return None, None
    return snaps[-1].name, snaps[-1]


def pick_id_key(items: list) -> str | None:
    if not items or not all(isinstance(it, dict) for it in items):
        return None
    for k in ID_KEYS:
        vals = [it.get(k) for it in items]
        if all(isinstance(v, (str, int)) for v in vals) and len(set(vals)) == len(vals):
            return k
    return None


def entry_label(item: dict, id_key: str) -> str:
    return str(item.get("name") or item.get("label") or item.get(id_key))


def diff_dict(p: dict, c: dict, path: str) -> list[str]:
    out: list[str] = []
    for k in sorted(set(p) | set(c)):
        pv, cv = p.get(k), c.get(k)
        if pv == cv:
            continue
        if isinstance(pv, list) and isinstance(cv, list):
            added = [x for x in cv if x not in pv]
            removed = [x for x in pv if x not in cv]
            for a in added:
                out.append(f"- 🟢 **{path}** · `{k}` added: {fmt(a)}")
            for r in removed:
                out.append(f"- 🔴 **{path}** · `{k}` removed: {fmt(r)}")
        elif isinstance(pv, dict) and isinstance(cv, dict):
            out.extend(diff_dict(pv, cv, f"{path} · {k}"))
        else:
            out.append(f"- ✏️ **{path}** · `{k}`: `{fmt(pv)}` → `{fmt(cv)}`")
    return out


def diff_list(prev: list, cur: list) -> list[str]:
    """Diff two list datasets; per-entry when an id key exists, coarse otherwise."""
    id_key = pick_id_key(cur) or pick_id_key(prev)
    if not id_key:
        if prev != cur:
            return [f"- ✏️ contents changed ({len(prev)} → {len(cur)} entries)"]
        return []
    p = {it[id_key]: it for it in prev if isinstance(it, dict) and id_key in it}
    c = {it[id_key]: it for it in cur if isinstance(it, dict) and id_key in it}
    lines: list[str] = []
    for eid in sorted(set(c) - set(p), key=str):
        lines.append(f"- ➕ **{entry_label(c[eid], id_key)}** added")
    for eid in sorted(set(p) - set(c), key=str):
        lines.append(f"- ➖ **{entry_label(p[eid], id_key)}** removed")
    for eid in sorted(set(p) & set(c), key=str):
        lines.extend(diff_dict(p[eid], c[eid], entry_label(c[eid], id_key)))
    return lines


def summarize(prev, cur) -> list[str]:
    def size(d):
        if isinstance(d, list):
            return len(d)
        if isinstance(d, dict):
            inner = d.get("entities")
            return len(inner) if isinstance(inner, (list, dict)) else len(d)
        return 0
    if prev == cur:
        return []
    return [f"- ✏️ regenerated ({size(prev)} → {size(cur)} entries)"]


def fmt(v) -> str:
    if isinstance(v, dict):
        return ", ".join(f"{k}={fmt(vv)}" for k, vv in sorted(v.items()))
    s = str(v)
    return s if len(s) < 80 else s[:77] + "..."


def save_snapshot(version: str, files: list[str]) -> Path:
    snap = SNAPS / version
    snap.mkdir(parents=True, exist_ok=True)
    for f in files:
        src = DATA_DIR / f
        if src.exists():
            content = json.loads(src.read_text())
            (snap / f).write_text(
                json.dumps(content, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            )
    return snap


def prepend_changelog(version: str, ts: str, lines: list[str]) -> None:
    header = f"## {version} — {ts}\n\n"
    body = "\n".join(lines) if lines else "_No data changes._"
    block = header + body + "\n\n"

    if CHANGELOG.exists():
        existing = CHANGELOG.read_text()
        # Drop existing entry for the same version (re-runs replace, don't stack)
        marker = f"\n## {version} —"
        if marker in existing:
            head, _, rest = existing.partition(marker)
            next_section = rest.find("\n## ")
            if next_section >= 0:
                existing = head + rest[next_section + 1:]
            else:
                existing = head.rstrip() + "\n"
    else:
        existing = "# Changelog\n\nGenerated by `scripts/changelog.py`. Each entry diffs the canonical data against the previous patch snapshot.\n\n"

    if existing.startswith("# Changelog"):
        head, _, tail = existing.partition("\n")
        parts = tail.split("\n\n", 2)
        if len(parts) >= 2:
            intro = parts[0]
            body_after = "\n\n".join(parts[1:])
            new = f"{head}\n{intro}\n\n{block}{body_after}".rstrip() + "\n"
        else:
            new = f"{head}\n{tail}\n{block}".rstrip() + "\n"
    else:
        new = block + existing

    CHANGELOG.write_text(new)


def main() -> int:
    meta = load_patch_meta()
    version = meta.get("version", "unknown")
    ts = meta.get("syncedAt", datetime.now(timezone.utc).isoformat())

    files = tracked_files()
    prev_version, prev_dir = load_previous()

    lines: list[str] = []
    total = 0
    for f in files:
        cur = json.loads((DATA_DIR / f).read_text())
        prev_path = prev_dir / f if prev_dir else None
        if prev_path is None or not prev_path.exists():
            n = len(cur) if isinstance(cur, (list, dict)) else 1
            lines.append(f"### {f}\n- 🌱 now tracked ({n} entries)")
            total += 1
            continue
        prev = json.loads(prev_path.read_text())
        if f in SUMMARY_ONLY:
            file_lines = summarize(prev, cur)
        elif isinstance(prev, list) and isinstance(cur, list):
            file_lines = diff_list(prev, cur)
        elif isinstance(prev, dict) and isinstance(cur, dict):
            file_lines = diff_dict(prev, cur, f.removesuffix(".json"))
        else:
            file_lines = [f"- ✏️ structure changed"] if prev != cur else []
        if file_lines:
            shown = file_lines[:MAX_LINES_PER_FILE]
            if len(file_lines) > MAX_LINES_PER_FILE:
                shown.append(f"- … and {len(file_lines) - MAX_LINES_PER_FILE} more changes")
            lines.append(f"### {f}\n" + "\n".join(shown))
            total += len(file_lines)

    snap = save_snapshot(version, files)
    print(f"✓ snapshot: {snap.relative_to(ROOT)} ({len(files)} files)")

    prepend_changelog(version, ts, lines)
    print(f"✓ changelog: {CHANGELOG.relative_to(ROOT)} — {total} change line(s) across {len(lines)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
