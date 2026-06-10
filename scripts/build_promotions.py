#!/usr/bin/env python3
"""
Build src/data/promotions.json from promotion.xml + effectUnit.xml.

Each promotion entry: id, slug, name, tier (derived from EffectUnit iClassNum
or the trailing digit on the id), prereq promotion id (via EffectUnitPrereq),
effects (humanized stat/trait modifiers), and the unit traits it's valid on.

We render promotion effects directly from EffectUnit since promotions are a
thin wrapper. The humanizer doesn't have a "full effect-unit" renderer yet —
this script does it inline for the fields promotions actually use:
strength/attack/defense modifiers, anti-trait modifiers, attack-value bonuses,
healing, terrain/vegetation/height bonuses, fatigue limits.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import effects  # noqa: E402
from humanize import (  # noqa: E402
    load_xml_indexes, fmt_decimal,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "promotions.json"


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def trait_label(t: str) -> str:
    return t.replace("UNITTRAIT_", "").title()


def terrain_label(t: str) -> str:
    return t.replace("TERRAIN_", "").title()


def vegetation_label(t: str) -> str:
    return t.replace("VEGETATION_", "").title()


def height_label(t: str) -> str:
    return t.replace("HEIGHT_", "").title()


def attack_label(t: str) -> str:
    return t.replace("ATTACK_", "").title()


def render_promotion_effect(e: ET.Element) -> list[str]:
    """Render the EffectUnit fields most relevant to promotions."""
    out: list[str] = []

    for tag, label in [
        ("iStrengthModifier", "Strength"),
        ("iAttackModifier",   "Attack"),
        ("iDefenseModifier",  "Defense"),
        ("iMoraleModifier",   "Morale"),
        ("iCityStrengthModifier", "City Strength"),
        ("iCityDefenseModifier",  "City Defense"),
    ]:
        v = e.findtext(tag)
        if v and v != "0":
            out.append(f"{fmt_decimal(int(v))}% {label}")

    # Trait-targeted strength bonuses (e.g., +50% vs Melee)
    for pair in e.findall("aiUnitTraitModifier/Pair"):
        t = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% vs {trait_label(t)}")

    for pair in e.findall("aiUnitTraitModifierAttack/Pair"):
        t = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% Attack vs {trait_label(t)}")

    for pair in e.findall("aiUnitTraitModifierDefense/Pair"):
        t = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% Defense vs {trait_label(t)}")

    for pair in e.findall("aiUnitTraitModifierMelee/Pair"):
        t = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% Melee vs {trait_label(t)}")

    # Attack pattern bonuses (Pierce/Cleave/Splash/Circle)
    for pair in e.findall("aiAttackValue/Pair"):
        a = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)} {attack_label(a)}")

    for pair in e.findall("aiAttackPercent/Pair"):
        a = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% {attack_label(a)} Damage")

    # Terrain / vegetation / height combat bonuses
    for pair in e.findall("aiTerrainFromModifier/Pair"):
        t = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% on {terrain_label(t)}")

    for pair in e.findall("aiVegetationFromModifier/Pair"):
        t = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% in {vegetation_label(t)}")

    for pair in e.findall("aiHeightFromModifier/Pair"):
        t = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{fmt_decimal(v)}% on {height_label(t)}")

    # Healing
    heal_extra = e.findtext("iHealExtra")
    if heal_extra and heal_extra != "0":
        out.append(f"{fmt_decimal(int(heal_extra))} Healing")
    if (e.findtext("iHealAlways") or "0") == "1":
        out.append("Heals every turn")

    # Movement / sight
    for tag, label in [
        ("iMovement", "Movement"),
        ("iVision",   "Sight"),
        ("iRangeMin", "Range Min"),
        ("iRangeMax", "Range Max"),
        ("iFatigueExtra", "Fatigue Limit"),
        ("iFatigueChange", "Fatigue/Turn"),
    ]:
        v = e.findtext(tag)
        if v and v != "0":
            out.append(f"{fmt_decimal(int(v))} {label}")

    if (e.findtext("bIgnoreZOC") or "0") == "1":
        out.append("Ignores Zone of Control")
    if (e.findtext("bIgnoreHill") or "0") == "1":
        out.append("Ignores Hill movement penalty")
    if (e.findtext("bAmphibious") or "0") == "1":
        out.append("Amphibious")

    # Registry backstop: any other populated field the game renders
    # (iVisionExtra, iRiverAttackModifier, cooldowns, …) gets a generic line
    # instead of vanishing. Exclude what this renderer phrases itself.
    out.extend(effects.extra_lines(e, "effectUnit", exclude=_PROMO_COVERED))

    return out


_PROMO_COVERED = frozenset({
    "iStrengthModifier", "iAttackModifier", "iDefenseModifier",
    "iMoraleModifier", "iCityStrengthModifier", "iCityDefenseModifier",
    "aiUnitTraitModifier", "aiUnitTraitModifierAttack",
    "aiUnitTraitModifierDefense", "aiUnitTraitModifierMelee",
    "aiAttackValue", "aiAttackPercent", "aiTerrainFromModifier",
    "aiVegetationFromModifier", "aiHeightFromModifier",
    "iHealExtra", "iHealAlways", "iMovement", "iVision",
    "iRangeMin", "iRangeMax", "iFatigueExtra", "iFatigueChange",
    "bIgnoreZOC", "bIgnoreHill", "bAmphibious",
})


def gather_requires_attack(e: ET.Element) -> list[str]:
    """Attack types this promotion only *modifies* (aiAttackPercent > 0 with no
    aiAttackValue grant). Game.cs canPromote: such a promotion is only offered
    to units that already have that attack type (e.g. Shrapnel → Splash units
    like Onager / Mangonel / Akkadian & Cimmerian Archer)."""
    values = {
        p.findtext("zIndex"): int(p.findtext("iValue") or "0")
        for p in e.findall("aiAttackValue/Pair")
    }
    out: list[str] = []
    for pair in e.findall("aiAttackPercent/Pair"):
        a = pair.findtext("zIndex") or ""
        v = int(pair.findtext("iValue") or "0")
        if v > 0 and values.get(a, 0) == 0:
            out.append(attack_label(a))
    return out


def gather_valid_traits(e: ET.Element) -> tuple[list[str], list[str]]:
    """Return (valid_traits, invalid_traits) — the unit-trait gates on a promotion."""
    valid: list[str] = []
    for pair in e.findall("abUnitTraitValid/Pair"):
        if (pair.findtext("bValue") or "0") == "1":
            t = pair.findtext("zIndex") or ""
            if t:
                valid.append(trait_label(t))
    invalid: list[str] = []
    for pair in e.findall("abUnitTraitInvalid/Pair"):
        if (pair.findtext("bValue") or "0") == "1":
            t = pair.findtext("zIndex") or ""
            if t:
                invalid.append(trait_label(t))
    return valid, invalid


def derive_tier(prom_id: str, effect_id: str, effect_entry: ET.Element | None) -> int:
    """Tier = EffectUnit's iClassNum if present, else trailing digit of id, else 1."""
    if effect_entry is not None:
        cn = effect_entry.findtext("iClassNum")
        if cn and cn.isdigit():
            return int(cn)
    # Fallback: trailing digit on the id (COMBAT1 → 1)
    m = "".join(c for c in prom_id if c.isdigit())
    if m:
        return int(m[-1])
    return 1


