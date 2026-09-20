#!/usr/bin/env python3
"""Which DLC does a GameContentRequired token come from?

Derived, never hand-listed. `additionalContent.xml` maps each store DLC to the
GameContentType tokens it grants (`aeGameContent`), and its `Name` resolves to
the marketed title in `text-misc.xml` (Empires of the Indus is the exception —
its Name points into `text-eoti.xml`). That is the game's own answer to "who
owns this content".

    DLC_HEROES_OF_AEGEAN           → CAMPAIGN_GREECE, NATION_HITTITES
    DLC_THE_SACRED_AND_THE_PROFANE → EVENTPACK_RELIGION
    DLC_PHARAOHS_OF_THE_NILE       → PHARAOHS
    DLC_WONDERS_AND_DYNASTIES      → WONDERS_DYNASTIES
    DLC_BEHIND_THE_THRONE          → EVENTPACK_SCANDAL
    DLC_CALAMITIES                 → CALAMITIES, AKSUM      ("Wrath of Gods")
    DLC_EMPIRES_OF_THE_INDUS       → EMPIRES_OF_THE_INDUS

Two things a hand-written map keeps getting wrong, and the reason this file
exists at all:

  · **AKSUM ships with Wrath of Gods**, not with The Sacred and the Profane.
    Seven builders each carried their own label map and four of them said SaP,
    mislabelling 69 entries across events, projects, traits and missions. The
    guess is understandable — Aksum's content sits in the BASE xml files rather
    than a `-wog` suffixed one, so nothing in the filename corrects you, and
    `bonus-event-sap.xml` really does mention RELIGION_PAGAN_AKSUM. It is still
    wrong.
  · **One DLC can grant several content types**, so the relation is not 1:1 in
    either direction (Calamities grants CALAMITIES *and* AKSUM; Heroes of the
    Aegean grants CAMPAIGN_GREECE *and* NATION_HITTITES).

Standalone by design: build_missions and build_mission_catalog import each
other, and this has to stay outside that cycle.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"

# The DLC titles live in text-misc.xml; Empires of the Indus points at the
# concept text in its own pack file instead.
TEXT_FILES = ("text-misc.xml", "text-eoti.xml", "text-infos.xml")

_NAMES: dict[str, str] | None = None
_BY_CONTENT: dict[str, str] | None = None
_TOKEN_BY_CONTENT: dict[str, str] | None = None


def _names() -> dict[str, str]:
    global _NAMES
    if _NAMES is None:
        out: dict[str, str] = {}
        for fn in TEXT_FILES:
            p = XML_DIR / fn
            if not p.exists():
                continue
            for e in ET.parse(p).getroot().findall("Entry"):
                k = (e.findtext("zType") or "").strip()
                v = (e.findtext("en-US") or "").split("~")[0].strip()
                if k and v and k not in out:
                    out[k] = v
        _NAMES = out
    return _NAMES


def _entries() -> list[tuple[str, str, list[str]]]:
    """(DLC token, display name, content types granted)."""
    text, out = _names(), []
    p = XML_DIR / "additionalContent.xml"
    if not p.exists():
        return out
    for e in ET.parse(p).getroot().findall("Entry"):
        z = (e.findtext("zType") or "").strip()
        if not z:
            continue
        name = text.get((e.findtext("Name") or "").strip(), "")
        label = name or z.replace("DLC_", "").replace("_", " ").title()
        granted = [gc.text for gc in e.findall("aeGameContent/zValue") if gc.text]
        out.append((z, label, granted))
    return out


def dlc_by_content() -> dict[str, str]:
    """GameContentType token → the DLC's display name."""
    global _BY_CONTENT
    if _BY_CONTENT is None:
        _BY_CONTENT = {gc: label for _, label, granted in _entries() for gc in granted}
    return _BY_CONTENT


def dlc_token_by_content() -> dict[str, str]:
    """GameContentType token → the DLC_* store token that grants it.

    The direction a SAVE needs: saves record store names in `<GameContent>`
    while every info entry names a content type, so the two cannot be compared
    directly.
    """
    global _TOKEN_BY_CONTENT
    if _TOKEN_BY_CONTENT is None:
        _TOKEN_BY_CONTENT = {gc: z for z, _, granted in _entries() for gc in granted}
    return _TOKEN_BY_CONTENT


def label(token: str, default: str | None = None) -> str | None:
    """Display name for a GameContentRequired token ('' = base game)."""
    if not token:
        return default
    return dlc_by_content().get(token, default)


if __name__ == "__main__":
    for z, name, granted in sorted(_entries()):
        print(f"{z:32s} {name:28s} {', '.join(granted)}")
