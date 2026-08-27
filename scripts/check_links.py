#!/usr/bin/env python3
"""
Post-build link check over dist/.

Verifies that every internal href/src in the generated HTML resolves to a
file in dist/, and reports unresolved <Term> references (`term--unknown`)
per page so broken entity links surface each patch instead of silently
shipping.

Run after `npx astro build`:  python3 scripts/check_links.py
Exit code 1 on broken internal links (unknown terms are warnings only).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BASE = "/owreference/"

ATTR_RE = re.compile(r'\b(?:href|src)="([^"#]*)(?:#[^"]*)?"')
UNKNOWN_RE = re.compile(r'term--unknown[^>]*>([^<]*)<')
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)
# Inlined CSS carries the .term--unknown rule itself; scanning it would
# match the stylesheet instead of markup (false positive).
STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)


def resolves(target: str, page_dir: Path) -> bool:
    if target.startswith(BASE):
        rel = unquote(target[len(BASE):])
        p = DIST / rel
    elif target.startswith("/"):
        return False  # absolute path outside our base — always wrong on GH Pages
    else:
        p = page_dir / unquote(target)
    if p.is_file():
        return True
    if p.is_dir() and (p / "index.html").is_file():
        return True
    # directory-format links without trailing slash
    return (p.parent / p.name / "index.html").is_file() if p.name else False


def main() -> int:
    if not DIST.exists():
        print("✗ dist/ not found — run `npx astro build` first")
        return 1

    broken: list[tuple[str, str]] = []
    unknown: dict[str, list[str]] = {}
    pages = sorted(DIST.rglob("*.html"))

    for page in pages:
        html = page.read_text(errors="replace")
        html = SCRIPT_RE.sub("", html)  # JS string literals aren't links
        html = STYLE_RE.sub("", html)   # nor are CSS selectors
        rel_page = str(page.relative_to(DIST))
        for m in ATTR_RE.finditer(html):
            url = m.group(1).strip()
            if not url or urlparse(url).scheme or url.startswith(("//", "mailto:", "data:")):
                continue
            if not resolves(url, page.parent):
                broken.append((rel_page, url))
        terms = [t.strip() for t in UNKNOWN_RE.findall(html) if t.strip()]
        if terms:
            unknown[rel_page] = sorted(set(terms))

    if unknown:
        n = sum(len(v) for v in unknown.values())
        print(f"⚠ {n} unresolved <Term> reference(s) across {len(unknown)} page(s):")
        for page, terms in sorted(unknown.items())[:20]:
            print(f"  {page}: {', '.join(terms[:8])}{' …' if len(terms) > 8 else ''}")
        if len(unknown) > 20:
            print(f"  … and {len(unknown) - 20} more pages")

    if broken:
        print(f"✗ {len(broken)} broken internal link(s):")
        for page, url in broken[:50]:
            print(f"  {page} → {url}")
        if len(broken) > 50:
            print(f"  … and {len(broken) - 50} more")
        return 1

    print(f"✓ link check: {len(pages)} pages, 0 broken internal links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
