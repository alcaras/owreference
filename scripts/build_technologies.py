#!/usr/bin/env python3
"""
Build src/data/technologies.json from tech.xml + the merged text index.

Each tech entry captures: id, slug, name, icon, cost, era (column), row,
prereq tech ids, and a list of XML-derived "unlocks" lines (humanized
EffectPlayer / EffectCity content). Hidden boost techs (`bHide=1`) are
filtered out — they're discovery-only and not part of the visible tree.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_nation_effects, _lookup_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "technologies.json"


# tech.xml uses iColumn 0..7 to position techs on the tree. The legacy
# spreadsheet groups these into named eras — we mirror that mapping.
ERA_LABELS = {
    0: "Bronze",
    1: "Iron",
    2: "Classical",
    3: "Imperial",
    4: "Royal",
    5: "Steel",
    6: "Heroic",
    7: "Renaissance",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def slug_of(tech_id: str) -> str:
    return tech_id.replace("TECH_", "").lower()


def icon_slug(z_icon: str) -> str:
    """tech.xml zIconName is like TECH_IRONWORKING — the file is ironworking.png."""
    return z_icon.replace("TECH_", "").lower()


def reverse_unlocks(indexes: dict) -> dict[str, dict[str, list[str]]]:
    """Build {tech_id: {category: [name, …]}} by scanning every XML that
    references TechPrereq. Tech XML lists the EffectPlayer it ships with, but
    the actual unlocks (units, projects, laws, improvements, buildings) all
    point *at* the tech from their own entries. This is the reverse index."""
    text = indexes.get("__text__", {})
    out: dict[str, dict[str, list[str]]] = {}

    def add(tech_id: str, category: str, label: str) -> None:
        if not tech_id or not tech_id.startswith("TECH_") or not label:
            return
        bucket = out.setdefault(tech_id, {})
        bucket.setdefault(category, []).append(label)

    # The humanizer doesn't index unit.xml / project.xml / build.xml /
    # improvement.xml for raw text lookup — they're on the lookup index but we
    # still need to walk the raw XML once to find TechPrereq references.
    for filename, category, _name_format in [
        ("unit.xml",        "Units",        "TEXT_UNIT_"),
        ("project.xml",     "Projects",     "TEXT_PROJECT_"),
        ("law.xml",         "Laws",         "TEXT_LAW_"),
        ("improvement.xml", "Improvements", "TEXT_IMPROVEMENT_"),
        ("build.xml",       "Builds",       "TEXT_BUILD_"),
    ]:
        path = XML_DIR / filename
        if not path.exists():
            continue
        for entry in ET.parse(path).getroot().findall("Entry"):
            zt = entry.findtext("zType") or ""
            if not zt:
                continue
            name_key = entry.findtext("Name") or ""
            label = text.get(name_key) or ""
            if not label:
                # Friendly fallback from the zType
                prefix = zt.split("_")[0] + "_"
                label = zt.replace(prefix, "").replace("_", " ").title()
            # Skip hidden / template entries
            if (entry.findtext("bHide") or "") == "1":
                continue
            # TechPrereq field exists on units/projects/laws/improvements
            tp = entry.findtext("TechPrereq")
            if tp:
                add(tp, category, label)
            # Some entries have abTechPrereq pairs (e.g., builds)
            for pair in entry.findall("abTechPrereq/Pair"):
                if (pair.findtext("bValue") or "0") == "1":
                    pid = pair.findtext("zIndex") or ""
                    if pid:
                        add(pid, category, label)

    # Deduplicate while preserving order
    for tech, cats in out.items():
        for cat, items in cats.items():
            seen: set[str] = set()
            uniq: list[str] = []
            for it in items:
                if it not in seen:
                    seen.add(it)
                    uniq.append(it)
            cats[cat] = uniq

    return out


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text = indexes.get("__text__", {})
    unlocks_index = reverse_unlocks(indexes)

    techs: list[dict] = []
    for entry in parse("tech.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt or not zt.startswith("TECH_"):
            continue
        # Skip the empty template entry and the hidden boost techs.
        if (entry.findtext("bHide") or "") == "1":
            continue

        name_key = entry.findtext("Name") or ""
        name = text.get(name_key, zt.replace("TECH_", "").replace("_", " ").title())
        z_icon = entry.findtext("zIconName") or zt

        prereqs: list[str] = []
        for pair in entry.findall("abTechPrereq/Pair"):
            if (pair.findtext("bValue") or "0") == "1":
                pid = pair.findtext("zIndex") or ""
                if pid:
                    prereqs.append(pid)

        col = int(entry.findtext("iColumn") or "0")
        row = int(entry.findtext("iRow") or "0")
        cost = int(entry.findtext("iCost") or "0")

        # Unlocked content from the player effect tree (humanized).
        unlocks: list[str] = []
        eff_player = entry.findtext("EffectPlayer") or ""
        if eff_player:
            unlocks = render_nation_effects(eff_player, indexes)

        # And from the reverse index — what units/projects/laws/improvements
        # list this tech as their prereq.
        unlocked_by_category: dict[str, list[str]] = unlocks_index.get(zt, {})

        techs.append({
            "id": zt,
            "slug": slug_of(zt),
            "name": name,
            "icon": f"img/icons/techs/{icon_slug(z_icon)}.png",
            "cost": cost,
            "column": col,
            "row": row,
            "era": ERA_LABELS.get(col, f"Era {col}"),
            "prereqs": [{
                "id": p,
                "slug": slug_of(p),
                "name": text.get(
                    (indexes.get("tech.xml", {}).get(p).findtext("Name") if indexes.get("tech.xml", {}).get(p) is not None else "") or "",
                    p.replace("TECH_", "").replace("_", " ").title(),
                ),
            } for p in prereqs],
            "unlocks": unlocks,
            "unlocksByCategory": unlocked_by_category,
        })

    techs.sort(key=lambda t: (t["column"], t["row"], t["slug"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(techs, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(techs)} techs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
