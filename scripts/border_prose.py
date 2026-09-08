#!/usr/bin/env python3
"""Round-trip the Border Expansion page's prose through a markdown file.

    python3 scripts/border_prose.py export > border-expansion-prose.md
    python3 scripts/border_prose.py apply border-expansion-prose.md

export writes one `### <id>` block per prose element, in page order:
headings, paragraphs, list items and HexBoard notes from
src/pages/border-expansion.astro (everything before the appendix), then the
board titles and captions from scripts/build_borders.py.

apply re-extracts the same blocks from the current sources, pairs them by
id, and rewrites every block whose text changed. Anything in `{...}` or in
`<tags>` is Astro/JSX and must survive the edit verbatim; the applier
refuses a block whose brace expressions or tag names no longer match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "src/pages/border-expansion.astro"
BUILD = ROOT / "scripts/build_borders.py"

# (kind, regex) — each regex has one capture group: the editable text.
PAGE_PATTERNS = [
    ("heading", re.compile(r'<h2 class="be-h">(.*?)</h2>', re.S)),
    ("subheading", re.compile(r'<h3 class="be-h3">(.*?)</h3>', re.S)),
    ("p", re.compile(r'<p(?: class="[^"]*")?>(.*?)</p>', re.S)),
    ("li", re.compile(r"<li>(.*?)</li>", re.S)),
    ("note", re.compile(r'note="([^"]*)"')),
    ("note", re.compile(r"note=\{`([^`]*)`\}")),
]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def page_blocks(src: str) -> list[dict]:
    end = src.index('id="appendix"')
    sections = [(m.start(), m.group(1)) for m in re.finditer(r'<section[^>]*\bid="([^"]+)"', src[:end])]

    def section_at(pos: int) -> str:
        cur = "top"
        for start, sid in sections:
            if start <= pos:
                cur = sid
        return cur

    found: list[dict] = []
    for kind, rx in PAGE_PATTERNS:
        for m in rx.finditer(src, 0, end):
            text = m.group(1)
            if "map(" in text or not norm(text) or re.fullmatch(r"\{[^{}]*\}", norm(text)):
                continue  # JSX-generated rows, empty <p></p>, pure data slots
            found.append(dict(kind=kind, start=m.start(1), end=m.end(1), text=text, section=section_at(m.start())))
    found.sort(key=lambda b: b["start"])
    counts: dict[str, int] = {}
    for b in found:
        key = f'{b["section"]}.{b["kind"]}'
        counts[key] = counts.get(key, 0) + 1
        b["id"] = f'{key}{counts[key]}'
    return found


def build_blocks(src: str) -> list[dict]:
    found: list[dict] = []
    for m in re.finditer(r'defs\.append\(dict\(\s*id="(\w+)"(.*?)\n    \)\)', src, re.S):
        sid, body, base = m.group(1), m.group(2), m.start(2)
        for field in ("title", "caption"):
            f = re.search(rf'{field}="([^"]*)"', body)
            if f:
                found.append(dict(kind=field, id=f"board.{sid}.{field}", start=base + f.start(1), end=base + f.end(1), text=f.group(1), section="boards"))
    return found


def export() -> str:
    out = [
        "# Border Expansion — prose",
        "",
        "Edit the text under each `###` heading. Keep the headings and their ids.",
        "Anything in `{...}` is a data slot and anything in `<...>` is markup:",
        "move them around freely but do not rename or drop them. Blank a block to",
        "leave it unchanged (deleting text is done by editing the source). Apply with",
        "`python3 scripts/border_prose.py apply <this file>`.",
        "",
    ]
    cur = None
    for b in page_blocks(PAGE.read_text()) + build_blocks(BUILD.read_text()):
        if b["section"] != cur:
            cur = b["section"]
            out += [f"## {cur}", ""]
        out += [f'### {b["id"]}', "", norm(b["text"]), ""]
    return "\n".join(out)


def parse_md(md: str) -> dict[str, str]:
    edits: dict[str, str] = {}
    cur = None
    buf: list[str] = []
    for line in md.splitlines() + ["### __end__"]:
        if line.startswith("### "):
            if cur:
                edits[cur] = norm("\n".join(buf))
            cur, buf = line[4:].strip(), []
        elif line.startswith("## ") or line.startswith("# "):
            continue
        elif cur:
            buf.append(line)
    return edits


def guard(old: str, new: str, bid: str) -> None:
    for label, rx in (("brace expression", r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"), ("tag", r"</?[A-Za-z][^\s>/]*")):
        a, b = sorted(re.findall(rx, old)), sorted(re.findall(rx, new))
        if a != b:
            sys.exit(f"{bid}: {label}s changed; old {a}\n  new {b}")


def apply(md_path: Path) -> None:
    edits = parse_md(md_path.read_text())
    changed = 0
    for path, extractor in ((PAGE, page_blocks), (BUILD, build_blocks)):
        src = path.read_text()
        blocks = extractor(src)
        for b in sorted(blocks, key=lambda b: -b["start"]):  # replace back-to-front so offsets hold
            new = edits.get(b["id"])
            if new is None or not new or new == norm(b["text"]):
                continue
            guard(b["text"], new, b["id"])
            if b["kind"] in ("note", "title", "caption") and '"' in new and not b["text"].startswith("`"):
                new = new.replace('"', "“")  # keep the attribute/string literal well-formed
            src = src[: b["start"]] + new + src[b["end"] :]
            changed += 1
            print(f'  {b["id"]}: {norm(b["text"])[:50]!r} → {new[:50]!r}')
        path.write_text(src)
    unknown = [k for k in edits if k not in {b["id"] for b in page_blocks(PAGE.read_text()) + build_blocks(BUILD.read_text())}]
    if unknown:
        print(f"ignored unknown ids: {unknown}")
    print(f"{changed} block(s) rewritten. If any board.* changed, run: python3 scripts/build_borders.py")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "export":
        sys.stdout.write(export())
    elif len(sys.argv) == 3 and sys.argv[1] == "apply":
        apply(Path(sys.argv[2]))
    else:
        sys.exit(__doc__)
