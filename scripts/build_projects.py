#!/usr/bin/env python3
"""
Build src/data/projects.json from project.xml + project-event*.xml.

Each project row carries:
  - id, slug, name, sortName, icon
  - source     (DLC / event-pack label; "Base game" otherwise)
  - eventOnly  (bHidden=1 — granted by events/missions, never in the build menu;
                shown with a badge on the page, not dropped)
  - flags      (repeat, unique, maxCount, noHurry, captureDestroy)
  - cost       (list of {yield, value}: ProductionType+iCost first, then
                aiYieldCost pairs — build costs are already user-facing scale)
  - prereqs    (structured: tech / project / culture / city / player /
                capital / option / flag — tech keeps the TECH_* id so the
                page can render a <Term>)
  - effects    (humanized one-liners via humanize.py: EffectCity,
                EffectCityExtra, EffectPlayer, Bonus, aiYieldModifier)

Run after `make sync` or whenever XML changes.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_city, render_effect_player, render_bonus,
    condition_name, yield_name, _lookup_name,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "projects.json"
ICON_DIRS = {
    # zIcon prefix → (strip, public subdir)
    "PROJECT_": ROOT / "public" / "img" / "icons" / "projects",
    "RESOURCE_": ROOT / "public" / "img" / "icons" / "resources",
    "RELIGION_": ROOT / "public" / "img" / "icons" / "religions",
}

# Base file first; DLC/event variants after (first occurrence of a zType wins).
PROJECT_FILES = [
    "project.xml",
    "project-event.xml",
    "project-event-eoti.xml",
    "project-event-sap.xml",
    "project-event-wd.xml",
    "project-event-wog.xml",
]

# GameContentRequired token → DLC / content-pack label. Mirrors
# build_events.py's DLC_LABELS; CALAMITIES confirmed as "Wrath of Gods"
# via TEXT_ADDITIONAL_CONTENT_DLC_CALAMITIES in text-misc.xml.
DLC_LABELS = {
    "EVENTPACK_RELIGION": "Religion event pack",
    "EVENTPACK_SCANDAL": "Behind the Throne",
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus",
    "WONDERS_DYNASTIES": "Wonders & Dynasties",
    "AKSUM": "Sacred & the Profane (Aksum)",
    "CALAMITIES": "Wrath of Gods",
}

CULTURE_LABELS = {
    "CULTURE_WEAK": "Weak Culture",
    "CULTURE_DEVELOPING": "Developing Culture",
    "CULTURE_STRONG": "Strong Culture",
    "CULTURE_LEGENDARY": "Legendary Culture",
}


def nice_token(token: str) -> str:
    """RELIGION_BUDDHISM → Buddhism, FAMILY_PANDYA → Pandya."""
    return (token.split("_", 1)[-1] if "_" in token else token).replace("_", " ").title()


def humanize_project_name(zt: str) -> str:
    return zt.replace("PROJECT_", "").replace("_", " ").title()


def resolve_icon(zicon: str) -> str:
    """Sprite path for a project's zIcon, '' if none was extracted."""
    for prefix, d in ICON_DIRS.items():
        if zicon.startswith(prefix):
            slug = zicon[len(prefix):].lower()
            if (d / f"{slug}.png").exists():
                return f"img/icons/{d.name}/{slug}.png"
    return ""


def bonus_supplement(b: ET.Element, indexes: dict) -> list[str]:
    """Bonus payload tags render_bonus() doesn't cover yet (we can't extend
    humanize.py from here without touching shared code, so supplement)."""
    out: list[str] = []
    pct = b.findtext("iHPCityPercent")
    if pct and pct != "0":
        out.append(f"+{int(pct)}% City HP")
    elif (b.findtext("iHPCity") or "0") != "0":
        out.append(f"+{int(b.findtext('iHPCity'))} City HP")
    if (b.findtext("bFoundReligionCity") or "0") == "1":
        out.append("Founds the next available World Religion here")
    rel = (b.findtext("FoundReligion") or "").strip()
    if rel:
        out.append(f"Founds {nice_token(rel)} here")
    fam = (b.findtext("ForceFamilySupremacy") or "").strip()
    if fam:
        out.append(f"Grants supremacy to the {nice_token(fam)} family")
    # Sub-bonuses applied to every city (e.g., Sangam Literature)
    for sub in b.findall("aeAllCityBonuses/zValue"):
        sb = indexes.get("bonus.xml", {}).get((sub.text or "").strip())
        if sb is not None:
            for line in render_bonus(sb, indexes) + bonus_supplement(sb, indexes):
                out.append(f"{line} in every City" if " in every City" not in line else line)
    return out


