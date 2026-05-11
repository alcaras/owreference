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


def load_nations() -> list[dict]:
    text_nation = load_text("text-nation.xml")
    text_family = load_text("text-family.xml")
    text_infos = load_text("text-infos.xml")
    text_unit = load_text("text-unit.xml") if (XML_DIR / "text-unit.xml").exists() else {}
    colors = load_colors()
    shrines_by_nation = load_shrines()

    # Map family → (nation_id, class)
    families_by_nation: dict[str, list[dict]] = defaultdict(list)
    for entry in parse("family.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        name_key = entry.findtext("Name") or ""
        team_color = entry.findtext("TeamColor") or ""
        family_class = entry.findtext("FamilyClass") or ""
        color_idx = entry.findtext("iColorIndex") or "0"
        if not zt or not team_color.startswith("TEAMCOLOR_NATION_"):
            continue
        nation = team_color.replace("TEAMCOLOR_", "")  # NATION_ASSYRIA
        class_key = f"TEXT_{family_class}"  # TEXT_FAMILYCLASS_CHAMPIONS
        families_by_nation[nation].append({
            "id": zt,
            "name": text_family.get(name_key, zt.replace("FAMILY_", "").title()),
            "class": text_infos.get(class_key, family_class.replace("FAMILYCLASS_", "").title()),
            "colorIndex": int(color_idx),
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

        nations.append({
            "id": zt,
            "slug": zt.replace("NATION_", "").lower(),
            "name": name,
            "color": {"bg": bg, "fg": fg, "ingameText": c.get("text", bg)},
            "startingTech": starting_tech,
            "startingLaw": starting_law,
            "dynasties": dynasties,
            "families": fams,
            "shrineXml": nation_shrines,
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
