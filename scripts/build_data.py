#!/usr/bin/env python3
"""
Build src/data/nations.json and src/styles/nation-tokens.css from:
  - reference/XML/Infos/*.xml   (canonical game data)
  - src/data/annotations/nations.yaml  (human-curated descriptions, seeded from xlsx)

Run after `make sync` or any time XML changes.
Deterministic output for clean git diffs.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_nation_effects, render_shrine_effects,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT_JSON = ROOT / "src" / "data" / "nations.json"
OUT_CSS = ROOT / "src" / "styles" / "nation-tokens.css"
ANNOTATIONS = ROOT / "src" / "data" / "annotations" / "nations.yaml"


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def first_form(s: str | None) -> str:
    """Game text strings are tilde-separated forms (singular~plural~adjective). Take the first."""
    if not s:
        return ""
    return s.split("~")[0].strip()


def load_text(filename: str) -> dict[str, str]:
    """Read a text-*.xml, return {zType: en-US first form}."""
    out: dict[str, str] = {}
    for entry in parse(filename).findall("Entry"):
        z = entry.findtext("zType")
        en = entry.findtext("en-US")
        if z and en:
            out[z] = first_form(en)
    return out


def load_colors() -> dict[str, dict[str, str]]:
    """Return {nation_id: {bg, text}} from color.xml."""
    colors: dict[str, dict[str, str]] = {}
    for entry in parse("color.xml").findall("Entry"):
        z = entry.findtext("zType") or ""
        hex_val = entry.findtext("zHexValue") or ""
        if not hex_val:
            continue
        # Normalize #RRGGBBAA → #RRGGBB
        if re.fullmatch(r"#[0-9a-fA-F]{8}", hex_val):
            hex_val = hex_val[:7]
        m = re.fullmatch(r"COLOR_(NATION_[A-Z_]+?)(_TEXT)?", z)
        if not m or "_FAMILY_" in m.group(1):
            continue
        nation = m.group(1)
        kind = "text" if m.group(2) else "bg"
        colors.setdefault(nation, {})[kind] = hex_val.lower()
    return colors


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(h: str) -> float:
    """Relative luminance per WCAG, 0..1."""
    def chan(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = hex_to_rgb(h)
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def best_fg(bg: str) -> str:
    """Pick black or white text for contrast against a tinted-down bg."""
    # In our dark theme cells, we overlay a 0.35-alpha black scrim on the bg.
    # That means the effective bg is darker than `bg` itself, so most colors want white text.
    # Only very light bgs (luma > 0.7) get black-ish text.
    return "#111418" if luminance(bg) > 0.65 else "#f5f6f8"


SHRINE_TYPE_PRIMARY_YIELD = {
    "WAR":        "TRAINING",
    "KINGSHIP":   "CIVICS",
    "WISDOM":     "SCIENCE",
    "SUN":        "ORDERS",
    "WATER":      "MONEY",
    "LOVE":       "GROWTH",
    "UNDERWORLD": "CULTURE",
    "HEARTH":     "CULTURE",
    "FIRE":       None,   # modifier-based: mines / lumber mills
    "HEALING":    None,   # modifier-based: grove / healer
    "HUNTING":    None,   # modifier-based: farms / camps / ranged
}
# Keyword fallback for FIRE/HEALING/HUNTING — match against yaml shrine text
SHRINE_TYPE_KEYWORDS = {
    "FIRE":    ["mine", "lumber"],
    "HEALING": ["grove", "healer"],
    "HUNTING": ["farm", "camp", "ranged"],
}


def load_shrines() -> dict[str, list[dict]]:
    """Return {nation_id: [shrine_dict, ...]} sorted by iSubClass."""
    text_improvement = load_text("text-improvement.xml")
    out: dict[str, list[dict]] = {}
    for entry in parse("improvement.xml").findall("Entry"):
        if (entry.findtext("Class") or "") != "IMPROVEMENTCLASS_SHRINE":
            continue
        nation = entry.findtext("NationPrereq") or ""
        if not nation.startswith("NATION_"):
            continue
        zt = entry.findtext("zType") or ""
        name_key = entry.findtext("Name") or ""
        # Shrine of Ninurta → Ninurta (drop "Shrine of " prefix)
        full = text_improvement.get(name_key, zt.replace("IMPROVEMENT_SHRINE_", "").title())
        deity = full.replace("Shrine of ", "").strip()

        av = entry.findtext("AssetVariation") or ""
        type_match = re.match(r"ASSET_VARIATION_IMPROVEMENT_SHRINE_([A-Z]+)", av)
        type_key = type_match.group(1) if type_match else "UNKNOWN"

        sub = int(entry.findtext("iSubClass") or "0")

        primary_yield = SHRINE_TYPE_PRIMARY_YIELD.get(type_key)
        # Pull yield outputs to also show what the shrine itself produces
        outputs: list[dict] = []
        for pair in entry.findall("aiYieldOutput/Pair"):
            yk = pair.findtext("zIndex") or ""
            iv = pair.findtext("iValue") or "0"
            if yk.startswith("YIELD_"):
                outputs.append({"yield": yk[6:].lower(), "value": int(iv)})

        out.setdefault(nation, []).append({
            "id": zt,
            "name": deity,
            "fullName": full,
            "type": type_key,
            "typeLabel": type_key.title(),
            "subClass": sub,
            "primaryYield": primary_yield,
            "yieldOutput": outputs,
        })
    for n in out:
        out[n].sort(key=lambda s: s["subClass"])
    return out


def match_yaml_shrines(yaml_shrines: list[str], xml_shrines: list[dict]) -> list[dict]:
    """For each yaml string, attach the matching XML shrine by primary yield (heuristic).
    Returns list of {effect, shrine} in yaml order."""
    if not yaml_shrines or not xml_shrines:
        return [{"effect": s, "shrine": None} for s in yaml_shrines]

    yield_to_shrine: dict[str, dict] = {}
    for s in xml_shrines:
        if s["primaryYield"]:
            yield_to_shrine.setdefault(s["primaryYield"], s)
    keyword_to_shrine: list[tuple[str, dict]] = []
    for s in xml_shrines:
        for kw in SHRINE_TYPE_KEYWORDS.get(s["type"], []):
            keyword_to_shrine.append((kw, s))

    used_ids: set[str] = set()
    pairs: list[dict] = []
    for effect in yaml_shrines:
        lower = effect.lower()
        chosen: dict | None = None
        # Try primary yield match
        for y, shrine in yield_to_shrine.items():
            yname = y.lower()
            short = {"orders": "order", "training": "training", "science": "sci",
                     "civics": "civic", "culture": "cult", "growth": "growth",
                     "money": "money"}.get(yname, yname)
            if short in lower and shrine["id"] not in used_ids:
                chosen = shrine
                break
        if not chosen:
            for kw, shrine in keyword_to_shrine:
                if kw in lower and shrine["id"] not in used_ids:
                    chosen = shrine
                    break
        if chosen:
            used_ids.add(chosen["id"])
        pairs.append({"effect": effect, "shrine": chosen})

    # Backfill any unmatched yaml entries with leftover XML shrines (by iSubClass)
    leftovers = [s for s in xml_shrines if s["id"] not in used_ids]
    for p in pairs:
        if p["shrine"] is None and leftovers:
            p["shrine"] = leftovers.pop(0)

    return pairs


def load_characters() -> dict[str, dict]:
    """Index character.xml entries by zType. Each char carries
    aeTraits + PreferredPortrait so we can show founder traits + portrait."""
    out: dict[str, dict] = {}
    if not (XML_DIR / "character.xml").exists():
        return out
    text_infos = load_text("text-infos.xml")
    text_trait = load_text("text-trait.xml") if (XML_DIR / "text-trait.xml").exists() else {}
    for entry in parse("character.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("CHARACTER_"):
            continue
        first_name_key = entry.findtext("FirstName") or ""
        display = text_infos.get(first_name_key, zt.replace("CHARACTER_", "").title())
        traits = []
        for t in entry.findall("aeTraits/zValue"):
            tk = t.text or ""
            if not tk:
                continue
            traits.append({
                "id": tk,
                "label": text_trait.get(f"TEXT_{tk}", tk.replace("TRAIT_", "").replace("_", " ").title()),
            })
        out[zt] = {
            "name": display,
            "gender": entry.findtext("Gender") or "",
            "age": int(entry.findtext("iAge") or "0"),
            "preferredPortrait": entry.findtext("PreferredPortrait") or "",
            "url": entry.findtext("URL") or "",
            "traits": traits,
        }
    return out


def find_portrait(character_name: str) -> str | None:
    """Return public/img path for a historical-person portrait whose name
    matches the character. We look up by the uppercased character name."""
    PORTRAITS = ROOT / "public" / "img" / "portraits" / "historical"
    if not PORTRAITS.exists():
        return None
    upper = character_name.upper().replace(" ", "_")
    for suffix in ["", "_elder", "_adult", "_teen", "_senior"]:
        candidate = PORTRAITS / f"{upper.lower()}{suffix}.png"
        if candidate.exists():
            return f"img/portraits/historical/{candidate.name}"
    return None


def load_dynasties(characters: dict[str, dict]) -> dict[str, list[dict]]:
    """Return {nation_id: [dynasty_dict, ...]} from dynasty.xml. Each dynasty
    is enriched with its founder character's traits and portrait."""
    text_infos = load_text("text-infos.xml")
    out: dict[str, list[dict]] = {}
    if not (XML_DIR / "dynasty.xml").exists():
        return out
    for entry in parse("dynasty.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("DYNASTY_"):
            continue
        nation = entry.findtext("Nation") or ""
        if not nation:
            continue
        name = text_infos.get(entry.findtext("Name") or "", zt.replace("DYNASTY_", "").title())
        desc = text_infos.get(entry.findtext("Description") or "", "")
        founder_id = entry.findtext("Founder") or ""
        first_ruler_id = entry.findtext("FirstRuler") or ""
        founder = characters.get(founder_id) if founder_id else None
        first_ruler = characters.get(first_ruler_id) if first_ruler_id else None
        # Prefer the FirstRuler for portrait + traits — the dynasty's playable
        # leader at game start. Fall back to founder.
        primary = first_ruler or founder
        primary_name = first_ruler["name"] if first_ruler else (founder["name"] if founder else "")
        portrait = find_portrait(primary_name) if primary_name else None
        out.setdefault(nation, []).append({
            "id": zt,
            "slug": zt.replace("DYNASTY_", "").lower(),
            "name": name,
            "description": desc,
            "founder": founder["name"] if founder else None,
            "firstRuler": first_ruler["name"] if first_ruler else None,
            "leaderAge": primary["age"] if primary else None,
            "leaderTraits": primary["traits"] if primary else [],
            "leaderUrl": primary["url"] if primary else "",
            "portrait": portrait,
            "gameContent": entry.findtext("GameContentRequired") or "",
        })
    return out


def load_nations() -> list[dict]:
    text_nation = load_text("text-nation.xml")
    text_family = load_text("text-family.xml")
    text_infos = load_text("text-infos.xml")
    text_unit = load_text("text-unit.xml") if (XML_DIR / "text-unit.xml").exists() else {}
    colors = load_colors()
    shrines_by_nation = load_shrines()
    characters = load_characters()
    dynasties_by_nation = load_dynasties(characters)
    xml_indexes = load_xml_indexes(XML_DIR)
    text_cityname = load_text("text-cityname.xml") if (XML_DIR / "text-cityname.xml").exists() else {}
    text_name = load_text("text-name.xml") if (XML_DIR / "text-name.xml").exists() else {}
    text_unit_for_starts = load_text("text-unit.xml") if (XML_DIR / "text-unit.xml").exists() else {}

    # Per-nation per-family hex (e.g., COLOR_NATION_ASSYRIA_FAMILY_01 → #b53c01).
    # Also alias the YEUZHI typo so the Yuezhi families pick up colors.
    family_hex: dict[tuple[str, int], str] = {}
    for entry in parse("color.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        hex_val = (entry.findtext("zHexValue") or "")
        m = re.fullmatch(r"COLOR_(NATION_[A-Z_]+)_FAMILY_(\d+)", zt)
        if m and hex_val:
            if re.fullmatch(r"#[0-9a-fA-F]{8}", hex_val):
                hex_val = hex_val[:7]
            family_hex[(m.group(1), int(m.group(2)))] = hex_val.lower()
            if m.group(1) == "NATION_YEUZHI":
                family_hex[("NATION_YUEZHI", int(m.group(2)))] = hex_val.lower()

    # Map family → (nation_id, class). Prefer abNation (canonical nation
    # reference) over TeamColor — Yuezhi has a typo'd TEAMCOLOR_NATION_YEUZHI
    # in the game data while abNation correctly says NATION_YUEZHI.
    families_by_nation: dict[str, list[dict]] = defaultdict(list)
    for entry in parse("family.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        name_key = entry.findtext("Name") or ""
        team_color = entry.findtext("TeamColor") or ""
        family_class = entry.findtext("FamilyClass") or ""
        color_idx = entry.findtext("iColorIndex") or "0"
        if not zt:
            continue
        nation = ""
        ab_nation_pairs = entry.findall("abNation/Pair")
        for p in ab_nation_pairs:
            if (p.findtext("bValue") or "0") == "1":
                nation = p.findtext("zIndex") or ""
                break
        if not nation and team_color.startswith("TEAMCOLOR_NATION_"):
            nation = team_color.replace("TEAMCOLOR_", "")
        if not nation:
            continue
        class_key = f"TEXT_{family_class}"  # TEXT_FAMILYCLASS_CHAMPIONS
        # XML uses 1-based slot numbers (FAMILY_01..04); iColorIndex is 0-based.
        slot = int(color_idx) + 1
        hex_color = family_hex.get((nation, slot))
        class_label = text_infos.get(class_key, family_class.replace("FAMILYCLASS_", "").title())
        families_by_nation[nation].append({
            "id": zt,
            "name": text_family.get(name_key, zt.replace("FAMILY_", "").title()),
            "class": class_label,
            "classKey": family_class.replace("FAMILYCLASS_", "").lower(),
            "colorIndex": int(color_idx),
            "ingameColor": hex_color,
            "ingameFg": best_fg(hex_color) if hex_color else "#f5f6f8",
        })

    # Build nations
    nations = []
    for entry in parse("nation.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt or not zt.startswith("NATION_"):
            continue
        gendered = entry.findtext("GenderedName") or ""
        # GENDERED_TEXT_NATION_ASSYRIA → TEXT_NATION_ASSYRIA
        text_key = gendered.replace("GENDERED_", "")
        name = text_nation.get(text_key, zt.replace("NATION_", "").title())

        starting_tech = [t.text.replace("TECH_", "").replace("_", " ").title()
                         for t in entry.findall("aeStartingTech/zValue") if t.text]
        starting_law = [t.text.replace("LAW_", "").replace("_", " ").title()
                        for t in entry.findall("aeStartingLaw/zValue") if t.text]
        dynasties = [t.text.replace("DYNASTY_", "").title()
                     for t in entry.findall("aeDynasties/zValue") if t.text]

        c = colors.get(zt, {"bg": "#444", "text": "#aaa"})
        bg = c.get("bg", "#444")
        fg = best_fg(bg)

        fams = sorted(families_by_nation.get(zt, []), key=lambda f: f["colorIndex"])
        nation_shrines = shrines_by_nation.get(zt, [])

        # City names (resolved to display text)
        city_names = []
        for cn in entry.findall("aeCityNames/zValue"):
            key = cn.text or ""
            if key:
                city_names.append(text_cityname.get(key, key.replace("CITYNAME_", "").title()))

        # First name pools
        first_names_male = []
        for nm in entry.findall("aeFirstNamesMale/zValue"):
            key = nm.text or ""
            if key:
                first_names_male.append(text_name.get(key, key.replace("NAME_", "").title()))
        first_names_female = []
        for nm in entry.findall("aeFirstNamesFemale/zValue"):
            key = nm.text or ""
            if key:
                first_names_female.append(text_name.get(key, key.replace("NAME_", "").title()))

        # Starting units (the first turn): pairs of (unit, count)
        start_units = []
        for pair in entry.findall("aiStartUnit/Pair"):
            uk = (pair.findtext("zIndex") or "")
            n_count = int(pair.findtext("iValue") or "0")
            if uk:
                start_units.append({
                    "id": uk,
                    "name": text_unit_for_starts.get(f"TEXT_{uk}", uk.replace("UNIT_", "").replace("_", " ").title()),
                    "count": n_count,
                    "slug": uk.replace("UNIT_", "").lower().replace("_", "-"),
                })
        # Initial city units (Worker, etc. spawned with the capital)
        city_units = []
        for pair in entry.findall("aiCityUnit/Pair"):
            uk = (pair.findtext("zIndex") or "")
            n_count = int(pair.findtext("iValue") or "0")
            if uk:
                city_units.append({
                    "id": uk,
                    "name": text_unit_for_starts.get(f"TEXT_{uk}", uk.replace("UNIT_", "").replace("_", " ").title()),
                    "count": n_count,
                    "slug": uk.replace("UNIT_", "").lower().replace("_", "-"),
                })

        first_build_id = entry.findtext("FirstBuild") or ""
        first_build_name = text_unit_for_starts.get(f"TEXT_{first_build_id}", first_build_id.replace("UNIT_", "").title()) if first_build_id else ""

        # Title labels
        leader_title = text_infos.get(entry.findtext("LeaderTitle") or "", "")
        heir_title = text_infos.get(entry.findtext("HeirTitle") or "", "")
        regent_title = text_infos.get(entry.findtext("RegentTitle") or "", "")
        successor_title = text_infos.get(entry.findtext("SuccessorTitle") or "", "")

        # Auto-derived bonus list from the game's effect tree.
        effect_player_id = (entry.findtext("EffectPlayer") or "").strip()
        effects_xml = render_nation_effects(effect_player_id, xml_indexes) if effect_player_id else []

        # Auto-derived shrine effects (per shrine)
        for s in nation_shrines:
            shrine_entry = xml_indexes.get("improvement.xml", {}).get(s["id"])
            if shrine_entry is not None:
                s["effectsXml"] = render_shrine_effects(shrine_entry)

        nations.append({
            "id": zt,
            "slug": zt.replace("NATION_", "").lower(),
            "name": name,
            "color": {"bg": bg, "fg": fg, "ingameText": c.get("text", bg)},
            "startingTech": starting_tech,
            "startingLaw": starting_law,
            "dynasties": dynasties,
            "dynastyDetails": dynasties_by_nation.get(zt, []),
            "families": fams,
            "shrineXml": nation_shrines,
            "effectsXml": effects_xml,
            "cityNames": city_names,
            "firstNamesMale": first_names_male,
            "firstNamesFemale": first_names_female,
            "startUnits": start_units,
            "cityUnits": city_units,
            "firstBuild": {"id": first_build_id, "name": first_build_name} if first_build_id else None,
            "titles": {
                "leader": leader_title,
                "heir": heir_title,
                "regent": regent_title,
                "successor": successor_title,
            },
            "playable": (entry.findtext("bPlayable") == "1") or entry.findtext("bPlayable") is None,
            "gameContent": entry.findtext("GameContentRequired") or "",
        })

    # Stable order — by slug
    nations.sort(key=lambda n: n["slug"])
    return nations


def load_annotations() -> dict:
    if not ANNOTATIONS.exists():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        print("⚠ pyyaml not installed; skipping annotations layer", file=sys.stderr)
        return {}
    return yaml.safe_load(ANNOTATIONS.read_text()) or {}


def merge_annotations(nations: list[dict], annotations: dict) -> list[dict]:
    """Overlay human-curated bonuses/shrines/uu text onto canonical XML data,
    and pair yaml shrines with XML shrines by primary yield."""
    by_slug = {n["slug"]: n for n in nations}
    for slug, ann in (annotations.get("nations") or {}).items():
        if slug not in by_slug:
            continue
        n = by_slug[slug]
        yaml_shrines = ann.get("shrines", []) or []
        matched = match_yaml_shrines(yaml_shrines, n.get("shrineXml", []) or [])
        n.update({
            "bonuses": ann.get("bonuses", []),
            "shrines": matched,
            "uniqueUnit": ann.get("uniqueUnit", {}),
            "leader": ann.get("leader", {}),
        })
    return nations


def write_css(nations: list[dict]) -> None:
    lines = [
        "/* Generated by scripts/build_data.py — do not edit by hand. */",
        "/* Each nation gets a CSS class with --nation-bg and --nation-fg tokens. */",
        "",
    ]
    for n in nations:
        lines.append(f".n-{n['slug']} {{")
        lines.append(f"  --nation-bg: {n['color']['bg']};")
        lines.append(f"  --nation-fg: {n['color']['fg']};")
        lines.append(f"  --nation-ingame: {n['color']['ingameText']};")
        lines.append("}")
    OUT_CSS.write_text("\n".join(lines) + "\n")


def main() -> int:
    nations = load_nations()
    annotations = load_annotations()
    nations = merge_annotations(nations, annotations)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(nations, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    write_css(nations)
    print(f"✓ wrote {OUT_JSON.relative_to(ROOT)} ({len(nations)} nations)")
    print(f"✓ wrote {OUT_CSS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
