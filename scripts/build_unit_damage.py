#!/usr/bin/env python3
"""
Build src/data/units.json from unit.xml + effectUnit.xml + unitTrait.xml.

For each combat-relevant unit we capture stats (strength, HP, move, sight,
range, attack pattern), training cost / upkeep yields, traits, tech prereq,
and a flattened "counters" list derived from the unit's built-in EffectUnit
modifiers — anything with an aiUnitTraitModifier* or aiAttackPercent line
becomes a "+50% vs Mounted" entry.

Non-combat units (settlers, workers, scouts) are kept but flagged so the
page can group them separately.

Each unit also carries a `category` ("normal" | "unique" | "tribal"), Culture
tier (`era`/`eraOrder` for unique units), `nationLabel`, `techLabel` and a
`source` DLC label, feeding the Units and Unique Units catalog pages.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, fmt_decimal,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "units.json"


# The classes we surface as primary "unit class" labels. Same vocabulary the
# spreadsheet's rock-paper-scissors chart uses. Order matters — the first
# matching trait wins, so POLEARM is checked before INFANTRY (a Hoplite is
# tagged with both, and "Polearm" is the more useful column for combat math).
PRIMARY_TRAITS = [
    "UNITTRAIT_SIEGE",
    "UNITTRAIT_RANGED",
    "UNITTRAIT_POLEARM",
    "UNITTRAIT_MOUNTED",
    "UNITTRAIT_INFANTRY",
    "UNITTRAIT_SHIP",
    "UNITTRAIT_DISCIPLE",
    "UNITTRAIT_WORKER",
    "UNITTRAIT_HORSE",
    "UNITTRAIT_CAMEL",
    "UNITTRAIT_ELEPHANT",
]

# Skinny labels for trait references in counter strings.
TRAIT_LABEL_OVERRIDES = {
    "UNITTRAIT_INFANTRY": "Infantry",
    "UNITTRAIT_POLEARM":  "Polearm",
    "UNITTRAIT_MOUNTED":  "Mounted",
    "UNITTRAIT_MELEE":    "Melee",
    "UNITTRAIT_RANGED":   "Ranged",
    "UNITTRAIT_SIEGE":    "Siege",
    "UNITTRAIT_SHIP":     "Ship",
    "UNITTRAIT_HORSE":    "Horse",
    "UNITTRAIT_CAMEL":    "Camel",
    "UNITTRAIT_ELEPHANT": "Elephant",
    "UNITTRAIT_TRIBAL":   "Tribal",
    "UNITTRAIT_WORKER":   "Worker",
    "UNITTRAIT_DISCIPLE": "Disciple",
    "UNITTRAIT_PROMOTABLE": "Promotable",
}


# Effect-icon art lives in two extracted folders; an EffectUnit's zIconName may
# point at either (Disarm's icon is a UnitTrait sprite, most are EffectUnit
# sprites). Resolve to whichever file actually exists.
EFFECT_ICON_DIRS = ["effects", "unit_traits"]


def effect_icon_path(icon_token: str) -> str | None:
    slug = (icon_token or "").replace("EFFECTUNIT_", "").replace("UNITTRAIT_", "") \
        .replace("CONCEPT_", "").lower()
    if not slug:
        return None
    for d in EFFECT_ICON_DIRS:
        if (ROOT / "public" / "img" / "icons" / d / f"{slug}.png").exists():
            return f"{d}/{slug}"
    return None


def effect_label(eff_id: str, gendered: str | None, text: dict[str, str]) -> str:
    """Resolve an EffectUnit's display name. The game keys these a few ways
    (TEXT_EFFECTUNIT_*, the GenderedName, or a CONCEPT alias); take the first
    that resolves, else humanize the zType."""
    for cand in (eff_id,
                 eff_id.replace("EFFECTUNIT_", "TEXT_EFFECTUNIT_"),
                 gendered,
                 (gendered or "").replace("GENDERED_", "")):
        if cand and cand in text:
            return text[cand]
    return token_title(eff_id, "EFFECTUNIT_")


# Metadata + pure stat-extra fields. An EffectUnit whose ONLY payload is one of
# these isn't a player-facing "special ability" — it's a stat contribution the
# game folds straight into vision/move (HelpText.Unit.cs lists it under those
# stat lines, not as an ability). EFFECTUNIT_EXTRA_VISION is exactly this: its
# sole field is iVisionExtra, already shown in the vision column, so listing a
# "High Vision" ability chip would double-count it.
ABILITY_META_FIELDS = {
    "zType", "Name", "GenderedName", "zIconName",
    "iVisionExtra", "iMovementExtra", "iRevealExtra",
}


def is_ability_effect(e: ET.Element | None) -> bool:
    if e is None:
        return True  # unknown effect — keep it rather than silently drop
    return any(c.tag not in ABILITY_META_FIELDS for c in e)


def _sgn(v: int) -> str:
    return f"+{v}" if v > 0 else str(v)


def describe_effect(e: ET.Element | None, eu_idx: dict[str, ET.Element],
                    text: dict[str, str]) -> list[str]:
    """Human, grounded description lines for one EffectUnit — a focused port of
    HelpText.buildEffectUnitHelp (HelpText.Unit.cs) covering the fields that
    actually appear on unit abilities. Names + attack-pattern help come from the
    game's own TEXT_* strings so phrasing matches the in-game tooltip."""
    if e is None:
        return []

    def nm(tok: str | None) -> str:
        tok = tok or ""
        return text.get("TEXT_" + tok, tok.split("_", 1)[-1].replace("_", " ").title())

    def pairs(tag: str) -> list[tuple[str, int]]:
        return [(p.findtext("zIndex") or "", int(p.findtext("iValue") or "0"))
                for p in e.findall(f"{tag}/Pair")]

    lines: list[str] = []

    # Flat strength / attack / defense (mostly on inflicted effects like Disarmed)
    for tag, label in (("iStrengthModifier", "Strength"),
                       ("iAttackModifier", "Attack"),
                       ("iDefenseModifier", "Defense")):
        v = int(e.findtext(tag) or "0")
        if v:
            lines.append(f"{_sgn(v)}% {label}")

    v = int(e.findtext("iUrbanAttackModifier") or "0")
    if v:
        lines.append(f"{_sgn(v)}% Strength attacking into Urban tiles (Cities)")
    v = int(e.findtext("iAdjacentSameModifier") or "0")
    if v:
        lines.append(f"{_sgn(v)}% Strength next to another unit of the same type")
    v = int(e.findtext("iAdjacentSameAttackModifier") or "0")
    if v:
        lines.append(f"{_sgn(v)}% Attack next to another unit of the same type")

    for tag, phrase in (("aiUnitTraitModifier", "{v}% Strength vs {t}"),
                        ("aiUnitTraitModifierMelee", "{v}% Strength in melee vs {t}"),
                        ("aiUnitTraitModifierAttack", "{v}% Attack vs {t}"),
                        ("aiUnitTraitModifierDefense", "{v}% Defense vs {t}")):
        for tok, val in pairs(tag):
            lines.append(phrase.format(v=_sgn(val), t=nm(tok)))

    for tok, val in pairs("aiImprovementToModifier"):
        lines.append(f"{_sgn(val)}% Strength attacking units on a {nm(tok)}")

    # Attack patterns (Splash/Pierce/Cleave/Circle): pull the game's own help line
    pct = dict(pairs("aiAttackPercent"))
    for tok, _ in pairs("aiAttackValue"):
        help_txt = text.get("TEXT_" + tok + "_HELP", "")
        extra = f" ({_sgn(pct[tok])}% damage)" if pct.get(tok) else ""
        lines.append((help_txt or f"{nm(tok)} attack pattern") + extra)

    if (e.findtext("bRout") or "0") == "1":
        lines.append("Can force the defender to Retreat (Rout) on a strong hit")
    if (e.findtext("bPush") or "0") == "1":
        lines.append("Pushes the defender back one tile (Panic)")

    def turns(n: str | None) -> str:
        return f"{n} turn" + ("" if n == "1" else "s")

    aae = e.find("AttackApplyEffectUnitTurns")
    if aae is not None:
        tgt = eu_idx.get(aae.findtext("First") or "")
        sub = describe_effect(tgt, eu_idx, text)
        suffix = f" ({'; '.join(sub)})" if sub else ""
        lines.append(f"Attacks inflict {nm(aae.findtext('First'))} for "
                     f"{turns(aae.findtext('Second'))}{suffix}")

    sae = e.find("SelfApplyEffectUnitTurns")
    if sae is not None:
        cost = e.find("SelfApplyEffectUnitYieldCost")
        cost_s = ""
        if cost is not None and cost.find("Pair") is not None:
            cp = cost.find("Pair")
            cost_s = f" (costs {cp.findtext('Second')} {nm(cp.findtext('First'))})"
        lines.append(f"On attack, gains {nm(sae.findtext('First'))} for "
                     f"{turns(sae.findtext('Second'))}{cost_s}")

    uf = e.find("UnitTraitFormation")
    if uf is not None:
        per = int(uf.findtext("Second") or "0")
        turns = int(uf.findtext("Third") or "0")
        lines.append(f"Formation: +{per}% Defense vs {nm(uf.findtext('First'))} per turn "
                     f"held in place, up to +{per * turns}% after {turns} turns")

    ignore = ([nm(x.text) for x in e.findall("aeIgnoreHeightCost/zValue")]
              + [nm(x.text) for x in e.findall("aeIgnoreVegetationCost/zValue")])
    if ignore:
        lines.append("Ignores the extra movement cost of " + ", ".join(ignore))

    return lines


