#!/usr/bin/env python3
"""
Build src/data/religious_spread.json — how a religion gets into a city: the
per-turn roll, which city the roll picks, Disciples, religious improvements,
tribal settlements, what blocks spread, and where a new religion is founded.

The passive spread is two functions in Game.cs, run once per game turn from
Game.doTurn (after the war scores, before founding):

  Game.getReligionSpread(religion)                       → percent per turn
      religion.xml iSpreadPercent
    + mapSize.xml iSpreadChange              (world religions only)
    + Σ theology.xml iSpreadChange           (every theology the religion has)
    + Σ over EVERY player whose state religion it is: effectPlayer
        iStateReligionSpread                 (Pilgrimage, Pious leader, Pax Kushana)
    + Σ over EVERY player: effectPlayer iWorldReligionSpread
                                             (Religious Upheaval — all religions)
  Game.doReligionSpread: for each founded religion without bNoSpread,
      randomPercent(chance) → Game.spreadReligion(religion)

  Game.spreadReligion(religion) — needs a Holy City, then picks ONE target:
      for every city on the map that isReligionSpreadEligible:
          d  = hex distance to the Holy City
          d  = Utils.modify(d, RELIGION_SPREAD_CONNECTION_DISTANCE_MODIFIER)
               if the city is on the Holy City team's trade network (−33 → ×67/100)
          D  = d × (religions already in the city + 1)
          score = D × (random 0..D−1 + 1)
      then (world religions only) every tribal settlement of a diplomacy tribe
      that has NO religion yet:
          D = distance, score = D × (random 0..D−1 + 1)
      lowest score wins; ties keep the one checked first (cities before sites)

  City.isReligionSpreadEligible: not already there, not banned by a Purge,
      a world religion (or the owner's own pagan one), and — if the city carries
      an effectCity with bNoReligionSpread (Iconography, SaP Dissent) — only the
      owner's state religion.

The scoring and the founding weights are code, not XML; they are recorded here
with their line numbers and watched by verify_source_constants.py.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dlc import dlc_by_content  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
SRC = ROOT / "reference" / "Source" / "Base" / "Game" / "GameCore"
OUT = ROOT / "src" / "data" / "religious_spread.json"
ENTITIES = ROOT / "src" / "data" / "entities.json"

# Game.getReligionCityFoundValue (Game.cs): the founding city is the highest
# sum of these, over cities that meet every prereq; equal sums are broken by a
# shuffle. Source-only constants, watched in verify_source_constants.py.
FOUND_WEIGHTS = [
    ("notHolyCity", 64000, "the city is not already the Holy City of any religion"),
    ("noHolyCityOwner", 32000, "its owner has no world-religion Holy City yet"),
    ("notCapital", 16000, "the city is not a capital"),
    ("human", 8000, "its owner is a human player"),
    ("dynasty", 4000, "its owner's dynasty prefers this religion"),
]


# ---------------------------------------------------------------- helpers ---
def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("text-*.xml")):
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            if k and k not in out:
                out[k] = e.findtext("en-US") or ""
    return out


_ICON_RE = re.compile(r"icon\([A-Z_]+\)")
_LINK_RE = re.compile(r"link\(([A-Z_]+)(?:,\d+)?\)")


def clean(s: str) -> str:
    s = (s or "").split("~")[0]
    return _ICON_RE.sub("", s).strip()


def int_of(e: ET.Element, tag: str, default: int = 0) -> int:
    t = e.findtext(tag)
    return int(t) if t not in (None, "") else default


def pairs(e: ET.Element, tag: str) -> list[tuple[str, int]]:
    out = []
    for p in e.findall(f"{tag}/Pair"):
        k, v = p.findtext("zIndex") or "", int(p.findtext("iValue") or 0)
        if k and v:
            out.append((k, v))
    return out


def find_line(path: Path, needle: str) -> int:
    for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if needle in line:
            return i
    raise SystemExit(f"{path.name}: `{needle}` not found — re-check the citation")


def cite(file: str, needle: str) -> str:
    return f"{file}:{find_line(SRC / file, needle)}"


def globals_int() -> dict[str, int]:
    out = {}
    for e in parse("globalsInt.xml").findall("Entry"):
        z, v = e.findtext("zType"), e.findtext("iValue")
        if z and v not in (None, ""):
            out[z] = int(v)
    return out


# ------------------------------------------------------------------ main ---
def main() -> None:
    text = load_text()
    dlc = dlc_by_content()
    gi = globals_int()
    ents = {e["id"]: e for e in json.loads(ENTITIES.read_text())["entities"]}

    def name_of(e: ET.Element, prefix: str) -> str:
        n = e.findtext("Name") or ""
        if not n and e.findtext("GenderedName"):
            n = (e.findtext("GenderedName") or "").replace("GENDERED_TEXT_", "TEXT_")
        t = clean(text.get(n, ""))
        if t:
            return t
        zid = e.findtext("zType") or ""
        return zid.removeprefix(prefix).replace("_", " ").title()

    def ent_name(eid: str, fallback: str) -> str:
        e = ents.get(eid)
        return e["name"] if e and "{" not in e["name"] else fallback

    def ref(eid: str, name: str) -> dict:
        return {"id": eid, "name": name, "linked": eid in ents}

    by_id = {}
    for fn in ("religion.xml", "tech.xml", "law.xml", "specialist.xml", "specialistClass.xml",
               "improvement.xml", "improvementClass.xml", "theology.xml", "mapSize.xml",
               "trait.xml", "occurrence.xml", "project-event-sap.xml", "tribe.xml",
               "dynasty.xml", "unit.xml"):
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            z = e.findtext("zType")
            if z:
                by_id[z] = e

    def label(zid: str, prefix: str) -> str:
        e = by_id.get(zid)
        return ent_name(zid, name_of(e, prefix) if e is not None else zid.removeprefix(prefix).title())

    # ---- religions -------------------------------------------------------
    religions = []
    for e in parse("religion.xml").findall("Entry"):
        rid = e.findtext("zType") or ""
        if not rid:
            continue
        pagan_nations = [p.text for p in e.findall("PaganNations/zValue") if p.text]
        pagan = bool(e.findtext("PaganNation")) or bool(pagan_nations)
        if e.findtext("bNotWorldOrPagan") == "1":
            continue
        name = name_of(e, "RELIGION_")
        prereqs: list[dict] = []
        if e.findtext("RequiresTech"):
            t = e.findtext("RequiresTech")
            prereqs.append({"kind": "tech", "text": "tech", **ref(t, label(t, "TECH_"))})
        if e.findtext("RequiresLaw"):
            t = e.findtext("RequiresLaw")
            prereqs.append({"kind": "law", "text": "law in force", **ref(t, label(t, "LAW_"))})
        if int_of(e, "iRequiresCitizens"):
            prereqs.append({"kind": "citizens", "count": int_of(e, "iRequiresCitizens"),
                            "text": "Citizens across all your cities"})
        if int_of(e, "iRequiresTheologies"):
            prereqs.append({"kind": "theologies", "count": int_of(e, "iRequiresTheologies"),
                            "text": "Theologies established in the world, by any religion"})
        for other, n in pairs(e, "aiRequiresReligion"):
            prereqs.append({"kind": "religionCities", "count": n,
                            "text": "cities anywhere on the map (any owner) following",
                            **ref(other, label(other, "RELIGION_"))})
        for sp, n in pairs(e, "aiRequiresSpecialist"):
            prereqs.append({"kind": "specialist", "count": n, "text": "of your specialists",
                            **ref(sp, label(sp, "SPECIALIST_"))})
        for sp, n in pairs(e, "aiRequiresSpecialistClass"):
            prereqs.append({"kind": "specialist", "count": n, "text": "of your specialists (any tier)",
                            **ref(sp, label(sp, "SPECIALISTCLASS_"))})
        for imp, n in pairs(e, "aiRequiresImprovement"):
            prereqs.append({"kind": "improvement", "count": n, "text": "active",
                            **ref(imp, label(imp, "IMPROVEMENT_"))})
        for cls, n in pairs(e, "aiRequiresImprovementClass"):
            prereqs.append({"kind": "improvement", "count": n, "text": "active",
                            **ref(cls, label(cls, "IMPROVEMENTCLASS_"))})
        if e.findtext("bRequiresCapital") == "1":
            prereqs.append({"kind": "capital", "text": "founded in your capital"})
        if int_of(e, "iRequiresLaws"):
            prereqs.append({"kind": "laws", "count": int_of(e, "iRequiresLaws"), "text": "laws in force"})
        if int_of(e, "iRequiresReligionsCity"):
            prereqs.append({"kind": "cityReligions", "count": int_of(e, "iRequiresReligionsCity"),
                            "text": "religions already in the city"})
        if e.findtext("RequiresReligion"):
            t = e.findtext("RequiresReligion")
            prereqs.append({"kind": "cityReligion", "text": "the city must follow",
                            **ref(t, label(t, "RELIGION_"))})
        if e.findtext("RequiresCulture"):
            prereqs.append({"kind": "culture", "text": "city culture at least " + label(e.findtext("RequiresCulture"), "CULTURE_")})
        religions.append({
            "id": rid,
            "name": name,
            "slug": rid.removeprefix("RELIGION_").lower(),
            "world": not pagan,
            "pagan": pagan,
            "hidden": e.findtext("bHidden") == "1",
            "noSpread": e.findtext("bNoSpread") == "1",
            "spreadPercent": int_of(e, "iSpreadPercent"),
            "foundingProject": e.findtext("FoundingProject") or "",
            "dlc": dlc.get(e.findtext("GameContentRequired") or "", None),
            "spreadUnit": e.findtext("SpreadUnit") or "",
            "prereqs": prereqs,
        })
    world = [r for r in religions if r["world"]]
    rolling = [r for r in world if not r["noSpread"]]
    assert rolling, "no world religion rolls for passive spread — XML shape changed?"

    # ---- map size --------------------------------------------------------
    map_sizes = []
    for e in parse("mapSize.xml").findall("Entry"):
        z = e.findtext("zType")
        if z:
            map_sizes.append({"id": z, "name": name_of(e, "MAPSIZE_"), "spreadChange": int_of(e, "iSpreadChange")})

    # ---- theologies ------------------------------------------------------
    theologies = []
    for e in parse("theology.xml").findall("Entry"):
        z = e.findtext("zType")
        if z and int_of(e, "iSpreadChange"):
            theologies.append({**ref(z, label(z, "THEOLOGY_")), "spreadChange": int_of(e, "iSpreadChange"),
                               "tier": int_of(e, "iTier", -1)})
    theologies.sort(key=lambda t: (-t["spreadChange"], t["name"]))

    # ---- player-level spread changes, with who carries them ---------------
    ep_root = parse("effectPlayer.xml")
    carriers: dict[str, list[dict]] = {}

    def add_carrier(ep: str, c: dict) -> None:
        carriers.setdefault(ep, []).append(c)

    for e in parse("law.xml").findall("Entry"):
        if e.findtext("EffectPlayer"):
            z = e.findtext("zType")
            add_carrier(e.findtext("EffectPlayer"), {"kind": "law", **ref(z, label(z, "LAW_"))})
    for e in parse("trait.xml").findall("Entry"):
        z = e.findtext("zType")
        for tag, note in (("EffectPlayer", ""), ("LeaderEffectPlayer", "while leader")):
            if e.findtext(tag):
                add_carrier(e.findtext(tag), {"kind": "trait", "note": note, **ref(z, label(z, "TRAIT_"))})
    for e in parse("occurrence.xml").findall("Entry"):
        z = e.findtext("zType")
        if e.findtext("EffectPlayer"):
            add_carrier(e.findtext("EffectPlayer"), {"kind": "occurrence", "dlc": dlc.get(e.findtext("GameContentRequired") or "", None),
                                                      **ref(z, label(z, "OCCURRENCE_"))})
    for e in parse("dynasty.xml").findall("Entry"):
        z = e.findtext("zType")
        if e.findtext("EffectPlayer"):
            add_carrier(e.findtext("EffectPlayer"), {"kind": "dynasty", **ref(z, label(z, "DYNASTY_"))})
    for e in parse("nation.xml").findall("Entry"):
        z = e.findtext("zType")
        if e.findtext("EffectPlayer"):
            add_carrier(e.findtext("EffectPlayer"), {"kind": "nation", **ref(z, label(z, "NATION_"))})

    player_effects = []
    for e in ep_root.findall("Entry"):
        z = e.findtext("zType") or ""
        for tag, scope in (("iStateReligionSpread", "state"), ("iWorldReligionSpread", "world")):
            v = int_of(e, tag)
            if v:
                cs = carriers.get(z, [])
                assert cs, f"{z} sets {tag} but nothing carries it — find the carrier"
                player_effects.append({"effectPlayer": z, "scope": scope, "value": v, "carriers": cs})
    player_effects.sort(key=lambda p: (p["scope"] != "state", -p["value"]))

    # ---- what blocks passive spread (bNoReligionSpread) --------------------
    blockers = []
    no_spread_ec = {e.findtext("zType") for e in parse("effectCity.xml").findall("Entry")
                    if e.findtext("bNoReligionSpread") == "1"}
    for e in ep_root.findall("Entry"):
        for tag in ("EffectCity", "EffectCityExtra"):
            if e.findtext(tag) in no_spread_ec:
                for c in carriers.get(e.findtext("zType"), []):
                    blockers.append({"effectCity": e.findtext(tag), **c})
    dissent = []
    for fn in sorted(XML_DIR.glob("project*.xml")):
        for e in ET.parse(fn).getroot().findall("Entry"):
            if e.findtext("EffectCity") in no_spread_ec:
                z = e.findtext("zType")
                rel = (e.findtext("EffectCityPrereq") or "").replace("EFFECTCITY_RELIGION_", "RELIGION_")
                dissent.append({**ref(z, label(z, "PROJECT_")), "religion": rel,
                                "hidden": e.findtext("bHidden") == "1",
                                "dlc": dlc.get(e.findtext("GameContentRequired") or "", None)})
    suppress = []
    for fn in sorted(XML_DIR.glob("project*.xml")):
        for e in ET.parse(fn).getroot().findall("Entry"):
            if e.findtext("EffectCityPrereq") in no_spread_ec and e.findtext("zType", "").startswith("PROJECT_SUPPRESS"):
                cost = pairs(e, "aiYieldCost")
                suppress.append({"id": e.findtext("zType"), "cost": [{"yield": y, "value": v} for y, v in cost],
                                 "requiresGovernor": e.findtext("bRequiresGovernor") == "1"})
    covered = {b["effectCity"] for b in blockers} | {"EFFECTCITY_" + d["id"].removeprefix("PROJECT_") for d in dissent}
    assert no_spread_ec <= covered, f"bNoReligionSpread effects with no carrier on the page: {no_spread_ec - covered}"

    # ---- improvements that spread their religion when finished ------------
    spread_imps: dict[tuple[str, str], dict] = {}
    for fn in sorted(XML_DIR.glob("improvement*.xml")):
        for e in ET.parse(fn).getroot().findall("Entry"):
            rel = e.findtext("ReligionSpread")
            if not rel:
                continue
            z = e.findtext("zType") or ""
            cls = e.findtext("Class") or ""
            key = (cls if cls == "IMPROVEMENTCLASS_SHRINE" else z, rel)
            row = spread_imps.setdefault(key, {
                "religion": rel, "religionName": label(rel, "RELIGION_"),
                "class": cls, "count": 0, "members": [],
                "wonder": e.findtext("bWonder") == "1",
            })
            row["count"] += 1
            row["members"].append(ref(z, label(z, "IMPROVEMENT_")))
    spread_imps_list = sorted(spread_imps.values(), key=lambda r: (r["class"] != "IMPROVEMENTCLASS_SHRINE", r["religionName"]))

    # ---- tribes the roll can reach ----------------------------------------
    tribes = []
    for e in parse("tribe.xml").findall("Entry"):
        z = e.findtext("zType")
        if z and e.findtext("bDiplomacy") == "1":
            tribes.append(ref(z, label(z, "TRIBE_")))

    # ---- founding ---------------------------------------------------------
    dynasty_pref = []
    for e in parse("dynasty.xml").findall("Entry"):
        if e.findtext("PreferredReligion"):
            z = e.findtext("zType")
            dynasty_pref.append({**ref(z, label(z, "DYNASTY_")), "religion": e.findtext("PreferredReligion"),
                                 "religionName": label(e.findtext("PreferredReligion"), "RELIGION_"),
                                 "nation": label(e.findtext("Nation") or "", "NATION_")})

    # ---- Disciples: training cost and who can train one out of religion ---
    units = {e.findtext("zType"): e for e in parse("unit.xml").findall("Entry")}
    spread_units = sorted({r["spreadUnit"] for r in religions if r["spreadUnit"]})
    costs = {(int_of(units[u], "iProduction"), int_of(units[u], "iProductionCity"), units[u].findtext("ProductionType") or "")
             for u in spread_units if u in units}
    assert len(costs) == 1, f"Disciples no longer share one cost: {costs}"
    prod, prod_city, prod_yield = costs.pop()
    any_religion = []
    for e in parse("effectCity.xml").findall("Entry"):
        us = [z.text for z in e.findall("aeBuildAnyReligionUnit/zValue") if z.text]
        if us:
            any_religion.append({"effectCity": e.findtext("zType"),
                                 "units": [label(u, "UNIT_") if "{" not in label(u, "UNIT_") else
                                           next((r["name"] for r in religions if r["spreadUnit"] == u), u) for u in us]})
    disciple = {"production": prod, "productionPerCity": prod_city, "yield": prod_yield, "anyReligion": any_religion}

    conn = gi["RELIGION_SPREAD_CONNECTION_DISTANCE_MODIFIER"]
    data = {
        "religions": religions,
        "mapSizes": map_sizes,
        "theologies": theologies,
        "playerEffects": player_effects,
        "blockers": blockers,
        "dissent": dissent,
        "suppress": suppress,
        "spreadImprovements": spread_imps_list,
        "tribes": tribes,
        "disciple": disciple,
        "globals": {
            "connectionModifier": conn,
            "connectionMultiplier": 100 + conn,
            "tribeSpreadBase": gi["TRIBE_SPREAD_RELIGION_BASE"],
            "tribeSpreadPer": gi["TRIBE_SPREAD_RELIGION_PER"],
            "purgeOrders": gi["UNIT_PURGE_COST"],
        },
        "founding": {
            "weights": [{"key": k, "value": v, "text": t} for k, v, t in FOUND_WEIGHTS],
            "dynastyPreferences": dynasty_pref,
        },
        "code": {
            "doTurn": cite("Game.cs", "doReligionSpread();"),
            "getReligionSpread": cite("Game.cs", "public virtual int getReligionSpread("),
            "doReligionSpread": cite("Game.cs", "protected virtual void doReligionSpread("),
            "spreadReligion": cite("Game.cs", "protected virtual void spreadReligion("),
            "connection": cite("Game.cs", "RELIGION_SPREAD_CONNECTION_DISTANCE_MODIFIER"),
            "roll": cite("Game.cs", "iDistance *= randomNext(iDistance) + 1;"),
            "eligible": cite("City.cs", "public virtual bool isReligionSpreadEligible("),
            "citySpread": cite("City.cs", "public virtual void spreadReligion("),
            "noSpreadUnlock": cite("City.cs", "if (infos().effectCity(eIndex).mbNoReligionSpread)"),
            "disciple": cite("Unit.cs", "public virtual bool canSpreadReligion("),
            "purge": cite("Unit.cs", "public virtual void purgeReligion("),
            "tribeCost": cite("Unit.cs", "public virtual int getSpreadReligionTribeCost("),
            "tribeSpread": cite("Unit.cs", "public virtual void spreadReligionTribe("),
            "tribeDiplomacy": cite("Player.cs", "public virtual bool canSpreadReligionTribe("),
            "improvementSpread": cite("Tile.cs", "pCityTerritory.spreadReligion(eReligionSpread, pSpreadPlayer: owner());"),
            "tileCarry": cite("Tile.cs", "cityTerritory().spreadReligion(eLoopReligion);"),
            "found": cite("Game.cs", "public virtual ReligionType doReligionFound("),
            "foundValue": cite("Game.cs", "protected virtual int getReligionCityFoundValue("),
            "canFoundGame": cite("Game.cs", "public virtual bool canFoundReligion("),
            "canFoundCity": cite("City.cs", "public virtual bool canFoundReligion("),
            "distance": cite("Utils.cs", "public virtual int distance(int iX1"),
            "modify": cite("Utils.cs", "public virtual int modify(int iValue"),
        },
    }
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ religious_spread.json — {len(rolling)} rolling religions, {len(player_effects)} player effects, "
          f"{len(blockers) + len(dissent)} blockers, {sum(r['count'] for r in spread_imps_list)} spreading improvements, "
          f"{len(tribes)} tribes")


if __name__ == "__main__":
    main()
