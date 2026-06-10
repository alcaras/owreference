#!/usr/bin/env python3
"""
Build src/data/council.json from council.xml + council-btt.xml + courtier.xml.

Two sections:

  • seats — the Council positions (Ambassador, Chancellor, Spymaster, plus the
    Behind the Throne Grand Vizier). Each seat's yield/opinion output scales
    with the seated character's ratings — and per the game source
    (InfoHelpers.getRatingYieldRateCouncil → modifyRating → triangleOffset with
    offset 0) the scaling is TRIANGULAR, not linear: a rating of R multiplies
    the base by R·(R+1)/2. The Jobs page renders these as flat "per Rating"
    raw-unit strings; here we keep the structured base values (÷10 for display
    units, per CLAUDE.md) and let the page explain the triangle.

  • courtiers — the four courtier types. courtier.xml expresses each type's
    rating roll (aiRatingBase + random(aiRatingRand), see
    Character.generateRatingsCourtier: base + randomNext(rand) → range
    base … base+rand-1), one archetype rolled from aiArchetypeDie and one
    adjective trait rolled from aiAdjectiveDie (weighted dice). Acquisition is
    not in courtier.xml — courtiers arrive via bonus.xml AddCourtier /
    AddCourtierOther / bRandomCourtier, which we trace back to their sources
    (events, tech bonus cards, real techs, the Patrons family seat, Hold Court).

Also emits a small meta block: courtiers join at age COURTIER_AGE (25) and
contribute the standard court rating yields at COURTIER_YIELD_MODIFIER (-67%,
i.e. 33% of a leader's rate).
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import load_xml_indexes, _lookup_name, yield_name, fmt_decimal  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "council.json"

RATING_LABELS: dict[str, str] = {
    "RATING_WISDOM": "Wisdom",
    "RATING_CHARISMA": "Charisma",
    "RATING_COURAGE": "Courage",
    "RATING_DISCIPLINE": "Discipline",
}

DLC_LABELS: dict[str, str] = {
    # EVENTPACK_SCANDAL is the internal id of the Behind the Throne event pack
    # (council-btt.xml — "btt").
    "EVENTPACK_SCANDAL": "Behind the Throne",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def pairs(entry: ET.Element, tag: str) -> list[tuple[str, int]]:
    out = []
    for p in entry.findall(f"{tag}/Pair"):
        out.append((p.findtext("zIndex") or "", int(p.findtext("iValue") or "0")))
    return out


class Names:
    """Resolve display names through genderedText.xml / trait.xml / tech.xml."""

    def __init__(self, indexes: dict):
        self.indexes = indexes
        # genderedText*.xml: GENDERED_TEXT_X → masculine TEXT_* token → en-US
        self.gendered: dict[str, str] = {}
        for p in sorted(XML_DIR.glob("genderedText*.xml")):
            for e in ET.parse(p).getroot().findall("Entry"):
                z = e.findtext("zType") or ""
                if not z:
                    continue
                for pr in e.findall("Texts/Pair"):
                    if pr.findtext("zIndex") == "GRAMMATICAL_GENDER_MASCULINE":
                        nm = _lookup_name(indexes, pr.findtext("zValue") or "")
                        if nm:
                            self.gendered.setdefault(z, nm)

    def gendered_name(self, token: str, fallback: str) -> str:
        return self.gendered.get(token) or fallback

    def trait(self, trait_id: str) -> str:
        # trait.xml entries carry no <Name>; the text key is TEXT_<zType>.
        nm = _lookup_name(self.indexes, f"TEXT_{trait_id}")
        if nm:
            return nm
        return trait_id.replace("TRAIT_", "").replace("_ARCHETYPE", "").replace("_", " ").title()

    def archetype(self, trait_id: str) -> str:
        # "A Rising Star"-style names are fine for plain traits, but archetype
        # chips read better bare ("Hero", "Scholar").
        return self.trait(trait_id)

    def tech(self, tech_id: str) -> str:
        entry = self.indexes.get("tech.xml", {}).get(tech_id)
        if entry is not None:
            nm = _lookup_name(self.indexes, entry.findtext("Name") or "")
            if nm:
                return nm
        return tech_id.replace("TECH_", "").replace("_", " ").title()


def build_seats(names: Names, indexes: dict) -> list[dict]:
    entries: list[ET.Element] = []
    for fn in ("council.xml", "council-btt.xml"):
        p = XML_DIR / fn
        if p.exists():
            entries.extend(e for e in ET.parse(p).getroot().findall("Entry") if e.findtext("zType"))

    seats: list[dict] = []
    for e in entries:
        zid = e.findtext("zType") or ""
        slug = zid.replace("COUNCIL_", "").lower()
        name = names.gendered_name(e.findtext("GenderedName") or "",
                                   zid.replace("COUNCIL_", "").replace("_", " ").title())

        tech_prereq = ""
        ep_prereq = e.findtext("EffectPlayerPrereq") or ""
        if ep_prereq.startswith("EFFECTPLAYER_TECH_"):
            tech_prereq = names.tech(ep_prereq.replace("EFFECTPLAYER_", ""))

        trait_prereqs = sorted(
            names.archetype(p.findtext("zIndex") or "")
            for p in e.findall("abTraitPrereq/Pair")
            if (p.findtext("bValue") or "0") == "1"
        )

        # Rating-scaled yields. XML values are rate units (10 = 1.0/turn
        # display); base = value at rating 1 (triangle(1) == 1).
        rating_yields: list[dict] = []
        for scope_tag, scope in (("aaiRatingYieldGlobal", "empire"), ("aaiRatingYieldCity", "per city")):
            for pr in e.findall(f"{scope_tag}/Pair"):
                rating = RATING_LABELS.get(pr.findtext("zIndex") or "", pr.findtext("zIndex") or "")
                for sp in pr.findall("SubPair"):
                    y = yield_name(sp.findtext("zSubIndex"))
                    raw = int(sp.findtext("iValue") or "0")
                    base = raw / 10
                    suffix = "/City" if scope == "per city" else ""
                    rating_yields.append({
                        "rating": rating,
                        "yield": y,
                        "scope": scope,
                        "base": base,
                        "text": f"{fmt_decimal(base)} {y}{suffix} × tri({rating})",
                    })

        # Rating-scaled opinion. Also triangular (InfoHelpers.getPlayerOpinionCouncil
        # → modifyRating offset 0, rounded out to 5); player opinion is disabled
        # in all-human (MP) games.
        rating_opinions: list[dict] = []
        for tag, target in (("aiPlayerOpinion", "Foreign Leader"),
                            ("aiTribeOpinion", "Tribe"),
                            ("aiReligionOpinion", "Religion"),
                            ("aiFamilyOpinion", "Family")):
            for rid, v in pairs(e, tag):
                rating = RATING_LABELS.get(rid, rid)
                rating_opinions.append({
                    "rating": rating,
                    "target": target,
                    "base": v,
                    "text": f"+{v} {target} Opinion × tri({rating})",
                })

        # Flat EffectPlayer riders the humanizer doesn't cover:
        other_effects: list[str] = []
        ep_id = e.findtext("EffectPlayer") or ""
        if ep_id:
            ep = indexes.get("effectPlayer.xml", {}).get(ep_id)
            if ep is not None:
                # Spymaster: <bAgent>1</bAgent> unlocks the Agent job in foreign
                # cities (Player.cs changeAgentUnlock).
                if ep.findtext("bAgent") == "1":
                    other_effects.append("Unlocks Agents in foreign cities")
                # Grand Vizier: NoGovernorEffectCity → EFFECTCITY_SHARED_POWER:
                # the Vizier acts as default Governor of every governor-less
                # city, with auto-build and no hurrying (Shared Power scandal).
                if ep.findtext("NoGovernorEffectCity"):
                    other_effects.append(
                        "Acts as default Governor in every city without one (auto-build, no hurrying)")

        seats.append({
            "id": zid,
            "slug": slug,
            "name": name,
            "dlc": DLC_LABELS.get(e.findtext("GameContentRequired") or "", e.findtext("GameContentRequired") or ""),
            "techPrereq": tech_prereq,
            "traitPrereqs": trait_prereqs,
            "assignOpinion": int(e.findtext("iOpinion") or "0"),
            "xpPerTurn": int(e.findtext("iXP") or "0"),
            "mission": (e.findtext("AssignMission") or "").replace("MISSION_", "").title(),
            "ratingYields": rating_yields,
            "ratingOpinions": rating_opinions,
            "otherEffects": other_effects,
        })
    return seats


def build_acquisition(names: Names) -> dict[str, list[str]]:
    """Trace how each courtier type is acquired: bonus.xml AddCourtier /
    AddCourtierOther → events that pay the bonus, techs whose BonusDiscover
    grants it, and the Patrons seat-founding bonus."""
    bonus_to_courtier: dict[str, str] = {}
    for e in parse("bonus.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        for tag in ("AddCourtier", "AddCourtierOther"):
            for pr in e.findall(f"{tag}/Pair"):
                cid = pr.findtext("First") or ""
                if cid:
                    bonus_to_courtier[z] = cid

    acq: dict[str, list[str]] = {}

    def add(cid: str, line: str) -> None:
        acq.setdefault(cid, []).append(line)

    # Techs: real techs grant on discovery; bTrash entries are bonus cards in
    # the tech deck. NOTE: bonus-card zTypes are legacy and do NOT match their
    # actual prereq (TECH_FORESTRY_BONUS_SCIENTIST requires Metaphysics!) —
    # always read abTechPrereq.
    for e in parse("tech.xml").findall("Entry"):
        bd = e.findtext("BonusDiscover") or ""
        cid = bonus_to_courtier.get(bd)
        if not cid:
            continue
        tname = _lookup_name(names.indexes, e.findtext("Name") or "")
        prereqs = [p.findtext("zIndex") or "" for p in e.findall("abTechPrereq/Pair")]
        if e.findtext("bTrash") == "1" and prereqs:
            add(cid, f"Tech bonus card (after {names.tech(prereqs[0])})")
        elif e.findtext("bTrash") == "1":
            # TECH_EVENT_BONUS_MINISTER: a prereq-less card events shuffle
            # into the tech deck.
            add(cid, "Tech bonus card (added to the deck by events)")
        else:
            add(cid, f"Discovering {tname or names.tech(e.findtext('zType') or '')}")

    # Family seat (BONUS_FAMILYCLASS_PATRONS_SEAT is the Patrons SeatFoundBonus)
    for e in parse("familyClass.xml").findall("Entry"):
        sfb = e.findtext("SeatFoundBonus") or ""
        cid = bonus_to_courtier.get(sfb)
        if cid:
            cls = (e.findtext("zType") or "").replace("FAMILYCLASS_", "").title()
            add(cid, f"Founding a {cls} family seat")

    # Events: count occurrences of each BONUS_ADD_GREAT_* across event XML
    event_bonuses = {b: c for b, c in bonus_to_courtier.items() if b.startswith("BONUS_ADD_GREAT_")}
    counts: dict[str, int] = {b: 0 for b in event_bonuses}
    for p in sorted(XML_DIR.glob("event*.xml")):
        txt = p.read_text(errors="ignore")
        for b in counts:
            counts[b] += txt.count(b)
    for b, cid in sorted(event_bonuses.items()):
        if counts[b]:
            add(cid, f"Event rewards ({counts[b]} event options)")

    return acq


def build_courtiers(names: Names, acquisition: dict[str, list[str]]) -> list[dict]:
    out: list[dict] = []
    for e in parse("courtier.xml").findall("Entry"):
        zid = e.findtext("zType") or ""
        if not zid:
            continue
        slug = zid.replace("COURTIER_", "").lower()
        name = names.gendered_name(e.findtext("GenderedName") or "",
                                   zid.replace("COURTIER_", "").replace("_", " ").title())
        nickname = names.gendered_name(e.findtext("GenderedNickname") or "", "")

        base = dict(pairs(e, "aiRatingBase"))
        rand = dict(pairs(e, "aiRatingRand"))
        ratings = []
        for rid in sorted(set(base) | set(rand)):
            b = base.get(rid, 0)
            r = rand.get(rid, 0)
            # Character.generateRatingsCourtier: base + randomNext(rand),
            # randomNext(N) ∈ [0, N-1] → range base … base+rand-1.
            ratings.append({
                "rating": RATING_LABELS.get(rid, rid),
                "min": b,
                "max": b + max(r - 1, 0),
            })

        def die(tag: str) -> list[dict]:
            rolls = pairs(e, tag)
            total = sum(v for _, v in rolls) or 1
            return [{
                "trait": names.trait(tid),
                "weight": v,
                "pct": round(100 * v / total, 1),
            } for tid, v in rolls]

        out.append({
            "id": zid,
            "slug": slug,
            "name": name,
            "nickname": nickname,
            "ratings": ratings,
            "archetypeDie": die("aiArchetypeDie"),
            "adjectiveDie": die("aiAdjectiveDie"),
            "acquisition": sorted(acquisition.get(zid, [])),
        })
    return out


def build_meta(names: Names) -> dict:
    g_int = {e.findtext("zType"): int(e.findtext("iValue") or "0")
             for e in parse("globalsInt.xml").findall("Entry") if e.findtext("zType")}
    courtier_mod = g_int.get("COURTIER_YIELD_MODIFIER", -67)

    # Court income scales triangularly too, but with each yield's own
    # iTriangleOffset (InfoHelpers.getRatingYieldRateCourt passes
    # yield.miTriangleOffset, unlike council seats which pass 0).
    yield_offsets = {
        (e.findtext("zType") or ""): int(e.findtext("iTriangleOffset") or "0")
        for e in parse("yield.xml").findall("Entry") if e.findtext("zType")
    }

    # rating.xml aiYieldCourtRate: what every court character (leader at 100%)
    # produces per rating; courtiers get it at 100+COURTIER_YIELD_MODIFIER %.
    court_rates = []
    for e in parse("rating.xml").findall("Entry"):
        rid = e.findtext("zType") or ""
        for p in e.findall("aiYieldCourtRate/Pair"):
            yid = p.findtext("zIndex") or ""
            raw = int(p.findtext("iValue") or "0")
            # Utils.modify: value * (100 + modifier) / 100, integer division.
            courtier_raw = raw * (100 + courtier_mod) // 100
            court_rates.append({
                "rating": RATING_LABELS.get(rid, rid),
                "yield": yield_name(yid),
                "full": raw / 10,
                "courtier": courtier_raw / 10,
                "triangleOffset": yield_offsets.get(yid, 0),
            })

    return {
        "courtierAge": g_int.get("COURTIER_AGE", 25),
        "courtierYieldModifier": courtier_mod,
        "courtRates": court_rates,
        "randomSources": [
            # bonus.xml bRandomCourtier consumers (missionResult.xml)
            "Hold Court mission result (random courtier type)",
            "Court of the Divine King (random courtier type)",
        ],
        "notes": [
            "Courtiers join the court at age 25 and count as court characters: "
            "each rating point yields court income at 33% of the leader's rate.",
            "A new courtier rolls one archetype and one adjective trait from "
            "weighted dice, plus a rating in their specialty.",
        ],
    }


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    names = Names(indexes)

    seats = build_seats(names, indexes)
    acquisition = build_acquisition(names)
    courtiers = build_courtiers(names, acquisition)
    meta = build_meta(names)

    data = {"courtiers": courtiers, "meta": meta, "seats": seats}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(seats)} seats, {len(courtiers)} courtiers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
