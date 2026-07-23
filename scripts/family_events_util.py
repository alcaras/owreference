"""Shared definition of "family events" — stories tied to a specific family
CLASS (Champions, Clerics, Hunters, Landowners, Patrons, Riders, Sages,
Statesmen, Traders, Artisans). Detected by any subject / condition / effect
that references that class:
  SUBJECT_FAMILY_<CLASS>, SUBJECT_CITY_<CLASS>, SUBJECT_PLAYER_FAMILYCLASS_<CLASS>,
  SUBJECT_FAMILY_<CLASS>_US, FAMILYCLASS_<CLASS>, …

Unlike wonder/project/building events (which have one defining completion
trigger and get pulled OUT of the general Story Events pages), a family class
is an orthogonal attribute: the same story also belongs to its own event
class / trigger. So the Family Events page is a NON-exclusive cross-cut — its
stories still appear under their class on Story Events — and build_story_events
does NOT exclude them.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

# Family classes (familyClass.xml) — the 10 archetypes a family can be.
CLASSES = ["CHAMPIONS", "CLERICS", "HUNTERS", "LANDOWNERS", "PATRONS",
           "RIDERS", "SAGES", "STATESMEN", "TRADERS", "ARTISANS"]

# One regex per class: matches FAMILYCLASS_<CLASS> or any SUBJECT_*_<CLASS>
# (optionally _US), so we don't false-match a substring of another token.
_PATTERNS = {
    c: re.compile(rf"(FAMILYCLASS_{c}\b|SUBJECT_[A-Z_]*?{c}(_US)?\b)")
    for c in CLASSES
}


def family_classes(s: ET.Element) -> list[str]:
    """The family classes a story references, in canonical order."""
    blob = ET.tostring(s, encoding="unicode")
    return [c for c in CLASSES if _PATTERNS[c].search(blob)]


def is_family_event(s: ET.Element) -> bool:
    return bool(family_classes(s))