def collect_abilities(effect_ids: list[str], eu_idx: dict[str, ET.Element],
                      text: dict[str, str]) -> list[dict]:
    """A unit's aeEffectUnit entries that are genuine named abilities (Disarm,
    Rout, Testudo, …) — the signature specials. Pure stat-extra effects (e.g.
    EXTRA_VISION → just +1 vision) are excluded; their value already shows in
    the stat columns. Each ability carries grounded `lines` (for the tooltip)
    and a `slug` (for its detail page)."""
    out: list[dict] = []
    for eid in effect_ids:
        e = eu_idx.get(eid)
        if not is_ability_effect(e):
            continue
        gendered = e.findtext("GenderedName") if e is not None else None
        icon_tok = (e.findtext("zIconName") if e is not None else None) or eid
        out.append({
            "id": eid,
            "slug": eid.replace("EFFECTUNIT_", "").lower(),
            "label": effect_label(eid, gendered, text),
            "icon": effect_icon_path(icon_tok),
            "lines": describe_effect(e, eu_idx, text),
        })
    return out


def unit_effect_ids(entry: ET.Element, trait_effect: dict[str, str]) -> list[str]:
    """Every EffectUnit a freshly-built unit carries: its own aeEffectUnit plus
    one per UnitTrait (Unit.cs:5288-5296). Needed for stat aggregation —
    vision/move modifiers (SIEGE −1, ELEPHANT −1, MOUNTED +1) live on traits."""
    ids = [t.text for t in entry.findall("aeEffectUnit/zValue") if t.text]
    for t in entry.findall("aeUnitTrait/zValue"):
        ef = trait_effect.get(t.text or "")
        if ef:
            ids.append(ef)
    return ids


