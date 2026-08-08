"""Shared definition of "Blessed" and "Cursed" events — the two divine-favour
character traits (trait.xml TRAIT_BLESSED / TRAIT_CURSED, each of which
aeTraitReplaces the other, so a character is never both).

A story counts for a trait if it relates to it in any of three ways:

  needs   — the story can only fire for a character who already has it
            (SUBJECT_BLESSED / SUBJECT_CURSED, whose TraitPrereq is the trait),
            listed either as a subject or as a SubjectExtras filter
  grants  — one of its options carries a bonus with aeAddTraits = the trait
  removes — one of its options carries a bonus with aeRemoveTraits = the trait

Like family events (and unlike wonder/project/building events, which have one
defining completion trigger), a blessing is an orthogonal attribute: these
stories also belong to their own event class / trigger. So these are
NON-exclusive cross-cut views — the stories still appear under their class on
Story Events, and build_story_events does NOT exclude them.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

TRAITS = {
    "BLESSED": {
        "trait": "TRAIT_BLESSED",
        "subject": "SUBJECT_BLESSED",
        "label": "Blessed",
    },
    "CURSED": {
        "trait": "TRAIT_CURSED",
        "subject": "SUBJECT_CURSED",
        "label": "Cursed",
    },
}


def _option_bonuses(story: ET.Element, eopt_idx: dict) -> list[ET.Element]:
    """Every bonus reachable from this story's options."""
    out = []
    for ref in story.findall("aeOptions/zValue"):
        opt = eopt_idx.get(ref.text or "")
        if opt is None:
            continue
        out.extend(b for b in opt.findall("aeBonuses/zValue") if b.text)
    return out


def relation(story: ET.Element, key: str, eopt_idx: dict, bonus_idx: dict) -> dict | None:
    """How a story relates to BLESSED/CURSED, or None if it doesn't.

    Returns {"needs": bool, "grants": bool, "removes": bool}.
    """
    spec = TRAITS[key]
    subject, trait = spec["subject"], spec["trait"]

    # gated: the subject appears as a cast slot or as an extra filter on one
    subjects = {s.text for s in story.findall("aeSubjects/zValue") if s.text}
    extras = {p.findtext("Second") for p in story.findall("SubjectExtras/Pair")}
    needs = subject in (subjects | extras)

    grants = removes = False
    for ref in _option_bonuses(story, eopt_idx):
        b = bonus_idx.get(ref.text or "")
        if b is None:
            continue
        if trait in {t.text for t in b.findall("aeAddTraits/zValue")}:
            grants = True
        if trait in {t.text for t in b.findall("aeRemoveTraits/zValue")}:
            removes = True

    if not (needs or grants or removes):
        return None
    return {"needs": needs, "grants": grants, "removes": removes}


def is_blessing_event(story: ET.Element, key: str, eopt_idx: dict, bonus_idx: dict) -> bool:
    return relation(story, key, eopt_idx, bonus_idx) is not None
