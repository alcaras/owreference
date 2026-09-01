#!/usr/bin/env python3
"""
Build src/data/hints.json — the game's Hints (the one-liners the loading
screen cycles through; the in-game wiki lists them under
TEXT_WIKI_NAV_UI_SECTION_HINTTEXTS "Hints").

Sources (there is no hint.xml — hints exist only as text keys):
  text-hint.xml       TEXT_HINT_*        base game
  text-hint-btt.xml   TEXT_BTT_HINT_*    Behind the Throne
  text-hint-sap.xml   TEXT_SAP_HINT_*    The Sacred and the Profane
  text-eoti.xml       TEXT_INDIA_HINT_*  Empires of the Indus
Plus improvement.xml's <Hint> keys — the build-advice line the game shows on
an improvement's tooltip — kept as a separate section.

Hint text is written in the game's inline markup. We reuse build_concepts'
Cleaner for includes/int()/icon()/glyph handling, but keep every link(TOKEN)
as a *segment* carrying its token, so the page can link each mention to the
entity registry (or to /concepts) instead of guessing from prose.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_concepts import Cleaner, load_full_text_index, load_globals_int  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "hints.json"

# file → (key prefix regex, source label). "" = base game.
HINT_SOURCES = [
    ("text-hint.xml", re.compile(r"^TEXT_HINT_(\d+)$"), ""),
    ("text-hint-btt.xml", re.compile(r"^TEXT_BTT_HINT_(\d+)$"), "Behind the Throne"),
    ("text-hint-sap.xml", re.compile(r"^TEXT_SAP_HINT_(\d+)$"), "Sacred & the Profane"),
    ("text-eoti.xml", re.compile(r"^TEXT_INDIA_HINT_(\d+)$"), "Empires of the Indus"),
]

# Segment markers: survive Cleaner's regex passes (control chars are matched by
# none of them), so link() tokens come back out intact after cleaning.
MARK = "\x01"
SEP = "\x02"
SEG_RE = re.compile(f"{MARK}([A-Z0-9_]+){SEP}([^{MARK}]*){MARK}")


class SegmentingCleaner(Cleaner):
    """Cleaner that leaves link() targets tagged instead of flattened."""

    def __init__(self, text: dict[str, str], globals_int: dict[str, str]):
        super().__init__(text, globals_int)
        # A display name can itself carry markup (TEXT_MISSION_QUELL_DISSENT_
        # ZOROASTRIANISM is "Quell link(RELIGION_ZOROASTRIANISM,1) Dissent"),
        # so flatten it with a plain Cleaner — markers must never nest.
        self.flat = Cleaner(text, globals_int)

    def link_name(self, token: str, form_idx: str | None) -> str:
        name = self.flat.clean(super().link_name(token, form_idx))
        return f"{MARK}{token}{SEP}{name}{MARK}"


def tidy(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s.replace("\n", " "))
    return re.sub(r"\s+([,.):;!?])", r"\1", s).strip()


def segment(cleaned: str) -> list[dict]:
    """Cleaned+marked string → [{text}|{text, ref}] segments."""
    segs: list[dict] = []
    pos = 0
    for m in SEG_RE.finditer(cleaned):
        if m.start() > pos:
            segs.append({"text": cleaned[pos:m.start()]})
        segs.append({"ref": m.group(1), "text": m.group(2)})
        pos = m.end()
    if pos < len(cleaned):
        segs.append({"text": cleaned[pos:]})

    # Collapse whitespace without losing the single spaces between segments.
    out: list[dict] = []
    for i, s in enumerate(segs):
        t = re.sub(r"[ \t]+", " ", s["text"].replace("\n", " "))
        if "ref" not in s:
            t = re.sub(r"\s+([,.):;!?])", r"\1", t)
            if i == 0:
                t = t.lstrip()
            if i == len(segs) - 1:
                t = t.rstrip()
            if not t:
                continue
        out.append({"ref": s["ref"], "text": t} if "ref" in s else {"text": t})
    return out


def build_hint(cleaner: SegmentingCleaner, key: str, raw: str, num: int, dlc: str) -> dict:
    segs = segment(cleaner.clean(raw))
    return {
        "id": key,
        "num": num,
        "dlc": dlc,
        "slug": key.removeprefix("TEXT_").lower().replace("_", "-"),
        "segments": segs,
        "text": tidy("".join(s["text"] for s in segs)),
        "refs": sorted({s["ref"] for s in segs if "ref" in s}),
    }


def main() -> int:
    text = load_full_text_index()
    cleaner = SegmentingCleaner(text, load_globals_int())

    hints: list[dict] = []
    skipped: list[dict] = []

    for fname, key_re, dlc in HINT_SOURCES:
        path = XML_DIR / fname
        # ET drops XML comments, so hints the designers commented out
        # ("No longer applicable" in text-hint.xml) never reach us.
        for e in ET.parse(path).getroot().findall("Entry"):
            key = e.findtext("zType") or ""
            m = key_re.match(key)
            if not m:
                continue
            raw = e.findtext("en-US") or ""
            if not raw.strip():
                skipped.append({"id": key, "reason": "empty en-US"})
                continue
            hints.append(build_hint(cleaner, key, raw, int(m.group(1)), dlc))

    hints.sort(key=lambda h: (h["dlc"], h["num"]))

    # Improvement tooltip hints — improvement.xml <Hint> → text key.
    improvements: list[dict] = []
    for e in ET.parse(XML_DIR / "improvement.xml").getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        hint_key = e.findtext("Hint") or ""
        if not zt or not hint_key:
            continue
        raw = text.get(hint_key, "")
        if not raw.strip():
            skipped.append({"id": hint_key, "reason": "no en-US for improvement Hint"})
            continue
        name = tidy(cleaner.flat.clean(text.get(f"TEXT_{zt}", zt))).split("~")[0].strip()
        segs = segment(cleaner.clean(raw))
        improvements.append({
            "id": zt,
            "name": name,
            "slug": zt.removeprefix("IMPROVEMENT_").lower().replace("_", "-"),
            "segments": segs,
            "text": tidy("".join(s["text"] for s in segs)),
            "refs": sorted({s["ref"] for s in segs if "ref" in s}),
        })
    improvements.sort(key=lambda i: i["name"].lower())

    payload = {
        "_meta": {
            "improvementHints": len(improvements),
            "skipped": sorted(skipped, key=lambda s: s["id"]),
            "source": "text-hint.xml, text-hint-btt.xml, text-hint-sap.xml, text-eoti.xml, improvement.xml",
            "total": len(hints),
        },
        "hints": hints,
        "improvementHints": improvements,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(hints)} hints "
          f"+ {len(improvements)} improvement hints, {len(skipped)} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