def effect_stat_extra(effect_ids: list[str], eu_idx: dict[str, ET.Element], field: str) -> int:
    total = 0
    for eid in effect_ids:
        e = eu_idx.get(eid)
        if e is not None:
            total += int(e.findtext(field) or "0")
    return total


# Culture-tier gating for unique units (they have no TechPrereq — a nation
# unlocks them at a Culture level instead). Steppe Rider has no CulturePrereq
# and no building gate: a true turn-one unique, surfaced as "Initial". The
# D'mt Warrior also has no CulturePrereq but DOES need a Stronghold, so it is
# gated by improvement instead (handled below) — not "from start".
ERA_BY_CULTURE = {
    "":                   {"order": 1, "label": "Initial"},
    "CULTURE_WEAK":       {"order": 1, "label": "Weak"},
    "CULTURE_DEVELOPING": {"order": 2, "label": "Developing"},
    "CULTURE_STRONG":     {"order": 3, "label": "Strong"},
    "CULTURE_LEGENDARY":  {"order": 4, "label": "Legendary"},
}

# DLC tag → short source label, mirroring build_wonders.py.
SOURCE_LABEL = {
    "":                     "Base game",
    "WONDERS_DYNASTIES":    "Wonders & Dynasties",
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus",
    "SEARCH_AND_PROGRESS":  "Search & Progress",
    "BEHIND_THE_THRONE":    "Behind the Throne",
}


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def token_title(token: str, prefix: str = "") -> str:
    """NATION_YUEZHI → Yuezhi, TECH_LAND_CONSOLIDATION → Land Consolidation."""
    if not token:
        return ""
    return token.replace(prefix, "", 1).replace("_", " ").title() if prefix else token.replace("_", " ").title()


