#!/usr/bin/env python3
"""
Build src/data/mapscripts.json — the procedurally-generated map scripts
(Continent, Inland Sea, Archipelago, Seaside, …) and their per-script
generation options.

These are the *generated* map types, not the hand-built preset scenario
maps. Names + descriptions come from text-map.xml (TEXT_MAP_NAME_<S> /
TEXT_MAP_HELP_<S>). Per-script options come from mapOption.xml entries
keyed MAP_OPTION_<S>_<GROUP>_<VALUE>, with their label/help in text-map.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import _strip_link_templates  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "mapscripts.json"

# A handful of scripts key their options under a shortened prefix.
OPTION_PREFIX_ALIAS = {
    "ARID_PLATEAU": "ARID",
}

# Option-group keywords, longest/most-specific first. The remainder after
# MAP_OPTION_<script>_ is matched against these to bucket the choice.
GROUP_KEYS = [
    ("PLAYER_START", "Player Start"),
    ("WATER_LOCATION", "Water Location"),
    ("WATER_SIZE", "Water Size"),
    ("CONTINENTS_NUMBER", "Continents"),
    ("CONTINENTS", "Continents"),
    ("TRIBES", "Tribes"),
    ("TERRAIN", "Terrain"),
    ("COAST", "Coast"),
    ("NUMBER", "Number"),
    ("SIZE", "Size"),
    ("LOCATION", "Location"),
    ("START", "Start"),
]

# Scripts tuned for a fixed/duel layout rather than the open-ended
# generators — surfaced but flagged so the page can group them apart.
SPECIAL_SCRIPTS = {"DOTA", "PLAYER_ISLANDS"}


def first(s: str | None) -> str:
    return _strip_link_templates((s or "").split("~")[0].strip()).replace("{br}", " ").strip()


def load_text(*names: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in names:
        p = XML_DIR / n
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            if k:
                out[k] = first(e.findtext("en-US"))
    return out


def main() -> int:
    T = load_text("text-map.xml", "text-calamities-map.xml")

    # Script keys = TEXT_MAP_NAME_<S> (excluding the _HELP siblings).
    script_keys = sorted(
        k[len("TEXT_MAP_NAME_"):]
        for k in T
        if k.startswith("TEXT_MAP_NAME_") and not k.endswith("_HELP")
    )

    opt_root = ET.parse(XML_DIR / "mapOption.xml").getroot()
    opt_entries = [
        (e.findtext("zType") or "", e)
        for e in opt_root.findall("Entry")
        if (e.findtext("zType") or "").startswith("MAP_OPTION_")
    ]

    scripts: list[dict] = []
    for s in script_keys:
        name = T.get(f"TEXT_MAP_NAME_{s}", s.replace("_", " ").title())
        desc = (
            T.get(f"TEXT_MAP_HELP_{s}")
            or T.get(f"TEXT_MAP_NAME_{s}_HELP")
            or T.get(f"TEXT_MAP_DESC_{s}")
            or ""
        )

        prefix = OPTION_PREFIX_ALIAS.get(s, s)
        token = f"MAP_OPTION_{prefix}_"

        groups: dict[str, list[dict]] = {}
        for zt, e in opt_entries:
            if not zt.startswith(token) or zt.endswith("_HELP"):
                continue
            rest = zt[len(token):]
            group_label = None
            value = rest
            for key, label in GROUP_KEYS:
                if rest == key or rest.startswith(key + "_"):
                    group_label = label
                    value = rest[len(key):].lstrip("_") or "Default"
                    break
            if group_label is None:
                group_label = "Variant"

            opt_name = first(e.findtext("Name") and T.get(e.findtext("Name"), "")) \
                or T.get(f"TEXT_{zt}") \
                or value.replace("_", " ").title()
            opt_help = first(e.findtext("Description") and T.get(e.findtext("Description"), "")) \
                or T.get(f"TEXT_{zt}_HELP") \
                or ""
            groups.setdefault(group_label, []).append(
                {"label": opt_name, "help": opt_help}
            )

        # Stable ordering: known group order, then alpha for any extras.
        order = [lbl for _, lbl in GROUP_KEYS] + ["Variant"]
        ordered_groups = [
            {"group": g, "choices": groups[g]}
            for g in sorted(groups, key=lambda g: (order.index(g) if g in order else 99, g))
        ]

        scripts.append({
            "slug": s.lower().replace("_", "-"),
            "id": s,
            "name": name,
            "description": desc,
            "special": s in SPECIAL_SCRIPTS,
            "optionGroups": ordered_groups,
            "optionCount": sum(len(g["choices"]) for g in ordered_groups),
        })

    scripts.sort(key=lambda x: (x["special"], x["name"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(scripts, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    gen = sum(1 for s in scripts if not s["special"])
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(scripts)} scripts ({gen} open generators)")
    for s in scripts:
        flag = " (special)" if s["special"] else ""
        print(f"  · {s['name']:22} {s['optionCount']:2} options{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
