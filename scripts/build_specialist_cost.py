#!/usr/bin/env python3
"""
Build src/data/specialist_cost.json — why a specialist costs more than the
base price printed on /rural-specialists and /urban-specialists.

The ramp is one global and one per-city counter:

    civics = max(1, (base * (100 + PRODUCED*n + cityModifier)) / 100)   [int math]

      base         specialist.xml iCivics + improvement.xml iSpecialistCost
                   (no improvement sets the latter in the current patch)
      PRODUCED     globalsInt.xml SPECIALIST_COST_PRODUCED_MODIFIER (5)
      n            City.getSpecialistProducedCount() — per CITY, never per player
      cityModifier effectCity iSpecialistRuralTrainTimeModifier or
                   iSpecialistUrbanTrainTimeModifier, by the specialist class's
                   bUrban flag

  Player.getSpecialistBuildCost (Player.cs:17828) does the multiply through
  Utils.modify (Utils.cs:58), which is integer truncation, and clamps to 1.

The separate yield cost (Food only — aiYieldCost names no other yield) is NOT
part of the ramp: it
runs through City.getSpecialistCostModifier + getSpecialistUrbanCostModifier
in Player.getSpecialistYieldCost (Player.cs:17802). Both sets of modifiers are
emitted here, tagged by which cost they move, because "specialist cost" in
conversation means both. The Citizen an urban specialist takes is neither: it is
a flat 1, charged only when Tile.isSpecialistCostCitizen (no specialist on the
tile to upgrade), outside getSpecialistYieldCost, so no modifier scales it.

Costs are RAW integers, like the rest of the specialist data — no /10
(same note as build_specialists.py).
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import load_xml_indexes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "specialist_cost.json"

# effectCity field → (which cost it moves, which specialists it applies to).
# The two "TrainTime" fields are named for time but land on the Civics build
# cost, in the same multiply as the produced-count ramp.
MODIFIER_FIELDS = {
    "iSpecialistRuralTrainTimeModifier": ("civics", "rural"),
    "iSpecialistUrbanTrainTimeModifier": ("civics", "urban"),
    "iSpecialistCostModifier": ("yield", "all"),
    "iSpecialistUrbanCostModifier": ("yield", "urban"),
}

# What an effectCity hangs off, by the file that references it. Effects reach a
# city through chains (law → EffectPlayer → EffectCity; difficulty preset →
# Advantage → EffectPlayer → EffectCity), so the walk below treats these files
# as pass-through links and keeps going until it reaches something a player
# recognises. File suffixes (-event-wog, -sap, …) are stripped first, so a DLC
# copy of a file lands on the same label.
PASSTHROUGH = {"effectCity.xml", "effectPlayer.xml", "advantage.xml"}
# advantage.xml is both: the advantage level is worth naming, and the difficulty
# preset that sets it is one hop further out.
ALSO_CARRIER = {"advantage.xml"}

# Only references that ATTACH an effect are followed. A token sitting in a
# Pair's zIndex is a *condition* ("if the city already has this effect"), which
# is how the Aksum Stele mentions the Landowners effect without carrying it.
def attaches(tag: str) -> bool:
    return tag.endswith(("EffectCity", "EffectPlayer")) or tag in ("Advantage", "zValue")

CARRIER_KINDS = {
    "familyClass.xml": "Family class",
    "law.xml": "Law",
    "trait.xml": "Trait",
    "project.xml": "Project",
    "improvement.xml": "Improvement",
    "difficultyMode.xml": "Difficulty preset",
    "difficulty.xml": "Prosperity level",
    "religion.xml": "Religion",
    "theology.xml": "Theology",
    "tech.xml": "Technology",
    "specialist.xml": "Specialist",
    "bonus.xml": "Event reward",
    "eventStory.xml": "Event",
    "advantage.xml": "Advantage level",
}

# The referencing tag says WHEN the effect applies. Blank means "while the
# carrier is active", which needs no qualifier.
TAG_NOTES = {
    "GovernorEffectCity": "in cities they govern",
    "NoGovernorEffectCity": "in cities with no governor",
    "LeaderEffectPlayer": "while they are the leader",
    "CouncilEffectPlayer": "while they hold the seat",
    "Advantage": "sets the advantage level",
}

# Hand-verified from reference/Source: every writer of
# City.miSpecialistProducedCount, and the specialist-placing paths that are
# NOT writers. Swept with grep over the whole Source tree — the free-specialist
# paths are the whole reason this page exists. verify_source_constants.py
# watches getSpecialistBuildCost so a patch that reshuffles this trips.
COUNTS = [
    {
        "what": "A specialist the city finishes from its build queue",
        "where": "City.finishBuild → incrementSpecialistProducedCount (City.cs:8528)",
    },
    {
        "what": "Each tier upgrade, so Apprentice, Master and Elder are three counts",
        "where": "an upgrade is another SPECIALIST_BUILD on the tile (Tile.getNextSpecialist, Tile.cs:7053)",
    },
    {
        "what": "Specialists the advanced-start setup drops into a new city",
        "where": "City.develop (City.cs:7829), run from Player advanced start (Player.cs:16318)",
    },
    {
        "what": "Specialists a city already holds when the game begins",
        "where": "Player.start seeds each city's count to its specialist count (Player.cs:15923)",
    },
]

IGNORES = [
    {
        "what": "A specialist granted by an event or any other bonus",
        "where": "bonus SetSpecialist (PlayerBonus.cs:8579) and AddSpecialistClasses "
                 "(PlayerBonus.cs:7267) place one with no increment",
    },
    {
        "what": "Wonder free specialists, such as the Jerwan Aqueduct on adjacent Farms",
        "where": "improvement AdjacentImprovementSpecialists → Tile.changeImprovementFreeSpecialists "
                 "(Tile.cs:6637 and Tile.cs:7785), a free-specialist count on the tile rather than a build",
    },
    {
        "what": "A specialist kept when a Worker upgrades the improvement under it",
        "where": "Unit.cs:12059 sets the new improvement's specialist directly",
    },
    {
        "what": "Removing a specialist, losing the tile, razing, or losing the city to a rival",
        "where": "nothing decreases the counter: the only writers are the two increments above, "
                 "Player.start and save loading",
    },
    {
        "what": "Specialists trained in your other cities",
        "where": "the counter lives on City, not Player (City.cs:181)",
    },
]


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text: dict[str, str] = indexes["__text__"]  # type: ignore[assignment]

    # GENDERED_TEXT_* → the masculine TEXT key (traits name themselves that way).
    gendered: dict[str, str] = {}
    for path in sorted(XML_DIR.glob("genderedText*.xml")):
        for e in ET.parse(path).getroot().findall("Entry"):
            zt = e.findtext("zType") or ""
            for pair in e.findall("Texts/Pair"):
                if (pair.findtext("zIndex") or "") == "GRAMMATICAL_GENDER_MASCULINE":
                    gendered.setdefault(zt, (pair.findtext("zValue") or "").strip())

    def name_of(entry: ET.Element, strip: str = "") -> str:
        zt = entry.findtext("zType") or ""
        for field in ("Name", "GenderedName"):
            key = entry.findtext(field) or ""
            key = gendered.get(key, key)
            if key and text.get(key):
                return text[key]
        stem = strip or (zt.split("_")[0] + "_")
        return zt.replace(stem, "").replace("_", " ").title()

    # ── the global ────────────────────────────────────────────────────────
    per_produced = 0
    for e in parse("globalsInt.xml").findall("Entry"):
        if (e.findtext("zType") or "") == "SPECIALIST_COST_PRODUCED_MODIFIER":
            per_produced = int(e.findtext("iValue") or "0")
    if per_produced == 0:
        print("✗ SPECIALIST_COST_PRODUCED_MODIFIER missing from globalsInt.xml")
        return 1

    # ── specialist classes: urban or rural ────────────────────────────────
    urban_class = {
        (e.findtext("zType") or ""): (e.findtext("bUrban") or "0") == "1"
        for e in parse("specialistClass.xml").findall("Entry")
        if e.findtext("zType")
    }

    # ── specialists: base Civics, Food, tier depth ────────────────────────
    spec_entries = [e for e in parse("specialist.xml").findall("Entry") if e.findtext("zType")]
    prereq = {
        (e.findtext("zType") or ""): (e.findtext("SpecialistPrereq") or "")
        for e in spec_entries
    }

    def tier_of(zt: str) -> int:
        """1 for a standalone/first-tier specialist, +1 per prereq step."""
        depth, cur = 1, zt
        while prereq.get(cur):
            cur = prereq[cur]
            depth += 1
        return depth

    specialists: list[dict] = []
    for e in spec_entries:
        zt = e.findtext("zType") or ""
        cls = e.findtext("Class") or ""
        food = 0
        for pair in e.findall("aiYieldCost/Pair"):
            if (pair.findtext("zIndex") or "") == "YIELD_FOOD":
                food = int(pair.findtext("iValue") or "0")
        specialists.append({
            "id": zt,
            "slug": zt.replace("SPECIALIST_", "").lower(),
            "name": name_of(e, "SPECIALIST_"),
            "classId": cls,
            "urban": bool(urban_class.get(cls, False)),
            "tier": tier_of(zt),
            "civics": int(e.findtext("iCivics") or "0"),
            "food": food,
        })

    # An improvement can add to the base Civics price (nothing does today —
    # emitted so the page can say so, and so a patch that starts using it
    # shows up in the changelog).
    imp_extra = [
        {"id": e.findtext("zType"), "name": name_of(e, "IMPROVEMENT_"),
         "civics": int(e.findtext("iSpecialistCost") or "0")}
        for e in parse("improvement.xml").findall("Entry")
        if (e.findtext("iSpecialistCost") or "0") not in ("0", "")
    ]

    # ── base-price groups, for the ramp table ─────────────────────────────
    # Rural specialists and every Apprentice share one base price; Master and
    # Elder sit above. Group by (price, tier-ish role) rather than hardcoding.
    groups: dict[int, dict] = {}
    for s in specialists:
        if s["civics"] == 0:
            continue
        g = groups.setdefault(s["civics"], {"civics": s["civics"], "rural": [], "urban": []})
        g["urban" if s["urban"] else "rural"].append(s["name"])
    bases = []
    for civics in sorted(groups):
        g = groups[civics]
        bases.append({
            "civics": civics,
            "ruralCount": len(g["rural"]),
            "urbanCount": len(g["urban"]),
            "examples": sorted(g["rural"])[:3] + sorted(g["urban"])[:3],
        })

    # ── city modifiers, with their carriers ───────────────────────────────
    effect_hits: dict[str, list[tuple[str, str, int]]] = {}
    for e in parse("effectCity.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        for field, (target, scope) in MODIFIER_FIELDS.items():
            raw = e.findtext(field) or "0"
            if raw not in ("0", ""):
                effect_hits.setdefault(zt, []).append((target, scope, int(raw)))

    # Who attaches each of those effects. Walk references outward, stepping
    # through the pass-through files (effectPlayer, advantage) until the trail
    # reaches a law, family class, trait, project or difficulty preset. Each hop
    # keeps the referencing tag, which is what says WHEN the effect applies
    # (GovernorEffectCity is only the cities that character governs).
    def norm_file(name: str) -> str:
        """improvement-event-sap.xml → improvement.xml (DLC copies of a file)."""
        stem = name[:-len(".xml")]
        for sep in ("-event-", "-event", "-"):
            if sep in stem:
                stem = stem.split(sep)[0]
                break
        return f"{stem}.xml"

    # token → [(file, entry, tag)] for every reference in the Infos tree
    refs: dict[str, list[tuple[str, ET.Element, str]]] = {}
    for path in sorted(XML_DIR.glob("*.xml")):
        if path.name.startswith(("text-", "genderedText")):
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for entry in root.findall("Entry"):
            if not (entry.findtext("zType") or ""):
                continue
            for node in entry.iter():
                token = (node.text or "").strip()
                if token.startswith(("EFFECTCITY_", "EFFECTPLAYER_", "ADVANTAGE_")) and attaches(node.tag):
                    refs.setdefault(token, []).append((path.name, entry, node.tag))

    def carriers_of(effect_id: str) -> list[dict]:
        out: list[dict] = []
        seen_tokens = {effect_id}
        # (token, tag that led here) — the tag of the LAST hop is the telling one
        frontier = [(effect_id, "")]
        for _ in range(4):
            nxt: list[tuple[str, str]] = []
            for token, _prev_tag in frontier:
                for fname, entry, tag in refs.get(token, []):
                    zt = entry.findtext("zType") or ""
                    if zt == token:
                        continue                      # the entry defining it
                    norm = norm_file(fname)
                    if norm in PASSTHROUGH:
                        if zt not in seen_tokens:
                            seen_tokens.add(zt)
                            nxt.append((zt, tag))
                        if norm not in ALSO_CARRIER:
                            continue
                    row = {
                        "kind": CARRIER_KINDS.get(norm, norm),
                        "id": zt,
                        "name": name_of(entry),
                        "note": TAG_NOTES.get(tag, ""),
                    }
                    if row not in out:
                        out.append(row)
            if not nxt:
                break
            frontier = nxt
        out.sort(key=lambda r: (r["kind"], r["name"]))
        return out

    effects_idx = {
        (e.findtext("zType") or ""): e
        for e in parse("effectCity.xml").findall("Entry") if e.findtext("zType")
    }
    modifiers: list[dict] = []
    for eid, hits in effect_hits.items():
        entry = effects_idx[eid]
        for target, scope, value in hits:
            modifiers.append({
                "id": eid,
                "name": name_of(entry, "EFFECTCITY_"),
                "target": target,          # civics = in the ramp multiply; yield = Food cost
                "scope": scope,            # rural / urban / all
                "value": value,
                "carriers": carriers_of(eid),
            })
    modifiers.sort(key=lambda m: (m["target"] != "civics", m["value"], m["name"]))

    data = {
        "global": {"token": "SPECIALIST_COST_PRODUCED_MODIFIER", "perProduced": per_produced},
        "bases": bases,
        "specialists": specialists,
        "improvementExtra": imp_extra,
        "modifiers": modifiers,
        "code": {
            "formula": "civics = max(1, base * (100 + perProduced*n + cityModifier) / 100), integer truncation",
            "buildCost": "Player.getSpecialistBuildCost (Player.cs:17828)",
            "yieldCost": "Player.getSpecialistYieldCost (Player.cs:17802)",
            "modify": "Utils.modify (Utils.cs:58) — truncating integer multiply",
            "counter": "City.getSpecialistProducedCount (City.cs:3079)",
            "counts": COUNTS,
            "ignores": IGNORES,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — +{per_produced}%/specialist, "
          f"{len(bases)} base prices, {len(modifiers)} city modifiers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
