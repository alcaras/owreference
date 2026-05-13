#!/usr/bin/env python3
"""Build src/data/tribes.json from reference/XML/Infos/tribe.xml.

For each diplomatic tribe (Gauls, Huns, Danes, Numidians, Scythians,
Thracians, Vandals) we surface:
  - canonical attrs (name, nickname, DLC, organized/mercenary flags,
    default diplomacy, sample names)
  - the tribe's signature unit (looked up via BONUS_TRIBAL_FINDING_RELIGION_
    *_DEFENSE in bonus-event.xml) and the unique 'free promotion' that
    unit ships with (its aeEffectUnit signature effect — Ranger, Cold,
    Nomad, etc — excluding generic Pierce/Cleave tiers)."""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "tribes.json"


def first_form(s: str | None) -> str:
    return (s or "").split("~")[0].strip()


def load_text(*filenames: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = first_form(e.findtext("en-US"))
            if k and en:
                out[k] = en
    return out


def fmt_dlc(tag: str) -> str:
    return tag.replace("_", " ").title() if tag else ""


# Generic XP-tier promos that aren't unique to any tribe — these show up
# on multiple units (siege/cleave/pierce ladders) and shouldn't be billed
# as the tribe's "unique" promo.
GENERIC_EFFECTS = {
    "EFFECTUNIT_PIERCE1", "EFFECTUNIT_PIERCE2", "EFFECTUNIT_PIERCE3",
    "EFFECTUNIT_CLEAVE1", "EFFECTUNIT_CLEAVE2", "EFFECTUNIT_CLEAVE3",
    "EFFECTUNIT_CRUSH1", "EFFECTUNIT_CRUSH2", "EFFECTUNIT_CRUSH3",
    "EFFECTUNIT_RANGE1", "EFFECTUNIT_RANGE2",
}


def load_tribe_units(text_unit: dict, text_effect: dict) -> dict[str, dict]:
    """Returns { TRIBE_X: {unit_id, unit_name, unit_icon_name, promo_id, promo_name, extra_promos:[{id,name}]} }."""
    out: dict[str, dict] = {}

    # Step 1: parse bonus-event.xml for tribal-defense unit grants
    tribe_unit: dict[str, str] = {}  # TRIBE_X → UNIT_Y_1
    be_root = ET.parse(XML_DIR / "bonus-event.xml").getroot()
    for entry in be_root.findall("Entry"):
        zt = entry.findtext("zType") or ""
        m = re.match(r"BONUS_TRIBAL_FINDING_RELIGION_(\w+?)_DEFENSE$", zt)
        if not m:
            continue
        tribe_key = f"TRIBE_{m.group(1)}"
        units = entry.findall("aiUnits/Pair/zIndex")
        if units and units[0].text:
            tribe_unit[tribe_key] = units[0].text

    # Hunnic Cavalry isn't granted via the defense bonus pattern (Huns are
    # an EOTI-DLC tribe). Hard-wire it from the unit naming convention.
    if "TRIBE_HUNS" not in tribe_unit:
        tribe_unit["TRIBE_HUNS"] = "UNIT_HUNNIC_CAVALRY_1"

    # Step 2: for each unit, parse its aeEffectUnit list
    unit_root = ET.parse(XML_DIR / "unit.xml").getroot()
    unit_effects: dict[str, list[str]] = {}
    unit_icon: dict[str, str] = {}
    for entry in unit_root.findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt:
            continue
        effs = [v.text for v in entry.findall("aeEffectUnit/zValue") if v.text]
        if effs:
            unit_effects[zt] = effs
        ic = entry.findtext("zIconName")
        if ic:
            unit_icon[zt] = ic

    for tribe_key, unit_id in tribe_unit.items():
        effs = unit_effects.get(unit_id, [])
        unique = [e for e in effs if e not in GENERIC_EFFECTS]
        extra = [e for e in effs if e in GENERIC_EFFECTS]
        primary = unique[0] if unique else (effs[0] if effs else None)

        # Lookup unit display name
        unit_text_key = f"TEXT_{unit_id}".replace("_1", "")  # collapse Gaesata_1 → Gaesata
        # Try forms with and without _1 suffix
        unit_name = (
            text_unit.get(f"TEXT_{unit_id}")
            or text_unit.get(unit_text_key)
            or unit_id.replace("UNIT_", "").replace("_", " ").title()
        )

        # Lookup promo display name
        def effect_name(e: str | None) -> str | None:
            if not e:
                return None
            return text_effect.get(f"TEXT_{e}", e.replace("EFFECTUNIT_", "").title())

        out[tribe_key] = {
            "unitId": unit_id,
            "unitName": unit_name,
            "unitIcon": (unit_icon.get(unit_id) or unit_id.replace("_1", "")).lower(),
            "promoId": primary,
            "promoName": effect_name(primary),
            "extraPromos": [{"id": e, "name": effect_name(e)} for e in extra],
        }

    return out


def main() -> int:
    text_tribe = load_text("text-tribe.xml")
    text_infos = load_text("text-infos.xml")
    # Pull unit text from base + DLC text files (Hunnic Cavalry lives in text-eoti.xml)
    text_unit = load_text(
        "text-unit.xml", "text-eoti.xml", "text-btt.xml", "text-wd.xml",
        "text-wog.xml", "text-sap.xml",
    )
    text_effect = load_text("text-effectUnit.xml")
    tribe_units = load_tribe_units(text_unit, text_effect)
    text_name = {}
    for p in XML_DIR.glob("text-name*.xml"):
        try:
            for e in ET.parse(p).getroot().findall("Entry"):
                k = e.findtext("zType") or ""
                en = first_form(e.findtext("en-US"))
                if k and en and "_HISTORICAL" not in k:
                    text_name.setdefault(k, en)
        except ET.ParseError:
            pass

    tribes: list[dict] = []
    root = ET.parse(XML_DIR / "tribe.xml").getroot()

    for entry in root.findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("TRIBE_"):
            continue

        slug = zt.replace("TRIBE_", "").lower()

        # Display name — TEXT_TRIBE_GAULS first form is e.g. "Gauls"
        name_key = f"TEXT_{zt}"
        display_name = text_tribe.get(name_key, slug.title())

        nickname_key = entry.findtext("GenderedNickname") or ""
        nickname_text_key = nickname_key.replace("GENDERED_", "")
        nickname = text_tribe.get(nickname_text_key, "")

        # Pull a small sample of first names (4 each)
        def names(field: str) -> list[str]:
            out = []
            for nm in entry.findall(f"{field}/zValue"):
                key = nm.text or ""
                if not key:
                    continue
                resolved = text_name.get(f"TEXT_{key}", key.replace("NAME_", "").title())
                out.append(resolved)
            return out

        names_m = names("aeFirstNamesMale")
        names_f = names("aeFirstNamesFemale")

        tribes.append({
            "id": zt,
            "slug": slug,
            "name": display_name,
            "nickname": nickname,
            "gameContent": fmt_dlc(entry.findtext("GameContentRequired") or ""),
            "organized": entry.findtext("bOrganized") == "1",
            "mercenary": entry.findtext("bMercenary") == "1",
            "diplomacy": entry.findtext("bDiplomacy") == "1",
            "defaultDiplomacy": (entry.findtext("Diplomacy") or "").replace("DIPLOMACY_", "").title(),
            "iPillagePriority": int(entry.findtext("iPillagePriority") or "0"),
            "iCityAttackPriority": int(entry.findtext("iCityAttackPriority") or "0"),
            "firstNamesMale": names_m,
            "firstNamesFemale": names_f,
            "namesMaleCount": len(names_m),
            "namesFemaleCount": len(names_f),
            "unit": tribe_units.get(zt),
        })

    tribes.sort(key=lambda t: t["slug"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(tribes, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(tribes)} tribes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
