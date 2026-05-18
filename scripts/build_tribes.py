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

# The 7 tribes that field a full combat roster (each has units flagged in
# unit.xml's azBarbarianPortraitName). Anarchy/Barbarians/Raiders/Rebels
# are generic enemy states with no roster.
COMBAT_TRIBES = {
    "TRIBE_DANES", "TRIBE_GAULS", "TRIBE_HUNS", "TRIBE_NUMIDIANS",
    "TRIBE_SCYTHIANS", "TRIBE_THRACIANS", "TRIBE_VANDALS",
}

# UnitCycle → branch label for the matrix sections.
BRANCH_BY_CYCLE = {
    "UNITCYCLE_MILITARY_INFANTRY": "Melee",
    "UNITCYCLE_MILITARY_RANGED": "Ranged",
    "UNITCYCLE_MILITARY_MOUNTED": "Mounted",
}
BRANCH_ORDER = {"Melee": 0, "Ranged": 1, "Mounted": 2}


def _icon_from(zicon: str | None, unit_id: str) -> str:
    """Icon filename (no ext). Art is extracted by zIconName with the
    leading UNIT_/unit_ prefix stripped, lowercased — e.g.
    UNIT_ELITE_HUSCARL → 'elite_huscarl'. Fall back to the unit id with
    its tier suffix collapsed if zIconName is missing."""
    base = (zicon or unit_id).lower()
    base = re.sub(r"^unit_", "", base)
    if not zicon:
        base = re.sub(r"_\d+$", "", base)
    return base


def build_rosters(text_unit: dict, text_effect: dict) -> dict[str, list[dict]]:
    """{ TRIBE_X: [ {id,name,icon,strength,branch,special,promoId,promoName}, ... ] }.

    A unit belongs to tribe X iff unit.xml lists X under
    azBarbarianPortraitName/Pair/zIndex. Game-data quirk: the Hunnic
    Cavalry pair (and its art) is tagged TRIBE_SCYTHIANS even though the
    unit is the Huns' signature line — re-home it to TRIBE_HUNS (mirrors
    the YEUZHI-typo class of upstream quirks; we paper over, never fix
    the user's Steam install)."""
    unit_root = ET.parse(XML_DIR / "unit.xml").getroot()

    # Pass 1: collect every tribe-tagged unit with its raw attrs.
    raw: list[dict] = []
    for entry in unit_root.findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt:
            continue
        tribes = {
            p.findtext("zIndex")
            for p in entry.findall("azBarbarianPortraitName/Pair")
            if (p.findtext("zIndex") or "").startswith("TRIBE_")
        }
        if not tribes:
            continue
        if "HUNNIC_CAVALRY" in zt:
            tribes = {"TRIBE_HUNS"}
        strength = int(entry.findtext("iStrength") or "0") // 10
        cycle = entry.findtext("UnitCycle") or ""
        branch = BRANCH_BY_CYCLE.get(cycle, "Melee")
        effs = [v.text for v in entry.findall("aeEffectUnit/zValue") if v.text]
        zicon = entry.findtext("zIconName")
        raw.append({
            "id": zt,
            "tribes": tribes & COMBAT_TRIBES,
            "strength": strength,
            "branch": branch,
            "icon": _icon_from(zicon, zt),
            "effs": effs,
        })

    # Pass 2: special vs generic. Strip the trailing _<tier> to get a
    # base name; a base name fielded by more than one tribe is a shared
    # generic unit, otherwise it's that tribe's unique upgrade.
    base_tribes: dict[str, set[str]] = {}
    for u in raw:
        base = re.sub(r"_\d+$", "", u["id"])
        base_tribes.setdefault(base, set()).update(u["tribes"])

    def effect_name(e: str | None) -> str | None:
        if not e:
            return None
        return text_effect.get(f"TEXT_{e}", e.replace("EFFECTUNIT_", "").title())

    rosters: dict[str, list[dict]] = {}
    for u in raw:
        base = re.sub(r"_\d+$", "", u["id"])
        special = len(base_tribes.get(base, set())) <= 1
        # Display name resolves via the _1-collapsed text key
        # (TEXT_UNIT_HUSCARL is empty; TEXT_UNIT_HUSCARL_1 = "Huscarl").
        name = (
            text_unit.get(f"TEXT_{u['id']}")
            or text_unit.get(f"TEXT_{base}_1")
            or text_unit.get(f"TEXT_{base}")
            or base.replace("UNIT_", "").replace("_", " ").title()
        )
        unique = [e for e in u["effs"] if e not in GENERIC_EFFECTS]
        promo = unique[0] if unique else None
        for tribe in u["tribes"]:
            rosters.setdefault(tribe, []).append({
                "id": u["id"],
                "name": name,
                "icon": u["icon"],
                "strength": u["strength"],
                "branch": u["branch"],
                "special": special,
                "promoId": promo if special else None,
                "promoName": effect_name(promo) if special else None,
            })

    for tribe, units in rosters.items():
        units.sort(key=lambda x: (
            BRANCH_ORDER.get(x["branch"], 9),
            x["strength"],
            0 if x["special"] else 1,
            x["id"],
        ))
    return rosters


def resolve_tribe_colors() -> dict[str, str]:
    """{ TRIBE_X: '#rrggbb' }, fully XML-derived.

    color.xml has no TEAMCOLOR_TRIBE_* entries. The mapping is a 3-hop
    chain through the game's own files (per the source-of-truth rule —
    prefer XML over a hand-assigned fallback):
      tribe.xml  <TeamColor>TEAMCOLOR_TRIBE_X
      teamColor.xml  TEAMCOLOR_TRIBE_X → aePlayerColors[0] (PLAYERCOLOR_*)
      playerColor.xml  PLAYERCOLOR_* → <AssetColor> COLOR_BARBARIAN_TRIBE_0N
      color.xml  COLOR_BARBARIAN_TRIBE_0N → <zHexValue>
    """
    # teamColor.xml: TEAMCOLOR_TRIBE_X → first aePlayerColors zValue
    tc_to_pc: dict[str, str] = {}
    for e in ET.parse(XML_DIR / "teamColor.xml").getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt.startswith("TEAMCOLOR_TRIBE_"):
            continue
        pc = e.findtext("aePlayerColors/zValue")
        if pc:
            tc_to_pc[zt] = pc

    # playerColor.xml: PLAYERCOLOR_* → AssetColor
    pc_to_color: dict[str, str] = {}
    for e in ET.parse(XML_DIR / "playerColor.xml").getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        ac = e.findtext("AssetColor")
        if zt and ac:
            pc_to_color[zt] = ac

    # color.xml: COLOR_* → hex
    color_hex: dict[str, str] = {}
    for e in ET.parse(XML_DIR / "color.xml").getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        hx = e.findtext("zHexValue")
        if zt and hx:
            color_hex[zt] = hx.strip()

    out: dict[str, str] = {}
    for e in ET.parse(XML_DIR / "tribe.xml").getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        team = e.findtext("TeamColor") or ""
        if not zt.startswith("TRIBE_") or not team:
            continue
        pc = tc_to_pc.get(team)
        col = pc_to_color.get(pc) if pc else None
        hx = color_hex.get(col) if col else None
        if hx:
            out[zt] = hx
    return out


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
    rosters = build_rosters(text_unit, text_effect)
    tribe_colors = resolve_tribe_colors()
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
            "combat": zt in COMBAT_TRIBES,
            "color": tribe_colors.get(zt),
            "roster": rosters.get(zt, []),
        })

    tribes.sort(key=lambda t: t["slug"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(tribes, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(tribes)} tribes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
