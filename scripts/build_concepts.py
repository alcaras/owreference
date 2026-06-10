#!/usr/bin/env python3
"""
Build src/data/concepts.json from concept.xml — the in-game encyclopedia of
mechanics ("Agent", "Alliance", "Anarchy", …).

Each concept entry carries:
  - GenderedName → genderedText*.xml → TEXT_CONCEPT_* → text-*.xml en-US
  - zHelpText   → TEXT_HELPTEXT_*   → text-helptext*.xml en-US

The help strings use the game's inline markup, which we resolve/clean here:
  - link(TOKEN[,N]) / {lowercase:link(TOKEN,N)} → display name (text index
    lookup of TEXT_<TOKEN>, falling back to humanize-style title-casing)
  - int(GLOBAL)   → value from globalsInt.xml (e.g. int(AGENT_NETWORK_TURNS) → 5)
  - icon(X)/hotkey(X) → dropped / readable key name
  - {YIELD_*}, {MOVEMENT}, {RESOURCE_*} → dropped (icon glyph tokens)
  - {TEXT_*}      → nested include, resolved recursively
  - {bullet}      → "• " list-item prefix
Paragraphs (newlines in en-US) are preserved as a list of strings.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "concepts.json"


def load_full_text_index() -> dict[str, str]:
    """{TEXT_KEY: raw en-US} across every text-*.xml (first definition wins)."""
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("text-*.xml")):
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        for e in root.findall("Entry"):
            k = e.findtext("zType") or ""
            v = e.findtext("en-US")
            if k and v is not None and k not in out:
                out[k] = v
    return out


def load_gendered_names() -> dict[str, str]:
    """{GENDERED_TEXT_X: masculine (first) TEXT key} across genderedText*.xml."""
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("genderedText*.xml")):
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            if not k or k in out:
                continue
            pairs = e.findall(".//Pair")
            # Prefer the masculine form; fall back to the first pair.
            chosen = ""
            for pair in pairs:
                if pair.findtext("zIndex") == "GRAMMATICAL_GENDER_MASCULINE":
                    chosen = pair.findtext("zValue") or ""
                    break
            if not chosen and pairs:
                chosen = pairs[0].findtext("zValue") or ""
            if chosen:
                out[k] = chosen
    return out


def load_globals_int() -> dict[str, str]:
    out: dict[str, str] = {}
    for e in ET.parse(XML_DIR / "globalsInt.xml").getroot().findall("Entry"):
        k = e.findtext("zType") or ""
        v = e.findtext("iValue")
        if k and v is not None:
            out[k] = v.strip()
    return out


def load_dlc_names(text: dict[str, str]) -> dict[str, str]:
    """Map GameContent tokens (EVENTPACK_RELIGION, CALAMITIES, …) to the
    display name of the DLC that ships them, via additionalContent.xml."""
    out: dict[str, str] = {}
    for e in ET.parse(XML_DIR / "additionalContent.xml").getroot().findall("Entry"):
        name_key = e.findtext("Name") or ""
        name = (text.get(name_key) or "").split("~")[0].strip()
        if not name:
            continue
        for v in e.findall("aeGameContent/zValue"):
            if v.text:
                out.setdefault(v.text, name)
    return out


# ── markup cleaning ─────────────────────────────────────────────────────────

LINK_RE = re.compile(r"\{lowercase:link\(([A-Z0-9_]+)(?:,(\d+))?\)\}|\blink\(([A-Z0-9_]+)(?:,(\d+))?\)")
INT_RE = re.compile(r"\bint\(([A-Z0-9_]+)\)")
ICON_RE = re.compile(r"\bicon\(([A-Za-z_]+)\)\s?")
HOTKEY_RE = re.compile(r"\bhotkey\(HOTKEY_([A-Z_]+)\)")
INCLUDE_RE = re.compile(r"\{(TEXT_[A-Z_0-9]+)\}")
GLYPH_RE = re.compile(r"\{[A-Z][A-Z_0-9]*\}\s?")  # {YIELD_X}, {MOVEMENT}, {RESOURCE_X}…


class Cleaner:
    def __init__(self, text: dict[str, str], globals_int: dict[str, str]):
        self.text = text
        self.globals_int = globals_int

    def link_name(self, token: str, form_idx: str | None) -> str:
        """Display name for a link() target: text index first, then a
        humanize-style title-cased fallback (drop the category prefix).
        The optional ,N selects a grammatical form (en-US: 0=singular, 1=plural)."""
        en = self.text.get(f"TEXT_{token}")
        if en:
            forms = [f.strip() for f in en.split("~")]
            i = int(form_idx) if form_idx is not None else 0
            return forms[i] if i < len(forms) else forms[0]
        # Same spirit as humanize._strip_link_templates, but also handles
        # digit-bearing tokens (IMPROVEMENT_THEATER_1) its regex misses.
        parts = token.split("_")
        if len(parts) > 1:
            parts = parts[1:]
        return " ".join(p.title() for p in parts)

    def _clean_pass(self, s: str, depth: int) -> str:
        if depth < 4:
            s = INCLUDE_RE.sub(lambda m: self.clean(self.text.get(m.group(1), ""), depth + 1), s)
        s = LINK_RE.sub(lambda m: self.link_name(m.group(1) or m.group(3) or "",
                                                 m.group(2) if m.group(1) else m.group(4)), s)
        s = INT_RE.sub(lambda m: self.globals_int.get(m.group(1), m.group(1)), s)
        s = HOTKEY_RE.sub(lambda m: " + ".join(w.title() for w in m.group(1).split("_")), s)
        s = ICON_RE.sub("", s)
        s = s.replace("{bullet}", "• ")
        s = GLYPH_RE.sub("", s)  # leftover icon glyph tokens
        return s

    def clean(self, raw: str, depth: int = 0) -> str:
        # Text substituted in from the text index can itself carry link()/glyph
        # markup (e.g. TEXT_MISSION_* strings) — iterate until stable, bounded.
        s = raw
        for _ in range(4):
            nxt = self._clean_pass(s, depth)
            if nxt == s:
                break
            s = nxt
        return s

    def paragraphs(self, raw: str) -> list[str]:
        cleaned = self.clean(raw)
        out: list[str] = []
        for line in cleaned.split("\n"):
            line = re.sub(r"\s+", " ", line).strip()
            line = re.sub(r"\s+([,.):;])", r"\1", line)  # no space before punctuation
            if line:
                out.append(line)
        return out


def main() -> int:
    text = load_full_text_index()
    gendered = load_gendered_names()
    globals_int = load_globals_int()
    dlc_names = load_dlc_names(text)
    cleaner = Cleaner(text, globals_int)

    concepts: list[dict] = []
    skipped: list[dict] = []

    for e in ET.parse(XML_DIR / "concept.xml").getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            skipped.append({"id": "(schema entry)", "reason": "no zType"})
            continue

        # Name: GenderedName → masculine TEXT key → en-US first form
        name = ""
        gn = e.findtext("GenderedName") or ""
        name_key = gendered.get(gn, "")
        if name_key and name_key in text:
            name = cleaner.clean(text[name_key]).split("~")[0].strip()
        if not name:
            skipped.append({"id": zt, "reason": f"no resolvable name (GenderedName={gn or '—'})"})
            continue

        # Help text: zHelpText → en-US, cleaned, split into paragraphs
        help_key = e.findtext("zHelpText") or ""
        paras = cleaner.paragraphs(text[help_key]) if help_key in text else []
        if not paras:
            skipped.append({"id": zt, "reason": f"no help text (zHelpText={help_key or '—'})"})
            continue

        # DLC tag, if any. EVENT_CONTENT_UNAVAILABLE marks disabled content.
        gc = (e.findtext("GameContentRequired") or "").strip()
        if not gc:
            dlc = ""
        elif gc == "EVENT_CONTENT_UNAVAILABLE":
            dlc = "Unavailable"
        else:
            dlc = dlc_names.get(gc, gc.replace("_", " ").title())

        concepts.append({
            "id": zt,
            "slug": zt.removeprefix("CONCEPT_").lower().replace("_", "-"),
            "name": name,
            "help": paras,
            "dlc": dlc,
        })

    concepts.sort(key=lambda c: (c["name"].lower(), c["id"]))

    payload = {
        "_meta": {
            "skipped": sorted(skipped, key=lambda s: s["id"]),
            "skippedCount": len(skipped),
            "source": "concept.xml",
            "total": len(concepts),
        },
        "concepts": concepts,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(concepts)} concepts, {len(skipped)} skipped")
    for s in skipped:
        print(f"  ⤷ skipped {s['id']}: {s['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
