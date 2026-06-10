#!/usr/bin/env python3
"""
Build src/data/culture.json from culture.xml + development.xml.

culture.xml — the four city culture levels (Weak → Developing → Strong →
Legendary): threshold to advance, VP per city, governor XP/turn, capture and
assimilation modifiers, and the per-Pop citizen consumption EffectCity.

development.xml — NOT city development: it's the "Development" game-setup
option (advanced start). Each level sets how many cities / how much capital
population / how many techs existing (AI) nations start with, plus how many
turns the AI holds off on wonders and religions.

Cross-references ("gates"): anything elsewhere in the XML that requires a
culture level —
  * improvement.xml  CulturePrereq  → wonders (bWonder) + urban buildings
  * unit.xml         CulturePrereq / CultureObsolete → culture-tier units
  * project.xml      RequiresCulture (city must be EXACTLY that level — the
                     tiered repeatables: Council I..IV etc., per City.cs 9967)
                     and MinimumCulture (city must be AT LEAST that level,
                     per City.cs 10061)
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import load_xml_indexes, render_effect_city  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "culture.json"

# Game text embeds icon(TOKEN) markers that _strip_link_templates doesn't
# cover (e.g. "icon(RELIGION_JUDAISM)Jewish Cathedral").
_ICON_RE = re.compile(r"icon\([A-Z_0-9]+\)")

CULTURE_ORDER = ["CULTURE_WEAK", "CULTURE_DEVELOPING", "CULTURE_STRONG", "CULTURE_LEGENDARY"]


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def clean(s: str) -> str:
    return _ICON_RE.sub("", s).strip()


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text = indexes["__text__"]  # merged en-US text across all text-*.xml

    def name_of(entry: ET.Element, fallback_prefix: str) -> str:
        key = entry.findtext("Name") or ""
        nm = clean(text.get(key, ""))
        if nm:
            return nm
        zt = entry.findtext("zType") or ""
        return zt.replace(fallback_prefix, "").replace("_", " ").title()

    # ── Gates: improvements (wonders + urban buildings) ────────────────────
    gates: dict[str, dict[str, list]] = {
        c: {"wonders": [], "buildings": [], "units": [], "projectsExact": [], "projectsMin": []}
        for c in CULTURE_ORDER
    }

    for e in parse("improvement.xml").findall("Entry"):
        cp = (e.findtext("CulturePrereq") or "").strip()
        if cp not in gates:
            continue
        item = {
            "id": e.findtext("zType") or "",
            "name": name_of(e, "IMPROVEMENT_"),
        }
        if (e.findtext("bWonder") or "0") == "1":
            gates[cp]["wonders"].append(item)
        else:
            cls = (e.findtext("Class") or "").replace("IMPROVEMENTCLASS_", "")
            item["class"] = cls.replace("_", " ").title()
            gates[cp]["buildings"].append(item)

    # ── Gates: units (culture-tier upgrades) ────────────────────────────────
    culture_label = {
        c: clean(text.get(f"TEXT_{c}", c.replace("CULTURE_", "").title()))
        for c in CULTURE_ORDER
    }
    for e in parse("unit.xml").findall("Entry"):
        cp = (e.findtext("CulturePrereq") or "").strip()
        if cp not in gates:
            continue
        obs = (e.findtext("CultureObsolete") or "").strip()
        gates[cp]["units"].append({
            "id": e.findtext("zType") or "",
            "name": name_of(e, "UNIT_"),
            "obsoleteAt": culture_label.get(obs, "") if obs in culture_label else "",
        })

    # ── Gates: projects ─────────────────────────────────────────────────────
    # RequiresCulture → city must be exactly that level (City.cs canDoProject).
    # MinimumCulture  → city must be at least that level.
    project_name: dict[str, str] = {}
    for e in parse("project.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        project_name[zt] = name_of(e, "PROJECT_")
        rc = (e.findtext("RequiresCulture") or "").strip()
        mc = (e.findtext("MinimumCulture") or "").strip()
        if rc in gates:
            gates[rc]["projectsExact"].append({"id": zt, "name": project_name[zt]})
        if mc in gates:
            gates[mc]["projectsMin"].append({"id": zt, "name": project_name[zt]})

    for g in gates.values():
        for k in g:
            g[k].sort(key=lambda x: x["name"])

    # ── Culture levels ──────────────────────────────────────────────────────
    effect_city_idx = indexes.get("effectCity.xml", {})
    levels: list[dict] = []
    for e in parse("culture.xml").findall("Entry"):
        zt = e.findtext("zType") or ""
        if zt not in CULTURE_ORDER:
            continue

        def num(tag: str) -> int:
            return int(e.findtext(tag) or "0")

        ec_id = (e.findtext("EffectCity") or "").strip()
        ec_entry = effect_city_idx.get(ec_id)
        # Citizen consumption lives on aiYieldRatePopulation → "-1 Food/Pop" etc.
        consumption = render_effect_city(ec_entry, per_city=False, indexes=indexes) if ec_entry is not None else []

        dp = (e.findtext("DefaultProject") or "").strip()
        levels.append({
            "id": zt,
            "slug": zt.replace("CULTURE_", "").lower(),
            "name": culture_label[zt],
            "order": CULTURE_ORDER.index(zt),
            "threshold": num("iThreshold"),
            "vp": num("iVP"),
            "governorXp": num("iXP"),
            "extraCaptureTurns": num("iExtraCaptureTurns"),
            "extraAssimilateTurns": num("iExtraAssimilateTurns"),
            "assimilationRate": num("iAssimilationRate"),
            "consumption": consumption,
            "defaultProject": {"id": dp, "name": project_name.get(dp, "")} if dp else None,
            "gates": gates[zt],
        })
    levels.sort(key=lambda l: l["order"])

    # ── Development levels (game-setup advanced start) ─────────────────────
    dev_levels: list[dict] = []
    # The named tiers share one template: "Existing Nations start with an
    # average of {0_num} Cities and {1_num} Technologies."
    dev_help_tpl = clean(text.get("TEXT_DEVELOPMENT_HELP", ""))
    for i, e in enumerate(parse("development.xml").findall("Entry")):
        zt = e.findtext("zType") or ""
        if not zt:
            continue
        help_txt = clean(text.get(f"{(e.findtext('Name') or '')}_HELP", ""))
        if not help_txt and (e.findtext("iAvgCities") or "") and dev_help_tpl:
            help_txt = (dev_help_tpl
                        .replace("{0_num}", e.findtext("iAvgCities") or "")
                        .replace("{1_num}", e.findtext("iTechs") or ""))
        dev_levels.append({
            "id": zt,
            "slug": zt.replace("DEVELOPMENT_", "").lower(),
            "name": clean(text.get(e.findtext("Name") or "", zt.replace("DEVELOPMENT_", "").title())),
            "help": help_txt,
            "order": i,
            "avgCities": int(e.findtext("iAvgCities") or "0"),
            "capitalPopulation": int(e.findtext("iCapitalPopulation") or "0"),
            "techs": int(e.findtext("iTechs") or "0"),
            "noWonderTurns": int(e.findtext("iNoWonderTurns") or "0"),
            "noReligionTurns": int(e.findtext("iNoReligionTurns") or "0"),
            "playerOnly": (e.findtext("bPlayerOnly") or "0") == "1",
        })

    # ── Globals that interact with culture levels ───────────────────────────
    globals_int = {
        (e.findtext("zType") or ""): int(e.findtext("iValue") or "0")
        for e in parse("globalsInt.xml").findall("Entry")
        if e.findtext("zType")
    }
    payload = {
        "cultureLevels": levels,
        "developmentLevels": dev_levels,
        "globals": {
            "baseAssimilateTurns": globals_int.get("CITY_BASE_ASSIMILATE_TURNS", 0),
            "assimilateYieldModifier": globals_int.get("CITY_ASSIMILATE_YIELD_MODIFIER", 0),
            "baseCaptureTurns": globals_int.get("CITY_BASE_CAPTURE_TURNS", 0),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    n_gates = sum(len(v) for lv in levels for v in lv["gates"].values())
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(levels)} culture levels, "
          f"{len(dev_levels)} development levels, {n_gates} culture-gated entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
