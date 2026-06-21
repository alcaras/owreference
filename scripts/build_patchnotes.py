#!/usr/bin/env python3
"""
Build src/data/patchnotes.json — the human-facing patch log.

Mohawk's official build notes (github.com/MohawkGames/main_buildnotes) are the
headline, mirrored locally so the static build is offline-safe. Against them we
correlate our own XML-derived data diff: each official note is paired with the
generated-data entries that actually moved (tech costs, improvement costs, …),
and anything that changed in the data but ISN'T mentioned in the notes is listed
separately. The diff is computed from the data SNAPSHOTS (current patch vs the
previous one) so it reflects game-XML changes, not reference-site code tweaks.

Run as part of `make changelog` (after changelog.py writes the new snapshot).
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_diff import diff_dirs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "patchnotes.json"
PATCH_JSON = ROOT / "data" / "patch.json"
SNAPS = ROOT / "data" / "snapshots"

NOTES_URL = "https://raw.githubusercontent.com/MohawkGames/main_buildnotes/main/latest_main"

# Words too generic to be a correlation signal on their own.
STOP = {
    "the", "and", "for", "with", "was", "are", "were", "your", "their", "when",
    "that", "this", "from", "now", "not", "have", "has", "been", "they", "than",
    "units", "unit", "city", "cities", "player", "players", "turn", "turns",
    "cost", "costs", "tier", "more", "less", "each", "some", "only", "give",
    "gives", "given", "wood", "tech", "techs", "updated", "true", "false",
    "entry", "military", "urban", "improvements", "improvement", "leader",
    "general", "character", "helptext", "fixed", "event", "events", "trait",
    "traits", "effect", "level", "added", "removed", "changed", "orders",
    "button", "option", "range", "ability", "abilities", "modifier", "units",
}
# Datasets whose top-level "entity" is just the dataset name — not a specific
# named thing, so don't phrase-match on it (rely on numbers / value words).
GENERIC_ENTITY = {
    "subjects", "ambitions", "concepts", "occurrences", "traits", "events", "missions",
}


def fetch_notes() -> str | None:
    try:
        with urllib.request.urlopen(NOTES_URL, timeout=15) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  ! could not fetch Mohawk notes ({e}); keeping existing mirror", file=sys.stderr)
        return None


def parse_notes(text: str) -> dict | None:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines:
        return None
    title = lines[0].strip()
    version = re.search(r"\b\d+\.\d+\.\d+\b", title)
    date = re.search(r"\d{4}-\d{2}-\d{2}", title)

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


# ── Correlation ─────────────────────────────────────────────────────────────

def _caps(text: str) -> set[str]:
    """Proper-noun-ish words (Capitalised, 5+ letters) — distinctive enough to
    correlate on. Lowercased for comparison. 'Plague'/'Ranger' qualify; a stray
    lowercase 'attack' in prose does not."""
    return {w.lower() for w in re.findall(r"\b[A-Z][a-z]{4,}\b", text)} - STOP


def note_signals(text: str) -> tuple[set[str], set[str]]:
    return _caps(text), set(re.findall(r"\d{2,}", text))


def record_signals(rec: dict) -> tuple[str | None, set[str], set[str]]:
    """(entity phrase for substring-match, proper-noun value words, numbers)."""
    ent = rec["entity"].split(" · ")[0].strip().lower()
    phrase = ent if (ent and ent not in GENERIC_ENTITY and ent != rec["file"].rstrip("s")) else None
    value = rec["detail"].split(":", 1)[1] if ":" in rec["detail"] else rec["detail"]
    return phrase, _caps(value), set(re.findall(r"\d{2,}", rec["detail"]))


def correlate(note: str, recs: list[dict]) -> list[int]:
    """Indices of records that plausibly back this note."""
    nc, nn = note_signals(note)
    low = note.lower()
    hits: list[int] = []
    for i, r in enumerate(recs):
        phrase, rc, rn = record_signals(r)
        # A specific entity name verbatim in the note, OR ≥2 shared multi-digit
        # numbers (cost tweaks), OR a shared proper-noun word (Plague, Ranger…).
        if (phrase and phrase in low) or len(rn & nn) >= 2 or (rc & nc):
            hits.append(i)
    return hits


def baseline_snapshot(build_id: str) -> Path | None:
    if not SNAPS.exists():
        return None
    cands = [d for d in SNAPS.iterdir() if d.is_dir() and d.name != build_id]
    return max(cands, key=lambda d: d.name) if cands else None


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
        OUT.write_text("[]\n")
        return 0

    parsed = parse_notes(text)
    if not parsed:
        print("✗ could not parse Mohawk notes", file=sys.stderr)
        return 1

    try:
        patch = json.loads(PATCH_JSON.read_text())
        parsed["buildId"] = patch.get("buildId") or patch.get("version") or ""
        parsed["syncedAt"] = patch.get("syncedAt", "")
    except Exception:
        parsed["buildId"] = ""

    # Clean XML diff: current data vs the previous patch's snapshot.
    base = baseline_snapshot(parsed["buildId"])
    recs = diff_dirs(base, ROOT / "src" / "data") if base else []
    used = [False] * len(recs)

    def slim(r: dict) -> dict:
        return {"file": r["file"], "entity": r["entity"], "kind": r["kind"], "detail": r["detail"]}

    for sec in parsed["sections"]:
        items = []
        for note in sec["items"]:
            related = correlate(note, recs)
            for i in related:
                used[i] = True
            items.append({"text": note, "related": [slim(recs[i]) for i in related]})
        sec["items"] = items

    # Anything that moved in the data but no note mentioned → "other changes".
    other: dict[str, list] = {}
    for i, r in enumerate(recs):
        if not used[i]:
            other.setdefault(r["file"], []).append(slim(r))
    parsed["otherChanges"] = [
        {"file": f, "records": rs} for f, rs in sorted(other.items())
    ]

    by_version = {p.get("version"): p for p in existing}
    by_version[parsed["version"]] = parsed
    merged = sorted(by_version.values(), key=lambda p: p.get("date", ""), reverse=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(merged, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    correlated = sum(used)
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {parsed['version']}: "
          f"{len(recs)} data changes ({correlated} correlated, {len(recs) - correlated} other)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