def project_bonus_lines(bonus_id: str, indexes: dict) -> list[str]:
    """Humanize a project's on-completion Bonus. A project Bonus applies to
    the city that ran it (City.cs passes pCity), so render_bonus()'s
    wonder-flavored 'in every City' phrasing is rewritten to 'in this City'."""
    b = indexes.get("bonus.xml", {}).get(bonus_id)
    if b is None:
        return []
    lines = [ln.replace(" in every City", " in this City") for ln in render_bonus(b, indexes)]
    lines += bonus_supplement(b, indexes)
    # Same convention as render_effect_player: one-time payloads carry an
    # "On completion:" prefix (and drop the leading +) so they can't be
    # mistaken for per-turn rates.
    out = []
    for ln in lines:
        if ln.startswith("Unlocks "):
            out.append(ln)
        else:
            out.append("On completion: " + ln.lstrip("+"))
    return out


def effect_city_supplement(token: str, ec: ET.Element, indexes: dict) -> list[str]:
    """EffectCity tags render_effect_city() doesn't cover yet (we supplement
    here rather than touching shared humanize.py)."""
    text: dict = indexes.get("__text__", {})
    out: list[str] = []
    # Name-only resource markers: the import projects grant the city the
    # same EffectCity the physical resource would (EFFECTCITY_RESOURCE_X).
    if token.startswith("EFFECTCITY_RESOURCE_"):
        out.append(f"Provides {nice_token(token[len('EFFECTCITY_RESOURCE_'):])} to this City")
    for pair in ec.findall("aiUnitTraitXP/Pair"):
        trait = nice_token(pair.findtext("zIndex") or "")
        v = int(pair.findtext("iValue") or "0")
        out.append(f"+{v} XP for {trait} units built here")
    for pair in ec.findall("aiUnitTrainModifier/Pair"):
        unit = nice_token(pair.findtext("zIndex") or "")
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{v:+d}% {unit} cost")
    for pair in ec.findall("aiUnitTraitTrainModifier/Pair"):
        trait = nice_token(pair.findtext("zIndex") or "")
        v = int(pair.findtext("iValue") or "0")
        out.append(f"{v:+d}% {trait} unit cost")
    for pair in ec.findall("aeTraitEffectUnit/Pair"):
        trait = nice_token(pair.findtext("zIndex") or "")
        eff = (pair.findtext("zValue") or "").strip()
        nm = text.get(f"TEXT_{eff}", nice_token(eff))
        out.append(f"{trait} units built here gain {nm}")
    for pair in ec.findall("aaiTerrainYield/Pair"):
        terrain = nice_token(pair.findtext("zIndex") or "")
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0") / 10
            if v == int(v):
                v = int(v)
            out.append(f"+{v} {y} on {terrain} tiles")
    fo = ec.findtext("iFamilyOpinion")
    if fo and fo != "0":
        out.append(f"{int(fo):+d} Family Opinion")
    unlock = (ec.findtext("EffectCityUnlock") or "").strip()
    if unlock:
        target = indexes.get("effectCity.xml", {}).get(unlock)
        nm = _lookup_name(indexes, target.findtext("Name") or "") if target is not None else ""
        out.append(f"Unlocks {nm or condition_name(unlock)}")
    return out


