#!/usr/bin/env python3
"""Build src/data/conversion.json from src/data/annotations/conversion.yaml.

The yaml documents religion-conversion logic that lives in compiled game
code. The four named constants it cites, however, ARE in globalsInt.xml —
so per the source-of-truth rules those are read from XML here (XML wins),
and the yaml values are only a fallback that triggers a drift warning.
Code-derived constants (scoring points, thresholds) stay yaml-maintained;
scripts/verify_source_constants.py tripwires those against game source.
"""
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET
import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "data" / "annotations" / "conversion.yaml"
GLOBALS_XML = ROOT / "reference" / "XML" / "Infos" / "globalsInt.xml"
OUT = ROOT / "src" / "data" / "conversion.json"

# conversion.json globals key → globalsInt.xml zType
XML_GLOBALS = {
    "characterReligionProb": "CHARACTER_RELIGION_PROB",
    "characterReligionDelayTurns": "CHARACTER_RELIGION_DELAY_TURNS",
    "adultAge": "ADULT_AGE",
    "tutorsAge": "TUTORS_AGE",
}


def load_globals_int() -> dict[str, int]:
    out: dict[str, int] = {}
    if not GLOBALS_XML.exists():
        return out
    for e in ET.parse(GLOBALS_XML).getroot().findall("Entry"):
        z = e.findtext("zType")
        v = e.findtext("iValue")
        if z and v is not None:
            try:
                out[z] = int(v)
            except ValueError:
                pass
    return out


def state_religion(gi: dict[str, int]) -> dict:
    """What adopting a State Religion costs and gives, from religion.xml.

    Cost: InfoHelpers.getAdoptReligionCost = iCostBase + iCostPerCity × cities
    + iCostPerChange × Player.getStateReligionChangeCount() (ONE counter per
    player, every adoption counts), rounded down to 10, capped at MAX_CIVICS.
    City effect: EffectPlayerState → StateReligionEffectCity, applied to each of
    the player's cities that follows the religion (City.cs). Opinion:
    PlayerOpinion.calculateCharacterOpinionStateReligion, ±STATE_RELIGION_OPINION_CHARACTER,
    halved against pagan followers, doubled for a religion head.
    """
    xml = ROOT / "reference" / "XML" / "Infos"
    ep = {e.findtext("zType"): e for e in ET.parse(xml / "effectPlayer.xml").getroot().findall("Entry")}
    ec = {e.findtext("zType"): e for e in ET.parse(xml / "effectCity.xml").getroot().findall("Entry")}
    costs, per_city, city_yields, upkeep = set(), set(), set(), {}
    for r in ET.parse(xml / "religion.xml").getroot().findall("Entry"):
        rid = r.findtext("zType")
        if not rid:
            continue
        costs.add((int(r.findtext("iCostBase") or 0), int(r.findtext("iCostPerChange") or 0)))
        per_city.add(int(r.findtext("iCostPerCity") or 0))
        state = ep.get(r.findtext("EffectPlayerState") or "")
        city = ec.get(state.findtext("StateReligionEffectCity") or "") if state is not None else None
        if city is not None:
            city_yields.add(tuple((p.findtext("zIndex"), int(p.findtext("iValue") or 0))
                                  for p in city.findall("aiYieldRate/Pair")))
        upkeep[rid] = r.findtext("EffectPlayerUpkeep") or ""
    assert len(costs) == 1 and per_city == {0}, f"state religion costs now differ by religion: {costs} {per_city}"
    assert len(city_yields) == 1, f"state religion city yields now differ by religion: {city_yields}"
    base, per_change = costs.pop()
    return {
        "costBase": base,
        "costPerChange": per_change,
        "maxCivics": gi.get("MAX_CIVICS", 0),
        "opinion": gi.get("STATE_RELIGION_OPINION_CHARACTER", 0),
        "cityYields": [{"yield": y, "value": v / 10} for y, v in city_yields.pop()],
        "upkeepReligions": sorted(k for k, v in upkeep.items() if v),
    }


def main() -> int:
    data = yaml.safe_load(SRC.read_text())
    gi = load_globals_int()
    drift = []
    for key, ztype in XML_GLOBALS.items():
        if ztype not in gi:
            print(f"⚠ {ztype} not found in globalsInt.xml — keeping yaml value")
            continue
        yaml_val = data.get("globals", {}).get(key)
        xml_val = gi[ztype]
        if yaml_val is not None and yaml_val != xml_val:
            drift.append(f"{key}: yaml={yaml_val} xml={xml_val} (using xml)")
        data.setdefault("globals", {})[key] = xml_val

    data["stateReligion"] = state_religion(gi)
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} (globals from globalsInt.xml)")
    for d in drift:
        print(f"⚠ drift vs yaml — {d} — update conversion.yaml comment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