def trait_label(t: str) -> str:
    return TRAIT_LABEL_OVERRIDES.get(t, t.replace("UNITTRAIT_", "").title())


def attack_label(t: str) -> str:
    return t.replace("ATTACK_", "").title()


def collect_counter_lines(effect_ids: list[str], eu_idx: dict[str, ET.Element]) -> list[dict]:
    """Walk the unit's EffectUnits and pull counter-style modifiers as
    structured rows: {kind, target, value}. Lets the page render either a
    chip or a row."""
    rows: list[dict] = []
    for eid in effect_ids:
        e = eu_idx.get(eid)
        if e is None:
            continue
        for tag, kind in [
            ("aiUnitTraitModifier",        "vs"),
            ("aiUnitTraitModifierMelee",   "melee vs"),
            ("aiUnitTraitModifierAttack",  "attack vs"),
            ("aiUnitTraitModifierDefense", "defense vs"),
        ]:
            for pair in e.findall(f"{tag}/Pair"):
                t = pair.findtext("zIndex") or ""
                v = int(pair.findtext("iValue") or "0")
                if v != 0:
                    rows.append({
                        "source": eid,
                        "kind": kind,
                        "target": trait_label(t),
                        "targetId": t,
                        "value": v,
                    })
        # Attack pattern boost (Pierce I etc.) — informational, not a counter
        for pair in e.findall("aiAttackPercent/Pair"):
            a = pair.findtext("zIndex") or ""
            v = int(pair.findtext("iValue") or "0")
            if v != 0:
                rows.append({
                    "source": eid,
                    "kind": "attack",
                    "target": attack_label(a),
                    "targetId": a,
                    "value": v,
                })
    return rows