def effect_prereq_label(token: str, indexes: dict) -> str:
    """Readable label for an EffectCity/EffectPlayer prerequisite token.
    Pattern-match the common shapes, fall back to the effect entry's own
    Name text, then to a title-cased token."""
    # Family-class effects: every city of that class (or its seat) has them.
    if token.startswith("EFFECTCITY_FAMILYCLASS_"):
        rest = token[len("EFFECTCITY_FAMILYCLASS_"):]
        if "_SEAT" in rest:
            cls = rest.split("_SEAT")[0]
            return f"{cls.title()} family seat"
        return f"{rest.split('_')[0].title()} family city"
    # Governor-trait effects (e.g., EFFECTCITY_TRAIT_SCHOLAR_INQUIRY).
    if token.startswith("EFFECTCITY_TRAIT_"):
        trait = token[len("EFFECTCITY_TRAIT_"):].split("_")[0]
        return f"{trait.title()} Governor"
    # Religion present / dissenting in the city.
    if token.startswith("EFFECTCITY_RELIGION_"):
        return f"{nice_token(token[len('EFFECTCITY_RELIGION_'):])} in city"
    if token.startswith("EFFECTCITY_DISSENT_"):
        return f"{nice_token(token[len('EFFECTCITY_DISSENT_'):])} dissent in city"
    # Player-side: nation, dynasty, law, leader trait.
    if token.startswith("EFFECTPLAYER_NATION_"):
        return token[len("EFFECTPLAYER_NATION_"):].split("_")[0].title()
    if token.startswith("EFFECTPLAYER_DYNASTY_"):
        return f"{nice_token(token[len('EFFECTPLAYER_DYNASTY_'):])} dynasty"
    if token.startswith("EFFECTPLAYER_LAW_"):
        # Longest LAW_* prefix that is a real law (LAW_TRADE_LEAGUE_CONVOY →
        # Trade League law; the trailing segment is the unlock channel).
        parts = token[len("EFFECTPLAYER_LAW_"):].split("_")
        laws = indexes.get("law.xml", {})
        for i in range(len(parts), 0, -1):
            law_id = "LAW_" + "_".join(parts[:i])
            entry = laws.get(law_id)
            if entry is not None:
                nm = _lookup_name(indexes, entry.findtext("Name") or "")
                return f"{nm or nice_token(law_id)} law"
    if token.startswith("EFFECTPLAYER_TRAIT_"):
        parts = token[len("EFFECTPLAYER_TRAIT_"):].split("_")
        traits = indexes.get("trait.xml", {})
        for i in range(len(parts), 0, -1):
            trait_id = "TRAIT_" + "_".join(parts[:i])
            entry = traits.get(trait_id)
            if entry is not None:
                nm = _lookup_name(indexes, entry.findtext("Name") or "")
                return f"{nm or nice_token(trait_id)} Leader"
    for fname in ("effectCity.xml", "effectPlayer.xml"):
        entry = indexes.get(fname, {}).get(token)
        if entry is not None:
            nm = _lookup_name(indexes, entry.findtext("Name") or "")
            if nm:
                return nm
    return condition_name(token)


def build_prereqs(e: ET.Element, indexes: dict, text: dict, proj_names: dict) -> list[dict]:
    out: list[dict] = []
    tech = (e.findtext("TechPrereq") or "").strip()
    if tech:
        out.append({"kind": "tech", "id": tech,
                    "label": text.get(f"TEXT_{tech}", nice_token(tech))})
    proj = (e.findtext("ProjectPrereq") or "").strip()
    if proj:
        out.append({"kind": "project", "label": proj_names.get(proj, nice_token(proj))})
    for tag in ("MinimumCulture", "RequiresCulture"):
        cul = (e.findtext(tag) or "").strip()
        if cul:
            out.append({"kind": "culture", "label": CULTURE_LABELS.get(cul, nice_token(cul))})
    ecp = (e.findtext("EffectCityPrereq") or "").strip()
    if ecp:
        out.append({"kind": "city", "label": effect_prereq_label(ecp, indexes)})
    epp = (e.findtext("EffectPlayerPrereq") or "").strip()
    if epp:
        out.append({"kind": "player", "label": effect_prereq_label(epp, indexes)})
    cap = (e.findtext("CapitalEffectPlayerPrereq") or "").strip()
    if cap:
        label = effect_prereq_label(cap, indexes)
        if "capital" not in label.lower():
            label = f"{label} (Capital)"
        out.append({"kind": "capital", "label": label})
    opt = (e.findtext("GameOptionPrereq") or "").strip()
    if opt:
        out.append({"kind": "option",
                    "label": f"Game option: {nice_token(opt.replace('GAMEOPTION_', ''))}"})
    for tag, label in (("bRequiresGovernor", "Governor"),
                       ("bRequiresDamage", "Damaged city"),
                       ("bRequiresRiver", "River"),
                       ("bRequiresCoast", "Coast"),
                       ("bRequiresFamilySeat", "Family seat")):
        if (e.findtext(tag) or "0") == "1":
            out.append({"kind": "flag", "label": label})
    return out


