#!/usr/bin/env python3
"""
Build src/data/patchnotes.json — the human-facing patch log.

Two sources, one file:
  1. Mohawk's official build notes (github.com/MohawkGames/main_buildnotes) —
     fetched once and MIRRORED locally so the static build is offline-safe. These
     are the headline (sectioned: Design / Programming / UI / Bugs Fixed / …).
  2. A distilled summary of our own generated-data diff (from CHANGELOG.md) —
     per-file change counts, rendered as the collapsible "verified in game data"
     support so a reader can see the official note is backed by an actual XML move.

The notes file is a flat text doc: a title line ("Main Branch 1.0.N Release DATE"),
then blank-line-delimited blocks that alternate header / bullet-list. Re-running is
idempotent: the current version is upserted into the array (newest first); if the
fetch fails (offline), the existing mirror is kept untouched.

Run as part of `make data` (after the per-dataset builders + changelog).
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "patchnotes.json"
PATCH_JSON = ROOT / "data" / "patch.json"
CHANGELOG = ROOT / "CHANGELOG.md"

NOTES_URL = "https://raw.githubusercontent.com/MohawkGames/main_buildnotes/main/latest_main"

# Changelog line prefixes → bucket.
DIFF_BUCKETS = {"🟢": "added", "🔴": "removed", "✏️": "changed", "🌱": "tracked"}


def fetch_notes() -> str | None:
    try:
        with urllib.request.urlopen(NOTES_URL, timeout=15) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # offline / rate-limited / moved — keep the mirror
        print(f"  ! could not fetch Mohawk notes ({e}); keeping existing mirror", file=sys.stderr)
        return None


def parse_notes(text: str) -> dict | None:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines:
        return None
    title = lines[0].strip()
    version = re.search(r"\b\d+\.\d+\.\d+\b", title)
    date = re.search(r"\d{4}-\d{2}-\d{2}", title)

    # Blank-line-delimited blocks after the title. A single-line block is a
    # section header; a multi-line block is the bullets for the open section.
    blocks: list[list[str]] = []
    cur: list[str] = []
    for ln in lines[1:]:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)

    # A single-line block is a section header; a multi-line block is the bullet
    # list for the section opened just before it.
    sections: list[dict] = []
    for block in blocks:
        if len(block) == 1:
            sections.append({"name": block[0], "items": []})
        else:
            if not sections:
                sections.append({"name": "Notes", "items": []})
            sections[-1]["items"].extend(block)
    return {
        "version": version.group(0) if version else title,
        "date": date.group(0) if date else "",
        "title": title,
        "sections": sections,
    }


def distill_changelog() -> list[dict]:
    """Per-file change counts from the top (most recent) CHANGELOG section."""
    if not CHANGELOG.exists():
        return []
    text = CHANGELOG.read_text()
    # Slice the first "## …" section (newest patch) up to the next "## ".
    parts = re.split(r"^## ", text, flags=re.M)
    if len(parts) < 2:
        return []
    top = parts[1]
    files: list[dict] = []
    cur: dict | None = None
    for ln in top.split("\n"):
        m = re.match(r"^### (.+)$", ln)
        if m:
            cur = {"file": m.group(1).strip(), "added": 0, "removed": 0, "changed": 0, "tracked": 0}
            files.append(cur)
            continue
        if cur is None:
            continue
        for glyph, bucket in DIFF_BUCKETS.items():
            if ln.lstrip().startswith(f"- {glyph}"):
                cur[bucket] += 1
                break
        else:
            if "now tracked" in ln:
                cur["tracked"] += 1
            elif re.match(r"^\s*- ", ln):
                cur["changed"] += 1  # ✏️ regenerated / misc edits
    # Keep only files with real movement; sort by total desc then name.
    out = [f for f in files if (f["added"] + f["removed"] + f["changed"] + f["tracked"])]
    out.sort(key=lambda f: (-(f["added"] + f["removed"] + f["changed"] + f["tracked"]), f["file"]))
    return out


def load_existing() -> list[dict]:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text())
        except Exception:
            return []
    return []


def main() -> int:
    existing = load_existing()
    text = fetch_notes()
    if text is None:
        if existing:
            print(f"✓ kept {OUT.relative_to(ROOT)} — {len(existing)} patch(es)")
            return 0
        print("✗ no notes mirror and fetch failed; writing empty patchnotes.json", file=sys.stderr)
        OUT.write_text("[]\n")
        return 0

    parsed = parse_notes(text)
    if not parsed:
        print("✗ could not parse Mohawk notes", file=sys.stderr)
        return 1

    # Attach our Steam build id + the distilled data diff for this build.
    try:
        patch = json.loads(PATCH_JSON.read_text())
        parsed["buildId"] = patch.get("buildId") or patch.get("version") or ""
        parsed["syncedAt"] = patch.get("syncedAt", "")
    except Exception:
        parsed["buildId"] = ""
    parsed["dataDiff"] = distill_changelog()

    # Upsert by version (newest first).
    by_version = {p.get("version"): p for p in existing}
    by_version[parsed["version"]] = parsed
    merged = sorted(by_version.values(), key=lambda p: p.get("date", ""), reverse=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(merged, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    secs = ", ".join(f"{s['name']} ({len(s['items'])})" for s in parsed["sections"])
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {parsed['version']} ({parsed['date']}): {secs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
