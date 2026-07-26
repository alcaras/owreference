#!/usr/bin/env python3
"""
Build src/data/order_economy.json — the per-nation Orders economy comparison.

Everything here is read out of the XML; the page layers *explicit, editable
assumptions* (how many horse/camel tiles a city works, which techs are in)
on top of these rates. No invented constants.

What the XML says about Orders (verified against the effect trees + Source):

  family classes (familyClass.xml → effectCity.xml)
    · Statesmen  EffectCity      +1 Orders/turn in EVERY city of that family
    · Riders     SeatEffectCity  +2 Orders/turn, seat city only
    · Hunters    EffectCity      IMPROVEMENT_CAMP +100%  (doubles camp output)
    · Statesmen  SeatEffectCity  unlocks the Decree project (Civics → Orders).
      project.xml lists BOTH an EffectCityPrereq (the seat) and a
      CapitalEffectPlayerPrereq (Constitution law) — City.cs:9914 ORs them, so
      the seat alone is enough.

  tiles (improvementClass.xml aaiResourceYieldOutput)
    · Pasture on HORSE            +0.5   (TechPrereq TECH_HUSBANDRY)
    · Camp on CAMEL or ELEPHANT   +0.5   (TechPrereq TECH_TRAPPING)
      Cattle/Sheep/Pig/Goat pastures and Game/Fur camps yield NO orders.

  nations
    · Persia  EFFECTCITY_NATION_PERSIA: aaiImprovementClassYield PASTURE
      +0.5 Orders — every pasture, any resource (horse pasture → 1.0 total)
    · Assyria EFFECTUNIT_ASSYRIA: +2 Orders per military kill (event-driven)
    · Tamil   EFFECTCITY_CHOLA: Harbor +1 Orders

  universal buildings / people
    · Garrison (any tier)  +0.5, no tech
    · Sun shrines          +0.5 (TECH_DIVINATION) — Shamash/Ra/Hvar/Melul/Surya
    · World-religion Temple +0.5
    · Pyramids (wonder)    +1
    · every Citizen        +0.1  (EFFECTCITY_CITIZEN)

  NOT orders, despite folklore:
    · Kushite Pyramids  → +4 Legitimacy
    · Aksum Mint Coin   → Money + Legitimacy
      Legitimacy only converts to Orders when characters are OFF
      (City.cs:11896 `if (!game().isCharacters())`), i.e. never in a normal game.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "order_economy.json"

ORDERS = "YIELD_ORDERS"


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def index(name: str) -> dict[str, ET.Element]:
    out = {}
    for e in parse(name).findall("Entry"):
        z = e.findtext("zType")
        if z:
            out[z] = e
    return out


def load_text() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("text-*.xml")):
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        for e in root.findall("Entry"):
            k = e.findtext("zType")
            v = e.findtext("en-US")
            if k and v and k not in out:
                out[k] = re.sub(r"^icon\([^)]*\)", "", v.split("~")[0]).strip()
    return out


def yield_rate(entry: ET.Element | None, tag: str = "aiYieldRate") -> float:
    """Orders value on a `<tag>` pair list, in display units (XML is ×10)."""
    if entry is None:
        return 0.0
    for pair in entry.findall(f"{tag}/Pair"):
        if pair.findtext("zIndex") == ORDERS:
            return int(pair.findtext("iValue") or "0") / 10
    return 0.0


def main() -> int:
    text = load_text()
    ec = index("effectCity.xml")
    impcls = index("improvementClass.xml")
    fam_cls = index("familyClass.xml")

    # ── family-class rates ────────────────────────────────────────────────
    classes: dict[str, dict] = {}
    for cid, e in fam_cls.items():
        if not cid.startswith("FAMILYCLASS_"):
            continue
        per_city = yield_rate(ec.get(e.findtext("EffectCity") or ""))
        seat = yield_rate(ec.get(e.findtext("SeatEffectCity") or ""))
        # camp multiplier (Hunters): aiImprovementModifier IMPROVEMENT_CAMP
        camp_mod = 0
        temple_mod = 0
        city_eff = ec.get(e.findtext("EffectCity") or "")
        if city_eff is not None:
            for pair in city_eff.findall("aiImprovementModifier/Pair"):
                if pair.findtext("zIndex") == "IMPROVEMENT_CAMP":
                    camp_mod = int(pair.findtext("iValue") or "0")
            # Clerics: aiImprovementClassModifier TEMPLE +100 → doubles the
            # world-religion temple's Orders in that family's cities.
            for pair in city_eff.findall("aiImprovementClassModifier/Pair"):
                if pair.findtext("zIndex") == "IMPROVEMENTCLASS_TEMPLE":
                    temple_mod = int(pair.findtext("iValue") or "0")
        # does the seat unlock the Decree project?
        seat_eff = ec.get(e.findtext("SeatEffectCity") or "")
        unlock = (seat_eff.findtext("EffectCityUnlock") or "") if seat_eff is not None else ""
        classes[cid] = {
            "id": cid,
            "name": text.get(e.findtext("Name") or "", cid.replace("FAMILYCLASS_", "").title()),
            "perCity": per_city,
            "seat": seat,
            "campModifier": camp_mod,
            "templeModifier": temple_mod,
            "unlocksDecree": unlock == "EFFECTCITY_FAMILYCLASS_STATESMEN_SEAT_DECREE",
        }

    # ── tile rates (which resource on which improvement class) ────────────
    tiles: dict[str, dict] = {}
    for cid in ("IMPROVEMENTCLASS_PASTURE", "IMPROVEMENTCLASS_CAMP"):
        e = impcls[cid]
        per_res = {}
        for pair in e.findall("aaiResourceYieldOutput/Pair"):
            res = pair.findtext("zIndex") or ""
            for sp in pair.findall("SubPair"):
                if sp.findtext("zSubIndex") == ORDERS:
                    per_res[res.replace("RESOURCE_", "").title()] = int(sp.findtext("iValue") or "0") / 10
        tiles[cid.replace("IMPROVEMENTCLASS_", "").lower()] = {
            "tech": e.findtext("TechPrereq") or "",
            "techName": text.get("TEXT_" + (e.findtext("TechPrereq") or ""), (e.findtext("TechPrereq") or "").replace("TECH_", "").title()),
            "byResource": per_res,
        }

    # tech costs / prereqs for the gating story
    techs = {}
    for e in parse("tech.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if z in ("TECH_TRAPPING", "TECH_HUSBANDRY", "TECH_DIVINATION",
                 "TECH_IRONWORKING", "TECH_CARTOGRAPHY"):
            techs[z] = {
                "name": text.get(e.findtext("Name") or "", z.replace("TECH_", "").title()),
                "cost": int(e.findtext("iCost") or "0"),
                # iColumn is the tech tier, 0-indexed: tiers 1-4 = columns 0-3.
                "tier": int(e.findtext("iColumn") or "0") + 1,
                "prereqs": [p.findtext("zIndex") for p in e.findall("abTechPrereq/Pair")],
            }

    # ── universal building rates ──────────────────────────────────────────
    imps = index("improvement.xml")
    def imp_orders(zid: str) -> float:
        return yield_rate(imps.get(zid), "aiYieldOutput")

    sun_shrines = sorted({
        z for z, e in imps.items()
        if (e.findtext("Class") or "") == "IMPROVEMENTCLASS_SHRINE" and imp_orders(z) > 0
    })
    buildings = {
        "garrison": {"orders": imp_orders("IMPROVEMENT_GARRISON_1"), "tech": imps["IMPROVEMENT_GARRISON_1"].findtext("TechPrereq") or ""},
        "sunShrine": {"orders": imp_orders(sun_shrines[0]) if sun_shrines else 0.0,
                      "tech": impcls["IMPROVEMENTCLASS_SHRINE"].findtext("TechPrereq") or "",
                      "examples": [text.get(imps[z].findtext("Name") or "", z) for z in sun_shrines]},
        "templeWorldReligion": {"orders": imp_orders("IMPROVEMENT_TEMPLE_ZOROASTRIANISM")},
        "pyramidsWonder": {"orders": imp_orders("IMPROVEMENT_PYRAMIDS")},
        "citizen": {"orders": yield_rate(ec.get("EFFECTCITY_CITIZEN"))},
        # YIELD_ORDERS iPerLegitimacy: Player.calculateNonCityYield adds
        # getLegitimacy() * iPerLegitimacy to the rate, ungated. Values are the
        # usual x10 internal scale, so 1 -> 0.1 display Orders per Legitimacy.
        "legitimacyPerOrder": next(
            (int(y.findtext("iPerLegitimacy") or "0") / 10
             for y in parse("yield.xml").findall("Entry")
             if y.findtext("zType") == ORDERS), 0.0),
        # Revelation theology adds Orders to every Temple (improvementClass
        # TEMPLE aaiTheologyYieldOutput) — Clerics then double that too.
        "revelationTemple": {"orders": next(
            (int(sp.findtext("iValue") or "0") / 10
             for pair in impcls["IMPROVEMENTCLASS_TEMPLE"].findall("aaiTheologyYieldOutput/Pair")
             if pair.findtext("zIndex") == "THEOLOGY_REVELATION"
             for sp in pair.findall("SubPair")
             if sp.findtext("zSubIndex") == ORDERS), 0.0)},
    }

    # ── Decree tiers (Civics → Orders conversion) ─────────────────────────
    bonuses = {}
    for p in XML_DIR.glob("bonus*.xml"):
        for e in ET.parse(p).getroot().findall("Entry"):
            z = e.findtext("zType")
            if z:
                bonuses.setdefault(z, e)
    decree = []
    for e in parse("project.xml").findall("Entry"):
        z = e.findtext("zType") or ""
        if not z.startswith("PROJECT_DECREE_"):
            continue
        b = bonuses.get(e.findtext("Bonus") or "")
        gain = 0
        if b is not None:
            for pair in b.findall("aiGlobalYields/Pair"):
                if pair.findtext("zIndex") == ORDERS:
                    gain = int(pair.findtext("iValue") or "0")
        decree.append({
            "id": z,
            "name": text.get(e.findtext("Name") or "", z),
            "civics": int(e.findtext("iCost") or "0"),
            "orders": gain,
            "culture": (e.findtext("RequiresCulture") or "").replace("CULTURE_", "").title(),
        })
    decree.sort(key=lambda d: d["civics"])

    # ── nations: which family classes they can field ──────────────────────
    fams = {}
    for e in parse("family.xml").findall("Entry"):
        z = e.findtext("zType")
        if not z:
            continue
        nats = [p.findtext("zIndex") for p in e.findall("abNation/Pair")
                if (p.findtext("bValue") or "1") == "1"]
        fams[z] = {"class": e.findtext("FamilyClass"), "nations": nats,
                   "name": text.get(e.findtext("Name") or "", z)}

    max_families = 3
    for e in parse("globalsInt.xml").findall("Entry"):
        if e.findtext("zType") == "MAX_FAMILIES":
            max_families = int(e.findtext("iValue") or "3")

    # per-nation special order effects
    def nation_specials(nid: str) -> list[dict]:
        out = []
        if nid == "NATION_PERSIA":
            v = 0.0
            t = ec.get("EFFECTCITY_NATION_PERSIA")
            if t is not None:
                for pair in t.findall("aaiImprovementClassYield/Pair"):
                    if pair.findtext("zIndex") == "IMPROVEMENTCLASS_PASTURE":
                        for sp in pair.findall("SubPair"):
                            if sp.findtext("zSubIndex") == ORDERS:
                                v = int(sp.findtext("iValue") or "0") / 10
            out.append({"kind": "pastureBonus", "value": v,
                        "label": f"+{v} Orders on every Pasture (any resource)"})
        if nid == "NATION_ASSYRIA":
            eu = index("effectUnit.xml").get("EFFECTUNIT_ASSYRIA")
            v = 0
            if eu is not None:
                for pair in eu.findall("aiMilitaryKillYield/Pair"):
                    if pair.findtext("zIndex") == ORDERS:
                        v = int(pair.findtext("iValue") or "0")
            out.append({"kind": "perKill", "value": v,
                        "label": f"+{v} Orders per military kill (event-driven)"})
        if nid == "NATION_YUEZHI":
            # FoundBonus BONUS_NATION_YUEZHI adds a Horse resource to every city
            # it founds — a guaranteed horse pasture per city on top of the map's.
            out.append({"kind": "foundHorse", "value": 1,
                        "label": "+1 Horse resource in every city founded"})
        if nid == "NATION_TAMIL":
            t = ec.get("EFFECTCITY_CHOLA")
            v = 0.0
            if t is not None:
                for pair in t.findall("aaiImprovementClassYield/Pair"):
                    if pair.findtext("zIndex") == "IMPROVEMENTCLASS_HARBOR":
                        for sp in pair.findall("SubPair"):
                            if sp.findtext("zSubIndex") == ORDERS:
                                v = int(sp.findtext("iValue") or "0") / 10
            out.append({"kind": "harbor", "value": v,
                        "label": f"+{v} Orders per Harbor"})
        return out

    # A nation's own city effect can scale every Shrine it builds — Kush's
    # EFFECTCITY_NATION_KUSH carries aiImprovementClassModifier SHRINE +50, so
    # its Sun shrine pays 0.75 Orders rather than 0.5. This applies to the
    # per-adjacent-wonder Kingship output too: Tile.cs:13608 folds
    # maiAdjacentWonderYieldOutput into the same iOutput that
    # City.getImprovementModifierForGovernor scales (Tile.cs:13717 →
    # City.cs:4365), so it is one modifier over the whole shrine yield.
    eff_player = index("effectPlayer.xml")

    def shrine_modifier(entry: ET.Element) -> int:
        epe = eff_player.get(entry.findtext("EffectPlayer") or "")
        if epe is None:
            return 0
        ece = ec.get(epe.findtext("EffectCity") or "")
        if ece is None:
            return 0
        for pair in ece.findall("aiImprovementClassModifier/Pair"):
            if pair.findtext("zIndex") == "IMPROVEMENTCLASS_SHRINE":
                return int(pair.findtext("iValue") or "0")
        return 0

    nations = []
    for e in parse("nation.xml").findall("Entry"):
        nid = e.findtext("zType") or ""
        if not nid or "BARBARIAN" in nid:
            continue
        my = [(z, d) for z, d in fams.items() if nid in d["nations"]]
        start = [t.text for t in e.findall("aeStartingTech/zValue") if t.text]
        def _shrine_type(i):
            m = re.match(r"ASSET_VARIATION_IMPROVEMENT_SHRINE_([A-Z_]+)",
                         i.findtext("AssetVariation") or "")
            return m.group(1).replace("_", " ").title() if m else ""
        # A nation can have MORE than one Orders shrine, and they pay out
        # differently: the Sun shrine is a flat rate (aiYieldOutput) while the
        # Kingship shrine is +1 per ADJACENT WONDER (aiAdjacentWonderYieldOutput).
        shrines = []
        for z, i in imps.items():
            if (i.findtext("Class") or "") != "IMPROVEMENTCLASS_SHRINE":
                continue
            if (i.findtext("NationPrereq") or "") != nid:
                continue
            flat = yield_rate(i, "aiYieldOutput")
            adj = yield_rate(i, "aiAdjacentWonderYieldOutput")
            if not flat and not adj:
                continue
            shrines.append({
                "id": z,
                "name": text.get(i.findtext("Name") or "", z),
                "type": _shrine_type(i),
                "orders": flat or adj,
                "per": "wonder" if adj else "flat",
            })
        shrines.sort(key=lambda x: (x["per"] != "flat", x["name"]))
        shrine = shrines[0] if shrines else None

        cls = sorted({d["class"] for _, d in my if d["class"]})
        nations.append({
            "id": nid,
            "slug": nid.replace("NATION_", "").lower(),
            "name": text.get(e.findtext("GenderedName") or "", nid.replace("NATION_", "").title()).split(",")[0],
            "dlc": e.findtext("GameContentRequired") or "",
            "familyCount": len(my),
            "classes": cls,
            "families": sorted([{"id": z, "name": d["name"], "class": d["class"]} for z, d in my],
                               key=lambda f: f["name"]),
            "startingTechs": start,
            "startingTechNames": [text.get("TEXT_" + t, t.replace("TECH_", "").title()) for t in start],
            "ordersShrine": shrine,
            "ordersShrines": shrines,
            "shrineModifier": shrine_modifier(e),
            "specials": nation_specials(nid),
        })
    nations.sort(key=lambda n: n["name"])

    # ── Legitimacy sources that a Schemer leader can convert into Orders ──
    # Kushite Pyramids: one per city (iMaxCityCount 1), +4 Legitimacy each.
    # Aksum's Mint Coin: a single upgrading project, each tier REPLACING the
    # last, so you hold only the current tier's Legitimacy.
    legit = {}
    kp = ec.get("EFFECTCITY_IMPROVEMENT_KUSHITE_PYRAMIDS")
    if kp is not None:
        legit["kushitePyramid"] = {"perCity": int(kp.findtext("iLegitimacy") or "0"),
                                   "name": text.get("TEXT_IMPROVEMENT_KUSHITE_PYRAMIDS", "Kushite Pyramids")}
    mint = []
    for e2 in parse("project-event.xml").findall("Entry"):
        z2 = e2.findtext("zType") or ""
        if not z2.startswith("PROJECT_MINT_COIN_") or not z2[-1].isdigit():
            continue
        t = ec.get(e2.findtext("EffectCity") or "")
        mint.append({
            "id": z2,
            "legitimacy": int(t.findtext("iLegitimacy") or "0") if t is not None else 0,
            "culture": (e2.findtext("MinimumCulture") or "").replace("CULTURE_", "").title(),
        })
    mint.sort(key=lambda m: m["legitimacy"])
    if mint:
        legit["aksumMintCoin"] = mint

    out = {
        "legitimacy": legit,
        "convertLegitimacy": {
            "flatCost": next((int(g.findtext("iValue") or "0") for g in parse("globalsInt.xml").findall("Entry")
                              if g.findtext("zType") == "CONVERT_LEGITIMACY_FLAT_COST"), 0),
            "orders": next((int(sp.findtext("iValue") or "0")
                            for f in XML_DIR.glob("bonus*.xml")
                            for b in ET.parse(f).getroot().findall("Entry")
                            if b.findtext("zType") == "BONUS_CONVERT_LEGITIMACY"
                            for sp in b.findall("aiGlobalYields/Pair")
                            if sp.findtext("zIndex") == ORDERS), 0),
        },
        "maxFamilies": max_families,
        "classes": classes,
        "tiles": tiles,
        "techs": techs,
        "buildings": buildings,
        "decree": decree,
        "nations": nations,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(nations)} nations, "
          f"{sum(1 for c in classes.values() if c['perCity'] or c['seat'] or c['campModifier'])} order-relevant family classes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
