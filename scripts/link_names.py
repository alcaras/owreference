"""Resolve the game's link(TOKEN[,N]) markup to the name the game shows.

The game renders link(UNIT_HITTITE_CHARIOT_1,2) through the info entry's own
Name text, picking the N-th "~" form (HelpLinkParser.GetHelpLink →
TextVariable.Evaluate(index)): "Heavy Chariot~a Heavy Chariot~Heavy Chariots"
gives "Heavy Chariots" for N=2. Title-casing the token instead ("Hittite
Chariot 1") is right only while a unit's zType happens to match its name, so
every link stripper should come through here.

Standalone (no humanize import) so effects.py, which humanize imports, can use
it too.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

XML_DIR = Path(__file__).resolve().parent.parent / "reference" / "XML" / "Infos"

LINK_RE = re.compile(r"\{?(lowercase:)?link\(([A-Z][A-Z0-9_]*)(?:\s*,\s*(\d+))?\)\}?")
ICON_RE = re.compile(r"\{?icon\([A-Z0-9_]+(?:,\d+)?\)\}?")


@lru_cache(maxsize=1)
def _indexes() -> tuple[dict[str, list[str]], dict[str, str]]:
    """(TEXT key → en-US forms, zType → Name key) across every Infos file."""
    forms: dict[str, list[str]] = {}
    name_key: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("*.xml")):
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        is_text = p.name.startswith("text-")
        for e in root.findall("Entry"):
            z = e.findtext("zType") or ""
            if not z:
                continue
            if is_text:
                en = e.findtext("en-US")
                if en and z not in forms:
                    forms[z] = [f.strip() for f in en.split("~")]
            else:
                n = e.findtext("Name") or ""
                if n and z not in name_key:
                    name_key[z] = n
    return forms, name_key


def _prettify(token: str) -> str:
    parts = token.split("_")
    if len(parts) > 1:
        parts = parts[1:]
    return " ".join(p.title() for p in parts)


def link_name(token: str, index: int = 0, _depth: int = 0) -> str:
    """Display name for a link() target, in the game's N-th form."""
    forms, name_key = _indexes()
    fs = forms.get(name_key.get(token, "")) or forms.get("TEXT_" + token)
    if not fs or _depth > 3:
        return _prettify(token)
    s = fs[index] if index < len(fs) and fs[index] else fs[0]
    return ICON_RE.sub("", resolve_links(s, _depth + 1)).strip()


def resolve_links(s: str, _depth: int = 0) -> str:
    """Replace every link(...) in `s` with its display name. The game
    lowercases a {lowercase:link()} name whole ("the pyramids"); we lowercase
    only a leading "The" so names stay capitalised like everywhere else on the
    site (LinkedText links non-yield names only in their own case)."""
    def repl(m: "re.Match[str]") -> str:
        name = link_name(m.group(2), int(m.group(3) or 0), _depth)
        if m.group(1) and name.startswith("The "):
            name = "the " + name[4:]
        return name
    return LINK_RE.sub(repl, s)


def with_dlc(filenames) -> list[str]:
    """Text files plus their DLC siblings: text-unit.xml → text-unit.xml,
    text-unit-hittite.xml. The Hittite units, nation and families are named
    only in the siblings, so a loader reading the base file alone fell back to
    the zType ("Hittite Chariot 1" for the Heavy Chariot). No sibling redefines
    a base key, so the order doesn't change any name."""
    out: list[str] = []
    for fn in filenames:
        stem = fn.removesuffix(".xml")
        for name in [fn, *sorted(p.name for p in XML_DIR.glob(f"{stem}-*.xml"))]:
            if name not in out:
                out.append(name)
    return out


def game_name(token: str) -> str:
    """The game's name for an info zType ("GOAL_THREE_LIBRARY_3" → "Three
    Universities"), or "" when it has none."""
    forms, name_key = _indexes()
    return link_name(token) if forms.get(name_key.get(token, "")) else ""