def is_combat_unit(entry: ET.Element) -> bool:
    """A unit is 'combat' if it has Strength > 0 and bRegular=1 (regular army),
    OR is a barbarian raider / tribe unit with strength. Settlers/workers
    have iStrength but aren't combat-trained."""
    strength = int(entry.findtext("iStrength") or "0")
    if strength <= 0:
        return False
    if (entry.findtext("bFound") or "0") == "1":  # settler
        return False
    if (entry.findtext("bBuild") or "0") == "1":  # worker
        return False
    if (entry.findtext("bCaravan") or "0") == "1":
        return False
    if (entry.findtext("bGeneral") or "0") == "1" and (entry.findtext("bRegular") or "0") != "1":
        return False
    return True


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text = indexes.get("__text__", {})
    eu_idx = indexes.get("effectUnit.xml", {})

    # Improvement display names + Culture gate, for units gated behind a city
    # building (ImprovementPrereq) or obsoleted by one (ImprovementObsolete):
    # GARRISON_2 → Stronghold (needs Developing), GARRISON_3 → Citadel (needs
    # Strong). The Culture gate lets a building-gated unit inherit its tier.
    imp_name: dict[str, str] = {}
    imp_culture: dict[str, str] = {}
    for ie in parse("improvement.xml").findall("Entry"):
        iz = ie.findtext("zType") or ""
        if iz:
            imp_name[iz] = text.get(ie.findtext("Name") or "", token_title(iz, "IMPROVEMENT_"))
            imp_culture[iz] = ie.findtext("CulturePrereq") or ""

    # Each UnitTrait contributes one EffectUnit to the units that carry it
    # (Unit.cs:5293-5296) — this is where SIEGE's −1 vision, ELEPHANT's −1 and
    # MOUNTED's +1 actually come from. Needed for accurate vision/movement.
    trait_effect: dict[str, str] = {}
    for te in parse("unitTrait.xml").findall("Entry"):
        tz = te.findtext("zType") or ""
        ef = te.findtext("EffectUnit") or ""
        if tz and ef:
            trait_effect[tz] = ef
    extra_vis = 0  # Globals.EXTRA_VISIBILITY, added to every unit's vision
    for ge in parse("globalsInt.xml").findall("Entry"):
        if (ge.findtext("zType") or "") == "EXTRA_VISIBILITY":
            extra_vis = int(ge.findtext("iValue") or "0")

    # Cumulative science to unlock a tech from a blank slate (no starting
    # techs): its own iCost plus every transitive abTechPrereq, each tech
    # counted once. Drives the counters page's "hide costlier tech" filter.
    # Pairs with bValue=1 are the real tree edges (bonus cards excluded by
    # never being a unit's TechPrereq).
    tech_cost: dict[str, int] = {}
    tech_prereqs: dict[str, list[str]] = {}
    for te in parse("tech.xml").findall("Entry"):
        tz = te.findtext("zType") or ""
        if not tz:
            continue
        tech_cost[tz] = int(te.findtext("iCost") or "0")
        tech_prereqs[tz] = [
            (p.findtext("zIndex") or "").strip()
            for p in te.findall("abTechPrereq/Pair")
            if (p.findtext("bValue") or "1") == "1"
        ]

    _closures: dict[str, frozenset] = {}

    def closure_set(tech: str) -> frozenset:
        if tech in _closures:
            return _closures[tech]
        seen: set[str] = set()
        stack = [tech]
        while stack:
            t = stack.pop()
            if not t or t in seen or t not in tech_cost:
                continue
            seen.add(t)
            stack.extend(tech_prereqs.get(t, []))
        fs = frozenset(seen)
        _closures[tech] = fs
        return fs

    def closure_cost(tech: str) -> int:
        return sum(tech_cost[t] for t in closure_set(tech))

    # Unique units are culture-gated, not tech-gated, so a raw closure would
    # call them free. Competitive heuristic (per the user): a Developing UU
    # (STR 6) needs ~4 laws adopted, a Strong UU (STR 8) ~7 — so their
    # effective techCost is the MINIMUM cumulative science that unlocks that
    # many law classes (each lawClass = one adoptable law; classes without a
    # TechPrereq, i.e. succession, count as free). Minimised by brute force
    # over closure unions — shared prereqs make greedy non-optimal.
    law_techs: list[str] = []
    free_laws = 0
    for le in parse("lawClass.xml").findall("Entry"):
        if not (le.findtext("zType") or ""):
            continue
        tp = le.findtext("TechPrereq") or ""
        if tp:
            law_techs.append(tp)
        else:
            free_laws += 1

    def min_science_for_laws(k: int) -> int:
        need = max(0, k - free_laws)
        if need == 0:
            return 0
        sets = [closure_set(t) for t in law_techs]
        best: int | None = None
        for combo in combinations(sets, need):
            union: set[str] = set().union(*combo)
            c = sum(tech_cost[t] for t in union)
            if best is None or c < best:
                best = c
        return best or 0

    LAWS_BY_CULTURE = {"CULTURE_DEVELOPING": 4, "CULTURE_STRONG": 7}
    laws_cost = {c: min_science_for_laws(k) for c, k in LAWS_BY_CULTURE.items()}

    units: list[dict] = []
    for entry in parse("unit.xml").findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt or not zt.startswith("UNIT_"):
            continue

        name_key = entry.findtext("Name") or ""
        zt_name = zt.replace("UNIT_", "").replace("_", " ").title()
        name = text.get(name_key, zt_name)
        # Religion disciples carry a parameterized name ("{UNIT-RELIGION,1}
        # Disciple") that the game fills in per religion at runtime. The zType
        # already names the religion (UNIT_BUDDHISM_DISCIPLE), so fall back to
        # it whenever the text still has an unresolved {…} template.
        if "{" in name:
            name = zt_name

        traits = [t.text for t in entry.findall("aeUnitTrait/zValue") if t.text]
        # Primary class follows PRIMARY_TRAITS priority — pick the *highest-
        # priority* trait this unit carries, not the first one listed on the unit.
        traits_set = set(traits)
        primary = next((t for t in PRIMARY_TRAITS if t in traits_set), traits[0] if traits else "")

        effect_ids = [t.text for t in entry.findall("aeEffectUnit/zValue") if t.text]

        # Costs and consumption
        costs: list[dict] = []
        for pair in entry.findall("aiYieldCost/Pair"):
            yk = (pair.findtext("zIndex") or "").replace("YIELD_", "").lower()
            iv = int(pair.findtext("iValue") or "0")
            if yk and iv:
                costs.append({"yield": yk, "value": iv})

        consumption: list[dict] = []
        for pair in entry.findall("aiYieldConsumption/Pair"):
            yk = (pair.findtext("zIndex") or "").replace("YIELD_", "").lower()
            iv = int(pair.findtext("iValue") or "0")
            if yk and iv:
                consumption.append({"yield": yk, "value": iv})

        upgrade_to = [t.text for t in entry.findall("aeUpgradeUnit/zValue") if t.text]
        obsolete_tech = [t.text for t in entry.findall("aeObsoleteTech/zValue") if t.text]

        # XML-derived counter modifiers (kept for other pages' damage math) +
        # named special abilities. Each ability carries its own grounded
        # description `lines`, so abilities and counters never render doubled.
        # Counters must include trait-attached effects (Unit.cs getEffectUnits
        # adds one EffectUnit per UnitTrait): UNITTRAIT_MOUNTED carries
        # +50% melee vs Siege and UNITTRAIT_CAMEL +50% vs Horse — both were
        # invisible when this walked only the unit's own aeEffectUnit.
        counters = collect_counter_lines(unit_effect_ids(entry, trait_effect), eu_idx)
        abilities = collect_abilities(effect_ids, eu_idx, text)

        # Effective vision / movement: base + every EffectUnit's extra (own +
        # trait-derived). SIEGE −1 vision is why a Battering Ram sees 3, not 4.
        all_effect_ids = unit_effect_ids(entry, trait_effect)
        eff_vision = (int(entry.findtext("iVision") or "0") + extra_vis
                      + effect_stat_extra(all_effect_ids, eu_idx, "iVisionExtra"))
        eff_movement = (int(entry.findtext("iMovement") or "0")
                        + effect_stat_extra(all_effect_ids, eu_idx, "iMovementExtra"))

        imp_prereq = entry.findtext("ImprovementPrereq") or ""
        imp_obsolete = entry.findtext("ImprovementObsolete") or ""

        # Classification axis used by the Units / Unique Units pages:
        #   unique  → has a NationPrereq (nation-only build; wins even if the
        #             unit also carries UNITTRAIT_TRIBAL, e.g. Yuezhi Steppe Rider)
        #   tribal  → carries UNITTRAIT_TRIBAL and no nation gate (barbarian/tribe)
        #   normal  → everything else (the roster any nation can build)
        nation_prereq = entry.findtext("NationPrereq") or ""
        is_tribal = "UNITTRAIT_TRIBAL" in traits_set
        if nation_prereq:
            category = "unique"
        elif is_tribal:
            category = "tribal"
        else:
            category = "normal"

        # Unique units gate on Culture tier, not tech (TechPrereq is empty).
        # A unit with no CulturePrereq but an ImprovementPrereq inherits the
        # building's own Culture gate (a Stronghold needs Developing, a Citadel
        # needs Strong) — so Aksum's D'mt Warrior reads "Developing", in step
        # with the other base uniques, rather than "from start". Only Steppe
        # Rider (no culture and no building) stays "Initial".
        culture = entry.findtext("CulturePrereq") or ""
        if nation_prereq and not culture and imp_prereq:
            culture = imp_culture.get(imp_prereq, culture)
        era = ERA_BY_CULTURE.get(culture, {"order": 0, "label": token_title(culture, "CULTURE_")})
        dlc = entry.findtext("GameContentRequired") or ""

        units.append({
            "id": zt,
            "slug": zt.replace("UNIT_", "").lower(),
            "name": name,
            "isCombat": is_combat_unit(entry),
            # Military vs civilian split for the page tabs. UnitCycle is the
            # game's own classification: every fighting unit is UNITCYCLE_MILITARY_*
            # (incl. Militia/Conscript), while support units carry their own cycle
            # (SCOUT, DISCIPLE, WORKER, FOUND, CARAVAN). This is cleaner than
            # isCombat, which counts Scouts/Disciples as combat because they have
            # a Strength stat — they're civilian for roster purposes.
            "isMilitary": (entry.findtext("UnitCycle") or "").startswith("UNITCYCLE_MILITARY"),
            "category": category,
            "isTribal": is_tribal,
            "culturePrereq": culture,
            "era": era["label"] if nation_prereq else "",
            "eraOrder": era["order"] if nation_prereq else 0,
            "nationLabel": token_title(nation_prereq, "NATION_"),
            "improvementPrereq": imp_prereq,
            "improvementPrereqLabel": imp_name.get(imp_prereq, "") if imp_prereq else "",
            "improvementObsolete": imp_obsolete,
            "improvementObsoleteLabel": imp_name.get(imp_obsolete, "") if imp_obsolete else "",
            "techLabel": token_title(entry.findtext("TechPrereq") or "", "TECH_"),
            "source": SOURCE_LABEL.get(dlc, token_title(dlc) if dlc else "Base game"),
            "iconSlug": (entry.findtext("zIconName") or zt).replace("UNIT_", "").lower(),
            "techPrereq": entry.findtext("TechPrereq") or "",
            # Cumulative science to field the unit from a blank slate: full
            # tech-prereq closure; for culture-gated uniques, the min science
            # to unlock enough laws for their tier. 0 for Militia/tribals.
            "techCost": (laws_cost.get(culture, 0) if nation_prereq
                         else closure_cost(entry.findtext("TechPrereq") or "")),
            "nationPrereq": entry.findtext("NationPrereq") or "",
            "primaryTrait": primary,
            "primaryLabel": trait_label(primary) if primary else "",
            "traits": [trait_label(t) for t in traits],
            "traitIds": traits,
            "strength":  int(entry.findtext("iStrength")  or "0"),
            "hp":        int(entry.findtext("iHPMax")     or "0"),
            "movement":  eff_movement,
            "vision":    eff_vision,
            "rangeMin":  int(entry.findtext("iRangeMin")  or "0"),
            "rangeMax":  int(entry.findtext("iRangeMax")  or "0"),
            "fatigue":   int(entry.findtext("iFatigue")   or "0"),
            "production":   int(entry.findtext("iProduction")   or "0"),
            "upgradeCost":  int(entry.findtext("iUpgradeCost")  or "0"),
            "trainingYield": (entry.findtext("ProductionType") or "").replace("YIELD_", "").lower(),
            "isMelee":     (entry.findtext("bMelee")    or "0") == "1",
            "isWater":     (entry.findtext("bWater")    or "0") == "1",
            "isRangeFlat": (entry.findtext("bRangeFlat") or "0") == "1",
            "costs": costs,
            "consumption": consumption,
            "upgradeTo": upgrade_to,
            "obsoleteTech": obsolete_tech,
            "effectUnits": effect_ids,
            "counters": counters,
            "abilities": abilities,
            "gameContent": entry.findtext("GameContentRequired") or "",
        })

    units.sort(key=lambda u: (not u["isCombat"], u["primaryLabel"] or "z", u["strength"], u["slug"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(units, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(units)} units")
    return 0


if __name__ == "__main__":
    sys.exit(main())
