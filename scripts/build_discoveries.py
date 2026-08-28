#!/usr/bin/env python3
"""
Build src/data/discoveries.json — the hidden "bonus card" techs.

`tech.xml` carries two kinds of entry. The visible tree (49 techs) is
build_technologies.py's job; everything flagged `bHide=1` is a **discovery**:
the one-shot card you draw when you finish a tech (Free Worker, Stone Boost,
Free Bireme…). They never appear in the tree, so the tech page rightly skips
them — but they are real, named, user-facing choices, so they get their own
page (and, through it, a home for search to land on).

Each entry: id, slug (matching the page anchor), name, cost, what it grants
(humanized `BonusDiscover`), the tech that offers it (`abTechPrereq` — never
parse the zType, it lies: TECH_FORESTRY_BONUS_SCIENTIST requires Metaphysics),
plus nation / culture / DLC gates.
"""
from __future__ import annotations

import collections
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_missions as m  # noqa: E402  reuse the bonus humanizer + text loader

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "discoveries.json"

# Card names/advice are scattered across the base + DLC string tables (the BtT
# cards live in text-misc-btt.xml, not text-infos-btt.xml), so load them all.
TEXT_FILES = (
    "text-infos.xml", "text-infos-btt.xml", "text-infos-sap.xml", "text-infos-hittite.xml",
    "text-misc.xml", "text-misc-btt.xml", "text-eoti.xml",
    "text-wonders-dynasties-infos.xml", "text-wonders-dynasties-misc.xml",
    "text-bonus.xml", "text-bonus-btt.xml", "text-bonus-sap.xml", "text-bonus-wog.xml",
    "text-unit.xml", "text-unit-hittite.xml", "text-nation.xml", "text-yield.xml",
    "text-occurrence-wog.xml", "text-occurrence-btt.xml",
)


def slug_of(zid: str, prefix: str) -> str:
    return zid.replace(prefix, "").lower()


def main() -> int:
    text = m.load_text(*TEXT_FILES)
    bonus_idx = m.bonus_index()
    techs = {e.findtext("zType"): e for e in ET.parse(XML_DIR / "tech.xml").getroot()
             if e.findtext("zType")}
    nations = {e.findtext("zType"): e for e in ET.parse(XML_DIR / "nation.xml").getroot()
               if e.findtext("zType")}
    resources = {e.findtext("zType"): e for e in ET.parse(XML_DIR / "resource.xml").getroot()
                 if e.findtext("zType")}
    occurrences = {}
    for fn in ("occurrence.xml", "occurrence-wog.xml", "occurrence-btt.xml"):
        if (XML_DIR / fn).exists():
            occurrences.update({e.findtext("zType"): e
                                for e in ET.parse(XML_DIR / fn).getroot() if e.findtext("zType")})

    def tech_name(zid: str) -> str:
        e = techs.get(zid)
        key = e.findtext("Name") if e is not None else None
        return m.clean_text(text.get(key or "", slug_of(zid, "TECH_").replace("_", " ").title()))

    def nation_name(zid: str) -> str:
        e = nations.get(zid)
        key = (e.findtext("Name") or e.findtext("GenderedName") or "") if e is not None else ""
        return m.clean_text(text.get(key.replace("GENDERED_", ""),
                                     slug_of(zid, "NATION_").title()))

    def resource_name(zid: str) -> str:
        e = resources.get(zid)
        key = e.findtext("Name") if e is not None else None
        return m.clean_text(text.get(key or "", slug_of(zid, "RESOURCE_").replace("_", " ").title()))

    def card_only_grants(bonus_id: str) -> list[dict]:
        """Bonus shapes the shared (event) humanizer doesn't render — they only
        ever turn up on discovery cards, so they're handled here rather than
        widening build_missions for one page."""
        b = bonus_idx.get(bonus_id)
        if b is None:
            return []
        out: list[dict] = []
        counts = collections.Counter(p.findtext("First")
                                     for p in b.findall("AddCourtierOther/Pair") if p.findtext("First"))
        for cid, n in sorted(counts.items()):
            out.append({"text": f"+{n} " + m.clean_text(
                text.get("TEXT_" + cid, slug_of(cid, "COURTIER_").title()))})
        for p in b.findall("aeImportResources/Pair"):
            rid = p.findtext("zIndex") or ""
            n = int((p.findtext("iValue") or "1").strip() or "1")
            out.append({"text": f"+{n} {resource_name(rid)} imported"})
        for v in b.findall("aeAllCityBonuses/zValue"):
            inner_id = v.text or ""
            inner = m.humanize_bonus(inner_id, bonus_idx, text)
            ib = bonus_idx.get(inner_id)
            growth = (ib.findtext("iBorderGrowth") or "") if ib is not None else ""
            if growth.strip():
                inner.append({"text": f"+{growth.strip()} Border Growth"})
            out += [{**g, "text": g["text"] + " in every city"} for g in inner]
        return out

    out: list[dict] = []
    for zid, e in techs.items():
        if (e.findtext("bHide") or "").strip() != "1":
            continue
        # The tech that offers this card. Read abTechPrereq — the zType lies.
        prereqs = [p.findtext("zIndex") for p in e.findall("abTechPrereq/Pair")
                   if (p.findtext("bValue") or "").strip() == "1" and p.findtext("zIndex")]
        grants = m.humanize_bonus(e.findtext("BonusDiscover") or "", bonus_idx, text)
        grants += card_only_grants(e.findtext("BonusDiscover") or "")
        if not grants:
            # A few cards grant something the bonus humanizer doesn't cover —
            # today only OccurrenceStartPlayer (the WoG "rally" occurrences).
            # Name the occurrence rather than showing an empty card.
            b = bonus_idx.get(e.findtext("BonusDiscover") or "")
            occ = b.findtext("OccurrenceStartPlayer") if b is not None else None
            if occ and occ in occurrences:
                grants = [{"text": "Starts " + m.clean_text(
                    text.get(occurrences[occ].findtext("Name") or "",
                             slug_of(occ, "OCCURRENCE_").replace("_", " ").title()))}]
        culture = (e.findtext("CultureValid") or "").replace("CULTURE_", "").title()
        out.append({
            "id": zid,
            "slug": slug_of(zid, "TECH_"),
            "name": m.clean_text(text.get(e.findtext("Name") or "",
                                          slug_of(zid, "TECH_").replace("_", " ").title())),
            "advice": m.clean_text(text.get(e.findtext("Advice") or "", "")),
            "cost": int((e.findtext("iCost") or "0").strip() or 0),
            "grants": grants,
            "techs": [{"id": t, "name": tech_name(t), "slug": slug_of(t, "TECH_")}
                      for t in prereqs],
            "nations": [{"id": n.text, "name": nation_name(n.text or ""),
                         "slug": slug_of(n.text or "", "NATION_")}
                        for n in e.findall("aeNationValid/zValue") if n.text],
            "culture": culture or None,
            "dlc": (e.findtext("GameContentRequired") or "").strip() or None,
            # bNoFree: can't be handed out by "free tech" effects; bTrash: goes
            # back in the deck when skipped. Both are true of every card today,
            # recorded so a patch that changes one is visible in the diff.
            "noFree": (e.findtext("bNoFree") or "").strip() == "1",
            "trash": (e.findtext("bTrash") or "").strip() == "1",
        })

    out.sort(key=lambda d: (d["techs"][0]["name"] if d["techs"] else "", d["name"]))
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    no_tech = sum(1 for d in out if not d["techs"])
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(out)} discoveries "
          f"({no_tech} with no offering tech, {sum(1 for d in out if d['nations'])} nation-locked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
