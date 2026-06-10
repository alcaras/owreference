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

    OUT.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} (globals from globalsInt.xml)")
    for d in drift:
        print(f"⚠ drift vs yaml — {d} — update conversion.yaml comment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
