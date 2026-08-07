#!/usr/bin/env python3
"""Build src/data/regents.json — who becomes regent, and what regency does.

Regency is entirely event-driven: when a leader dies (or abdicates) and the new
leader is a minor, EVENTTRIGGER_SUCCESSION_US fires and the highest-priority
regent event whose subject filters can be satisfied wins. So the "who is
picked" answer is a priority ladder read off eventStory.xml `iPriority` plus
each event's SubjectExtras (relationship, age and health filters).

Sources:
  eventStory.xml   — the regent events, their iPriority and SubjectExtras
  subject.xml      — what each filter means (iMinAge/iMaxAge, RelationLeader…)
  eventOption.xml  — which option actually grants regency (bonus with
                     iRegentOfSubject; Character.makeRegent)
  trait.xml        — TRAIT_REGENT / TRAIT_FORMER_REGENT effects
  globalsType.xml  — REGENT_TRAIT, FORMER_REGENT_TRAIT, REGENT_TITLE
  text-*.xml       — names and the events' own prose
"""
from __future__ import annotations

import glob
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "regents.json"


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("text-*.xml")):
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        for e in root.findall("Entry"):
            k, v = e.findtext("zType"), e.findtext("en-US")
            if k and v and k not in out:
                v = re.sub(r"^icon\([^)]*\)", "", v.split("~")[0])
                v = re.sub(r"\{[^}]*\}", "", v)
                v = re.sub(r"link\(([A-Z_0-9]+)(?:,\d+)?\)", "", v)
                out[k] = re.sub(r"\s{2,}", " ", v).strip()
    return out


def load_gendered_text() -> dict[str, str]:
    """GENDERED_TEXT_* → its masculine TEXT_* key (same as build_traits)."""
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("genderedText*.xml")):
        for entry in ET.parse(p).getroot().findall("Entry"):
            zid = entry.findtext("zType") or ""
            if not zid:
                continue
            for pair in entry.findall("Texts/Pair"):
                if (pair.findtext("zIndex") or "").endswith("MASCULINE"):
                    out[zid] = pair.findtext("zValue") or ""
                    break
    return out


def main() -> int:
    text = load_text()
    gendered = load_gendered_text()

    def name_of(key: str, fallback: str) -> str:
        if key.startswith("GENDERED_TEXT_"):
            key = gendered.get(key, key)
        return text.get(key, fallback)
    subjects = {e.findtext("zType"): e for e in parse("subject.xml").findall("Entry")
                if e.findtext("zType")}
    options = {e.findtext("zType"): e for e in parse("eventOption.xml").findall("Entry")
               if e.findtext("zType")}

    # bonuses that actually create a regent (PlayerBonus.cs miRegentOfSubject)
    regent_bonuses = set()
    for f in glob.glob(str(XML_DIR / "bonus*.xml")):
        for e in ET.parse(f).getroot().findall("Entry"):
            if (e.findtext("iRegentOfSubject") or "") != "":
                regent_bonuses.add(e.findtext("zType"))

    def describes(sid: str) -> str:
        """Human phrase for a subject filter."""
        e = subjects.get(sid)
        if e is None:
            return sid
        rel = e.findtext("RelationLeader") or ""
        if rel:
            return rel.replace("SUBJECTRELATION_", "").replace("_OF", "").replace("_", "/").title() \
                + " of the new leader"
        lo, hi = e.findtext("iMinAge"), e.findtext("iMaxAge")
        if lo and hi:
            return f"aged {lo}–{hi}"
        if lo:
            return f"aged {lo} or older"
        if hi:
            return f"aged {hi} or younger"
        if (e.findtext("bRoyal") or "0") == "1":
            return "royal family"
        if (e.findtext("bFamilyHead") or "0") == "1":
            return "a family head"
        if sid == "SUBJECT_HEALTHY":
            return "healthy"
        if sid == "SUBJECT_CHARACTER_US":
            return "any character in your court"
        return sid.replace("SUBJECT_", "").replace("_", " ").title()

    events = []
    for e in parse("eventStory.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        opts = [x.text for x in e.findall("aeOptions/zValue") if x.text]
        grants = [o for o in opts
                  if any((b.text in regent_bonuses)
                         for b in (options[o].findall("aeBonuses/zValue") if o in options else [])
                         if b.text)]
        if not grants:
            continue
        subs = [x.text for x in e.findall("aeSubjects/zValue")]
        # SubjectExtras: First = subject index, Second = extra filter on it
        cand, leader = [], []
        for pair in e.findall("SubjectExtras/Pair"):
            idx, sid = pair.findtext("First"), pair.findtext("Second")
            if sid in (None, "", "None") or sid == "SUBJECT_IGNORE_NO_EVENT_TRAITS":
                continue
            (cand if idx == "3" else leader).append(describes(sid))
        who = subs[3] if len(subs) > 3 else ""
        # SUBJECT_CHARACTER_US carries no descriptive weight — the relationship
        # filter on that slot is what actually names the candidate
        rel = next((c for c in cand if c.endswith("the new leader")), "")
        events.append({
            "id": z,
            "name": text.get(e.findtext("Name") or "", z),
            "priority": int(e.findtext("iPriority") or "0"),
            "candidate": rel or (describes(who) if who else "any character"),
            "candidateFilters": [c for c in cand if c != rel],
            "leaderFilters": leader,
            "abdication": "ABDICATION" in z,
            "optional": len(opts) > 1,
        })
    events.sort(key=lambda x: (-x["priority"], x["id"]))

    def trait(tid: str) -> dict:
        for e in parse("trait.xml").findall("Entry"):
            if e.findtext("zType") == tid:
                ratings = [f"{p.findtext('iValue')} {p.findtext('zIndex').replace('RATING_','').title()}"
                           for p in e.findall("aiRating/Pair")]
                return {
                    "id": tid,
                    "name": name_of(e.findtext("GenderedName") or "",
                                    tid.replace("TRAIT_", "").replace("_", " ").title()),
                    "familyOpinion": int(e.findtext("iOpinionFamily") or "0"),
                    "ratings": ratings,
                }
        return {"id": tid, "name": tid, "familyOpinion": 0, "ratings": []}

    globals_type = {e.findtext("zType"): e.findtext("zValue")
                    for e in parse("globalsType.xml").findall("Entry") if e.findtext("zType")}

    data = {
        "events": events,
        "regentTrait": trait(globals_type.get("REGENT_TRAIT", "TRAIT_REGENT")),
        "formerRegentTrait": trait(globals_type.get("FORMER_REGENT_TRAIT", "TRAIT_FORMER_REGENT")),
        "title": text.get(
            next((e.findtext("Name") for e in parse("title.xml").findall("Entry")
                  if e.findtext("zType") == globals_type.get("REGENT_TITLE")), ""), "Regent"),
        "counts": {"events": len(events)},
    }
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(events)} regent events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