def derive_class(prom_id: str, effect_entry: ET.Element | None) -> str:
    """Promotion 'family' / class name — used for chain grouping.
    Pulled from EffectUnit Class if available; otherwise stripped trailing digits."""
    if effect_entry is not None:
        cls = effect_entry.findtext("Class")
        if cls:
            return cls.replace("EFFECTUNITCLASS_", "").title()
    base = prom_id.replace("PROMOTION_", "")
    while base and base[-1].isdigit():
        base = base[:-1]
    return base.title()


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text = indexes.get("__text__", {})
    eu_idx = indexes.get("effectUnit.xml", {})

    # Build a reverse map: EffectUnit id → promotion id (so we can resolve
    # EffectUnitPrereq, which references an effect unit, back to its promotion).
    eu_to_prom: dict[str, str] = {}
    for entry in parse("promotion.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        eu = entry.findtext("EffectUnit") or ""
        if zt and eu:
            eu_to_prom[eu] = zt

    promotions: list[dict] = []
    for entry in parse("promotion.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt or not zt.startswith("PROMOTION_"):
            continue

        name_key = entry.findtext("Name") or ""
        name = text.get(name_key, zt.replace("PROMOTION_", "").replace("_", " ").title())

        effect_id = entry.findtext("EffectUnit") or ""
        effect_entry = eu_idx.get(effect_id)

        prereq_eu = entry.findtext("EffectUnitPrereq") or ""
        prereq_prom = eu_to_prom.get(prereq_eu) if prereq_eu else ""

        valid_traits, invalid_traits = ([], [])
        effects: list[str] = []
        requires_attack: list[str] = []
        if effect_entry is not None:
            effects = render_promotion_effect(effect_entry)
            valid_traits, invalid_traits = gather_valid_traits(effect_entry)
            requires_attack = gather_requires_attack(effect_entry)

        tier = derive_tier(zt, effect_id, effect_entry)
        cls = derive_class(zt, effect_entry)

        promotions.append({
            "id": zt,
            "slug": zt.replace("PROMOTION_", "").lower(),
            "name": name,
            "tier": tier,
            "class": cls,
            "effectUnit": effect_id,
            "prereqId": prereq_prom,
            "prereqName": (
                text.get(
                    (indexes.get("promotion.xml", {}).get(prereq_prom).findtext("Name") if indexes.get("promotion.xml", {}).get(prereq_prom) is not None else "") or "",
                    prereq_prom.replace("PROMOTION_", "").replace("_", " ").title(),
                ) if prereq_prom else ""
            ),
            "effects": effects,
            "validTraits": valid_traits,
            "invalidTraits": invalid_traits,
            "requiresAttack": requires_attack,
            "priority": (entry.findtext("bPriority") or "0") == "1",
            "gameContent": entry.findtext("GameContentRequired") or "",
        })

    promotions.sort(key=lambda p: (p["tier"], p["class"], p["slug"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(promotions, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(promotions)} promotions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
