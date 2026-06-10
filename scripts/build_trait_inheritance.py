#!/usr/bin/env python3
"""
Build src/data/trait_inheritance.json from trait.xml + eventStory.xml.

Output shape: {"traits": [...], "inheritance": [...]}.

"traits" is the XML-canonical personality matrix:
  • Personality traits (iAdjectiveDie > 0, bStrength or bWeakness set)
  • The trait's polar opposite (aeTraitReplaces — Affable replaces Cruel)
  • The character rating it strengthens/weakens (aePositiveRating / aeNegativeRating)
  • Family-head / agent / religion-head bonus modifiers
  • Same-trait opinion (iOpinionSame — characters with the same trait like each other)
  • The traits this one conflicts with (aiTraitOpinion with negative values)

"inheritance" restores the legacy sheet's "Inheritance Trait 1/2/3" view,
but derived from the XML instead of community curation. The real mechanism
is the EVENTCLASS_TRAIT_INHERITANCE event family in eventStory.xml
("Like father, like son"): each event requires a non-leader parent with a
specific trait (SubjectExtras → subject.xml TraitPrereq), triggers on a
child/teenager in the succession line (EVENTTRIGGER_NEW_TURN_CHARACTER,
iProb gate), and its single option grants one trait drawn from the bonus's
aeRandomTrait list — uniformly among the candidates the child can legally
gain (Character.doRandomTrait in the game source).

Note: the "Mother's/Father's Disposition" study events are a different
mechanic — they pass on parent *ratings* (±1 Charisma etc.), not traits.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "trait_inheritance.json"


RATING_LABELS: dict[str, str] = {
    "RATING_WISDOM":     "Wisdom",
    "RATING_CHARISMA":   "Charisma",
    "RATING_COURAGE":    "Courage",
    "RATING_DISCIPLINE": "Discipline",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text(*filenames: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").split("~")[0].strip()
            if k:
                out[k] = en
    return out


def get_trait_name(trait_id: str, gendered_text: dict, text_trait: dict) -> str:
    """Resolve TRAIT_AFFABLE → 'Affable'."""
    # GenderedName might be GENDERED_TEXT_TRAIT_AFFABLE → TEXT_TRAIT_AFFABLE
    text_key = gendered_text.get(f"GENDERED_TEXT_{trait_id.replace('TRAIT_', 'TRAIT_')}", "")
    if text_key and text_key in text_trait:
        return text_trait[text_key]
    # Fallback: title-case the suffix
    return trait_id.replace("TRAIT_", "").replace("_", " ").title()


def load_gendered_text() -> dict[str, str]:
    """Map GENDERED_TEXT_TRAIT_X → TEXT_TRAIT_X (masculine, first form)."""
    out: dict[str, str] = {}
    p = XML_DIR / "genderedText.xml"
    if not p.exists():
        return out
    for entry in ET.parse(p).getroot().findall("Entry"):
        zid = entry.findtext("zType") or ""
        if not zid:
            continue
        for pair in entry.findall("Texts/Pair"):
            if (pair.findtext("zIndex") or "").endswith("MASCULINE"):
                out[zid] = pair.findtext("zValue") or ""
                break
    return out


def load_trait_kinds() -> dict[str, str]:
    """TRAIT_X → strength | weakness | neutral, for ALL traits (unfiltered).

    Inheritance children include traits outside the personality matrix
    (Divine, Exotic, Insane, Miserable, Infamous), so the kind map must not
    use the iAdjectiveDie filter.
    """
    kinds: dict[str, str] = {}
    for e in parse("trait.xml").findall("Entry"):
        zid = e.findtext("zType") or ""
        if not zid:
            continue
        if (e.findtext("bStrength") or "0") == "1":
            kinds[zid] = "strength"
        elif (e.findtext("bWeakness") or "0") == "1":
            kinds[zid] = "weakness"
        else:
            kinds[zid] = "neutral"
    return kinds


def build_inheritance(name_of, kinds: dict[str, str]) -> list[dict]:
    """Derive parent trait → possible child traits from the
    EVENTCLASS_TRAIT_INHERITANCE events."""
    # subject.xml: SUBJECT_X → required trait (TraitPrereq), and age windows
    subj_trait: dict[str, str] = {}
    subj_age: dict[str, tuple[str, str, str]] = {}  # id → (label, min, max)
    for e in parse("subject.xml").findall("Entry"):
        zid = e.findtext("zType") or ""
        if not zid:
            continue
        t = e.findtext("TraitPrereq") or ""
        if t.startswith("TRAIT_"):
            subj_trait[zid] = t
        mn, mx = e.findtext("iMinAge"), e.findtext("iMaxAge")
        if mn and mx:
            label = zid.replace("SUBJECT_", "").replace("_", " ").title()
            subj_age[zid] = (label, mn, mx)

    # eventOption*.xml: option → bonuses
    opt_bonuses: dict[str, list[str]] = {}
    for p in sorted(XML_DIR.glob("eventOption*.xml")):
        if p.name.startswith("text-"):
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            zid = e.findtext("zType") or ""
            if zid:
                opt_bonuses[zid] = [v.text for v in e.findall("aeBonuses/zValue") if v.text]

    # bonus*.xml: bonus → aeRandomTrait candidate list (XML order = Trait 1/2/3)
    bonus_random: dict[str, list[str]] = {}
    for p in sorted(XML_DIR.glob("bonus*.xml")):
        for e in ET.parse(p).getroot().findall("Entry"):
            zid = e.findtext("zType") or ""
            rnd = [v.text for v in e.findall("aeRandomTrait/zValue") if v.text]
            if zid and rnd:
                bonus_random[zid] = rnd

    def trait_ref(tid: str) -> dict:
        return {
            "id": tid,
            "kind": kinds.get(tid, "neutral"),
            "name": name_of(tid),
            "slug": tid.replace("TRAIT_", "").lower(),
        }

    rows: list[dict] = []
    for p in sorted(XML_DIR.glob("eventStory*.xml")):
        if p.name.startswith("text-"):
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            if (e.findtext("Class") or "") != "EVENTCLASS_TRAIT_INHERITANCE":
                continue
            zid = e.findtext("zType") or ""
            # Parent trait: the SubjectExtras entry that is a trait-prereq subject
            parent_traits = []
            child_age = ""
            for pair in e.findall("SubjectExtras/Pair"):
                s = pair.findtext("Second") or ""
                if s in subj_trait:
                    parent_traits.append(subj_trait[s])
                elif s in subj_age:
                    label, mn, mx = subj_age[s]
                    child_age = f"{label} ({mn}–{mx})"
            if len(parent_traits) != 1:
                print(f"  ! {zid}: expected 1 parent trait, got {parent_traits} — skipped")
                continue
            # Child candidates: the single option's bonus aeRandomTrait list
            children: list[str] = []
            for opt in e.findall("aeOptions/zValue"):
                for b in opt_bonuses.get(opt.text or "", []):
                    children.extend(bonus_random.get(b, []))
            if not children:
                print(f"  ! {zid}: no aeRandomTrait outcome — skipped")
                continue
            rows.append({
                "childAge": child_age,
                "children": [trait_ref(t) for t in children],
                "eventId": zid,
                "parent": trait_ref(parent_traits[0]),
                "prob": int(e.findtext("iProb") or "0"),
            })

    kind_order = {"strength": 0, "weakness": 1, "neutral": 2}
    rows.sort(key=lambda r: (kind_order.get(r["parent"]["kind"], 3), r["parent"]["name"]))
    return rows


def main() -> int:
    text_trait = load_text("text-trait.xml", "text-trait-btt.xml", "text-trait-sap.xml", "text-trait-wog.xml")
    gendered = load_gendered_text()

    root = parse("trait.xml")
    entries: list[ET.Element] = root.findall("Entry")

    def name_of(tid: str) -> str:
        return get_trait_name(tid, gendered, text_trait)

    traits: list[dict] = []

    for e in entries:
        zid = e.findtext("zType") or ""
        if not zid or "_ARCHETYPE" in zid:
            continue
        # Only "personality" traits — those that come from upbringing and have
        # opposites. iAdjectiveDie > 0 is the canonical filter.
        ad = e.findtext("iAdjectiveDie") or "0"
        if not ad or int(ad) <= 0:
            continue
        # Only the ones that are either a strength or a weakness — these are
        # the pair-able personality traits the spreadsheet covers.
        is_strength = (e.findtext("bStrength") or "0") == "1"
        is_weakness = (e.findtext("bWeakness") or "0") == "1"
        if not (is_strength or is_weakness):
            continue

        positive_rating = ""
        for r in e.findall("aePositiveRating/zValue"):
            if r.text:
                positive_rating = RATING_LABELS.get(r.text, r.text)
                break
        negative_rating = ""
        for r in e.findall("aeNegativeRating/zValue"):
            if r.text:
                negative_rating = RATING_LABELS.get(r.text, r.text)
                break

        # Opposite trait (the one this trait replaces — e.g. Affable replaces Cruel)
        opposites: list[str] = []
        for rep in e.findall("aeTraitReplaces/zValue"):
            if rep.text:
                opposites.append(name_of(rep.text))

        # Traits this one dislikes / conflicts with (negative aiTraitOpinion)
        conflicts: list[str] = []
        for pair in e.findall("aiTraitOpinion/Pair"):
            iv = int(pair.findtext("iValue") or "0")
            if iv < 0:
                tid = pair.findtext("zIndex") or ""
                if tid:
                    conflicts.append(name_of(tid))

        opinion_same = int(e.findtext("iOpinionSame") or "0")

        modifiers: list[dict] = []
        for tag, label in [
            ("iFamilyHeadModifier", "Family Head"),
            ("iAgentModifier",      "Agent"),
            ("iReligionHeadModifier", "Religion Head"),
            ("iBirthModifier",      "Birth"),
            ("iUnitBuildModifier",  "Unit Build"),
            ("iWeaknessLimitModifier", "Weakness Limit"),
            ("iStrengthLimitModifier", "Strength Limit"),
        ]:
            v = e.findtext(tag) or "0"
            if v and v != "0":
                modifiers.append({"label": label, "value": int(v)})

        traits.append({
            "id": zid,
            "slug": zid.replace("TRAIT_", "").lower(),
            "name": name_of(zid),
            "kind": "strength" if is_strength else "weakness",
            "positiveRating": positive_rating,
            "negativeRating": negative_rating,
            "opposites": opposites,
            "conflicts": sorted(set(conflicts)),
            "iOpinionSame": opinion_same,
            "modifiers": modifiers,
            "iconName": e.findtext("zIconName") or "",
        })

    # Sort: strengths first, then weaknesses; alphabetical within each
    traits.sort(key=lambda t: (0 if t["kind"] == "strength" else 1, t["name"]))

    inheritance = build_inheritance(name_of, load_trait_kinds())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"inheritance": inheritance, "traits": traits}
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    s_count = sum(1 for t in traits if t["kind"] == "strength")
    w_count = sum(1 for t in traits if t["kind"] == "weakness")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(traits)} traits ({s_count} strengths, "
          f"{w_count} weaknesses), {len(inheritance)} inheritance events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
