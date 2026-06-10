#!/usr/bin/env python3
"""
Build src/data/opinion.json from opinionFamily / opinionTribe / opinionCharacter
/ opinionPlayer XML.

Each of those XML files defines the bracket table for a relationship type:
Furious / Angry / Upset / Cautious / Pleased / Friendly. Each bracket lists
the gameplay effects that apply at that level (maintenance, training,
unit strength, war probability, etc.).

The spreadsheet's "Opinion" tab is the cross-product: relationship type ×
bracket × effect category. We mirror that here so the page can render four
tables, one per relationship type.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "opinion.json"


# Canonical bracket order (worst → best). Matches the spreadsheet's column order.
BRACKET_ORDER = ["FURIOUS", "ANGRY", "UPSET", "CAUTIOUS", "PLEASED", "FRIENDLY"]


# Per relationship type, label each scalar field with a human caption + sign
# convention. (sign_negative_good: True for fields where a negative number is
# the *desirable* outcome — e.g. -50% Mercenary Cost is good for the player.)
FIELD_LABELS: dict[str, dict[str, str]] = {
    "Family": {
        # opinionFamily: only EffectCity / EffectUnit pointers. The actual
        # mechanical effects live in those effectCity / effectUnit entries.
    },
    "Tribe": {
        "iStartAlliancePercent":    "Start Alliance %",
        "iEndAlliancePercent":      "End Alliance %",
        "iPeacePercent":            "Peace %",
        "iTrucePercent":            "Truce %",
        "iWarPercent":              "War %",
        "iRaidDistModifier":        "Raid Distance",
        "iMercenaryCostModifier":   "Mercenary Cost",
        "iSettleCostModifier":      "Settle Cost",
    },
    "Character": {
        "iBirthModifier":           "Birth %",
        "iMissionCostModifier":     "Mission Cost",
        "iRateModifier":            "Job Yield %",
        "iStrengthModifier":        "Unit Strength %",
    },
    "Player": {
        "iStartAlliancePercent":    "Start Alliance %",
        "iEndAlliancePercent":      "End Alliance %",
        "iPeacePercent":            "Peace %",
        "iTrucePercent":            "Truce %",
        "iWarPercent":              "War %",
        "bDeclareWar":              "Can Declare War",
    },
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text(*filenames: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").split("~")[0].strip()
            if k:
                out[k] = en
    return out


def humanize_effect_city(idx: dict, effect_city_id: str) -> list[str]:
    """Render the EFFECTCITY_OPINIONFAMILY_* entry as readable lines."""
    if not effect_city_id:
        return []
    ec = idx.get(effect_city_id)
    if ec is None:
        return []
    out: list[str] = []
    # Yield modifiers (e.g., +50% maintenance, -20% training)
    for pair in ec.findall("aiYieldModifier/Pair"):
        y = (pair.findtext("zIndex") or "").replace("YIELD_", "").title()
        v = int(pair.findtext("iValue") or "0")
        sign = "+" if v > 0 else ""
        out.append(f"{sign}{v}% {y}")
    # Rate yields (per-city flat numbers)
    for pair in ec.findall("aiYieldRate/Pair"):
        y = (pair.findtext("zIndex") or "").replace("YIELD_", "").title()
        v = int(pair.findtext("iValue") or "0") / 10
        sign = "+" if v > 0 else ""
        out.append(f"{sign}{v} {y}/City")
    # Hurry / rebel flags
    if (ec.findtext("bNoHurry") or "0") == "1":
        out.append("Cannot hurry production")
    # XML field is iRebelProb (NOT iRebelChance — that field doesn't exist)
    rebel = ec.findtext("iRebelProb") or "0"
    if rebel and rebel != "0":
        out.append(f"+{rebel}% Rebel Chance")
    return out


def humanize_effect_unit(idx: dict, effect_unit_id: str) -> list[str]:
    """Render the EFFECTUNIT_OPINIONFAMILY_* entry as readable lines."""
    if not effect_unit_id:
        return []
    eu = idx.get(effect_unit_id)
    if eu is None:
        return []
    out: list[str] = []
    sm = eu.findtext("iStrengthModifier") or "0"
    if sm and sm != "0":
        sign = "+" if int(sm) > 0 else ""
        out.append(f"{sign}{sm}% Unit Strength")
    return out


def fmt_scalar(field: str, value: str) -> str:
    """Render a single scalar opinion field with appropriate sign + suffix."""
    if field.startswith("b"):
        return "Yes" if value == "1" else "No"
    try:
        v = int(value)
    except ValueError:
        return value
    if v == 0:
        return ""
    sign = "+" if v > 0 else ""
    # Most are percentage modifiers
    return f"{sign}{v}%"


def build_table(filename: str, kind: str) -> dict:
    """Read one opinionX.xml + return a structured bracket table."""
    root = parse(filename)
    brackets: list[dict] = []

    # Build effectCity/effectUnit indexes if we need to recurse
    ec_idx: dict[str, ET.Element] = {}
    eu_idx: dict[str, ET.Element] = {}
    ec_file = XML_DIR / "effectCity.xml"
    eu_file = XML_DIR / "effectUnit.xml"
    if ec_file.exists():
        ec_idx = {e.findtext("zType"): e for e in ET.parse(ec_file).getroot().findall("Entry") if e.findtext("zType")}
    if eu_file.exists():
        eu_idx = {e.findtext("zType"): e for e in ET.parse(eu_file).getroot().findall("Entry") if e.findtext("zType")}

    field_map = FIELD_LABELS[kind]

    for entry in root.findall("Entry"):
        zid = entry.findtext("zType") or ""
        if not zid:
            continue
        # Pull bracket name from the suffix
        bracket = zid.split("_")[-1]
        if bracket not in BRACKET_ORDER:
            continue

        threshold = entry.findtext("iThreshold")
        threshold_int = int(threshold) if threshold else None

        scalars: list[dict] = []
        # Order fields per FIELD_LABELS dict to match a stable column order
        for field, label in field_map.items():
            raw = entry.findtext(field) or "0"
            if raw == "0" or raw == "":
                continue
            scalars.append({"field": field, "label": label, "value": fmt_scalar(field, raw)})

        city_effects: list[str] = []
        unit_effects: list[str] = []
        if kind == "Family":
            city_effects = humanize_effect_city(ec_idx, entry.findtext("EffectCity") or "")
            unit_effects = humanize_effect_unit(eu_idx, entry.findtext("EffectUnit") or "")

        brackets.append({
            "bracket": bracket,
            "label": bracket.title(),
            "threshold": threshold_int,
            "scalars": scalars,
            "cityEffects": city_effects,
            "unitEffects": unit_effects,
        })

    brackets.sort(key=lambda b: BRACKET_ORDER.index(b["bracket"]))

    # Threshold range label — e.g. Angry is "-199 / -100" because Furious's
    # threshold is -200 and Angry's is -100.
    for i, b in enumerate(brackets):
        lo = brackets[i - 1]["threshold"] + 1 if i > 0 and brackets[i - 1]["threshold"] is not None else None
        hi = b["threshold"]
        if i == 0:
            b["range"] = f"≤ {hi}"
        elif b["threshold"] is None:
            # Last bucket (Friendly) has no upper threshold
            b["range"] = f"≥ {lo}"
        else:
            b["range"] = f"{lo} / {hi}"

    return {
        "kind": kind,
        "label": kind,
        "brackets": brackets,
    }


def main() -> int:
    tables = [
        build_table("opinionFamily.xml",    "Family"),
        build_table("opinionTribe.xml",     "Tribe"),
        build_table("opinionCharacter.xml", "Character"),
        build_table("opinionPlayer.xml",    "Player"),
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(tables, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    total = sum(len(t["brackets"]) for t in tables)
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(tables)} tables, {total} brackets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