def build_cost(e: ET.Element) -> list[dict]:
    """ProductionType + iCost (the yield the city produces it with), then
    aiYieldCost pairs (up-front payment). Already user-facing scale."""
    out: list[dict] = []
    prod = (e.findtext("ProductionType") or "").strip()
    cost = int(e.findtext("iCost") or "0")
    if prod and cost > 0:
        out.append({"yield": prod.replace("YIELD_", "").lower(), "value": cost})
    for pair in e.findall("aiYieldCost/Pair"):
        y = (pair.findtext("zIndex") or "").replace("YIELD_", "").lower()
        v = int(pair.findtext("iValue") or "0")
        if y and v:
            out.append({"yield": y, "value": v})
    return out


def build_effects(e: ET.Element, indexes: dict) -> list[str]:
    lines: list[str] = []
    for tag in ("EffectCity", "EffectCityExtra"):
        ec_id = (e.findtext(tag) or "").strip()
        if ec_id:
            ec = indexes.get("effectCity.xml", {}).get(ec_id)
            if ec is not None:
                lines.extend(render_effect_city(ec, per_city=False, indexes=indexes))
                lines.extend(effect_city_supplement(ec_id, ec, indexes))
    ep_id = (e.findtext("EffectPlayer") or "").strip()
    if ep_id:
        lines.extend(render_effect_player(ep_id, indexes))
    b_id = (e.findtext("Bonus") or "").strip()
    if b_id:
        lines.extend(project_bonus_lines(b_id, indexes))
    # aiYieldModifier: city yield modifier while this project is the current
    # build (City.getBuildYieldModifier) — e.g., Council I: +40% Civics.
    for pair in e.findall("aiYieldModifier/Pair"):
        y = yield_name(pair.findtext("zIndex"))
        v = int(pair.findtext("iValue") or "0")
        if v:
            lines.append(f"+{v}% {y} while in production")
    # Deduplicate, preserving order
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        if ln and ln not in seen:
            seen.add(ln)
            out.append(ln)
    return out


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text: dict[str, str] = indexes["__text__"]  # type: ignore[assignment]

    # First pass: zType → display name (for ProjectPrereq labels), with
    # first-file-wins dedup across base + event files.
    entries: dict[str, ET.Element] = {}
    for fn in PROJECT_FILES:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            zt = (e.findtext("zType") or "").strip()
            if zt and zt not in entries:
                entries[zt] = e
    proj_names = {
        zt: text.get(e.findtext("Name") or "", humanize_project_name(zt))
        for zt, e in entries.items()
    }

    projects: list[dict] = []
    for zt, e in entries.items():
        name = proj_names[zt]
        max_count = int(e.findtext("iMaxCount") or "0")
        gcr = (e.findtext("GameContentRequired") or "").strip()
        projects.append({
            "id": zt,
            "slug": zt.replace("PROJECT_", "").lower(),
            "name": name,
            "sortName": name,
            "icon": resolve_icon((e.findtext("zIcon") or "").strip()),
            "source": DLC_LABELS.get(gcr, nice_token(gcr)) if gcr else "Base game",
            "dlc": bool(gcr),
            "eventOnly": (e.findtext("bHidden") or "0") == "1",
            "repeat": (e.findtext("bRepeat") or "0") == "1",
            "unique": (e.findtext("bUnique") or "0") == "1",
            "maxCount": max_count,
            "noHurry": (e.findtext("bNoHurry") or "0") == "1",
            "captureDestroy": (e.findtext("bCaptureDestroy") or "0") == "1",
            "cost": build_cost(e),
            "prereqs": build_prereqs(e, indexes, text, proj_names),
            "effects": build_effects(e, indexes),
        })

    # Buildable first, then event-only; alphabetical within each group.
    projects.sort(key=lambda p: (p["eventOnly"], p["sortName"].lower(), p["id"]))

    OUT.write_text(json.dumps(projects, sort_keys=True, indent=2) + "\n")
    buildable = sum(1 for p in projects if not p["eventOnly"])
    no_fx = [p["id"] for p in projects if not p["effects"]]
    print(f"Wrote {len(projects)} projects ({buildable} buildable, "
          f"{len(projects) - buildable} event-only) → {OUT.relative_to(ROOT)}")
    if no_fx:
        print(f"  note: {len(no_fx)} projects render no effect lines: "
              + ", ".join(no_fx[:12]) + ("…" if len(no_fx) > 12 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
