#!/usr/bin/env python3
"""Post-build prose check: the mechanical tells of the writing rules in CLAUDE.md
("Writing rules"), measured on the text a reader actually sees in dist/.

Fails (exit 1) on:
  · a source citation in visible text ("Game.cs:13611", "Unit.cs", "HelpText.Bonus.cs")
    — citations belong in the builder docstring and the commit message (rule 8)
  · a "Where this comes from" section (rule 8)
Warns on:
  · a lede (first .lede paragraph, else the first paragraph of the page body)
    longer than 60 words — a lede says what the page is for, it is not a summary (rule 1)
  · code vocabulary in prose: "asserted", "dead code", "bDebug", method calls
    like getReligionSpread() (rule 2)

Usage: python3 scripts/audit_prose.py [--dist DIR] [--only REGEX] [--strict]
--strict turns warnings into failures.
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CITATION = re.compile(r"\b[A-Z][A-Za-z]*(?:\.[A-Z][A-Za-z]*)*\.cs\b(?::\d+)?")
SOURCES_HEADING = re.compile(r"where this comes from", re.I)
CODE_WORDS = re.compile(r"\b(asserted|dead code|bDebug)\b|\b[a-z]+[A-Z][A-Za-z]+\(\)")
LEDE_MAX_WORDS = 60
SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


class Visible(HTMLParser):
    """Collects visible text, the page's lede, and whether we are inside
    <code>/<pre> (field names in code spans are allowed; citations are not)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.text: list[str] = []
        self.lede: list[str] | None = None
        self.in_lede = 0
        self.first_p: list[str] | None = None
        self.in_p = 0
        self.in_main = False
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP_TAGS:
            self.skip += 1
        if "hidden" in a or a.get("aria-hidden") == "true":
            if tag not in ("br", "img", "input"):
                self.hidden += 1
                self._hid_tag = tag
        if tag == "main":
            self.in_main = True
        cls = (a.get("class") or "").split()
        if tag == "p" and "lede" in cls and self.lede is None:
            self.lede, self.in_lede = [], 1
        elif self.in_lede and tag == "p":
            self.in_lede += 1
        if tag == "p" and self.in_main and self.first_p is None:
            self.first_p, self.in_p = [], 1

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip:
            self.skip -= 1
        if self.hidden and tag == getattr(self, "_hid_tag", None):
            self.hidden -= 1
        if tag == "p":
            if self.in_lede:
                self.in_lede -= 1
            if self.in_p:
                self.in_p = 0

    def handle_data(self, data):
        if self.skip or self.hidden:
            return
        self.text.append(data)
        if self.in_lede and self.lede is not None:
            self.lede.append(data)
        if self.in_p and self.first_p is not None:
            self.first_p.append(data)


def main() -> int:
    args = sys.argv[1:]
    dist = Path(args[args.index("--dist") + 1]) if "--dist" in args else ROOT / "dist"
    only = re.compile(args[args.index("--only") + 1]) if "--only" in args else None
    strict = "--strict" in args
    fails: list[str] = []
    warns: list[str] = []
    pages = 0
    for html in sorted(dist.rglob("index.html")):
        rel = str(html.parent.relative_to(dist)) or "/"
        if only and not only.search(rel):
            continue
        raw = html.read_text(errors="replace")
        if 'http-equiv="refresh"' in raw:
            continue
        pages += 1
        v = Visible()
        v.feed(raw)
        text = " ".join(" ".join(v.text).split())
        for m in sorted(set(CITATION.findall(text))):
            fails.append(f"{rel}: source citation in visible text: {m}")
        if SOURCES_HEADING.search(text):
            fails.append(f"{rel}: a 'Where this comes from' section")
        lede = " ".join((v.lede if v.lede is not None else (v.first_p or []))).split()
        if len(lede) > LEDE_MAX_WORDS:
            warns.append(f"{rel}: lede is {len(lede)} words (max {LEDE_MAX_WORDS}): {' '.join(lede[:12])}…")
        for m in sorted(set(x if isinstance(x, str) else (x[0] or x) for x in CODE_WORDS.findall(text))):
            if m:
                warns.append(f"{rel}: code vocabulary in prose: {m!r}")

    for f in fails:
        print(f"✗ {f}")
    for w in warns:
        print(f"⚠ {w}")
    bad = len(fails) + (len(warns) if strict else 0)
    print(f"{'✗' if bad else '✓'} prose audit: {pages} pages, {len(fails)} failure(s), {len(warns)} warning(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
