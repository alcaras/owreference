#!/usr/bin/env python3
"""
Build src/data/ambitions.json from goal.xml + victory.xml + victoryPoint.xml
+ globalsInt.xml.

Old World's Goal objects drive the Ambition system (and event/scenario
quests). Each goal is a bundle of completion thresholds — "control N cities",
"stockpile N yield", "build N of improvement X" — plus offer constraints:

  • iMinTier/iMaxTier   — which ambition slot (1st…10th) the goal may fill.
                          Source: PlayerGoal.cs · isGoalTierValid() — the
                          "tier" is countNumAmbitions()+1, i.e. how many
                          ambitions you've already completed.
  • iAmbitionClass      — dedupe bucket; the XML's own CLASS comments name
                          each bucket and we parse them out of goal.xml.
  • bVictoryEligible    — marks a National Ambition (the tier-10 capstone of
                          VICTORY_AMBITION; Player.cs · hasAmbitionVictoryEligible).
  • TechPrereq/TechObsolete, NationPrereq, aeFamilyClass, aeReligion — when
                          and to whom the goal can be offered.

There is no per-goal reward field: finishing an ambition increments
STAT_AMBITION_ACHIEVED (feeding Legitimacy via the cognomen system), counts
toward the 10 needed for VICTORY_AMBITION, and fires
EVENTTRIGGER_AMBITION_FINISHED events. The lone FinishBonus/RankedBonuses
fields are scenario-quest rewards and are surfaced as notes.

Goal yield fields are in DISPLAY units (PlayerGoal.cs divides rates by
Constants.YIELDS_MULTIPLIER before comparing) — do NOT divide by 10 here.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "ambitions.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import load_xml_indexes, _first_form  # noqa: E402


# ────────────────────────────────────────────────────────────────────────────
# Text helpers
# ────────────────────────────────────────────────────────────────────────────

_ICON_RE = re.compile(r"\{?icon\(([A-Z0-9_]+)(?:,\d+)?\)\}?")
# humanize._LINK_RE only matches [A-Z_]+ tokens — link(IMPROVEMENT_GARRISON_1,2)
# style tokens with digits survive _first_form, so catch them here too.
_LINK_DIGIT_RE = re.compile(r"\{?(?:lowercase:)?link\(([A-Z][A-Z0-9_]*)(?:,\d+)?\)\}?")
_LEFTOVER_TEMPLATE_RE = re.compile(r"\{[^}]*\}")


def _prettify(token: str, drop_prefix: bool = True) -> str:
    parts = token.split("_")
    if drop_prefix and len(parts) > 1:
        parts = parts[1:]
    return " ".join(p.title() for p in parts)


def clean_text(s: str, resolver=None) -> str:
    """Strip the game's icon(...) / digit-bearing link(...) markup
    (plain link(...) is already handled by humanize._first_form) and
    collapse whitespace. `resolver` maps a raw token to a display name."""
    fix = resolver or _prettify
    s = _LINK_DIGIT_RE.sub(lambda m: fix(m.group(1)), s)
    s = _ICON_RE.sub(lambda m: fix(m.group(1)), s)
    s = _LEFTOVER_TEMPLATE_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


class Names:
    """zType → English display name, resolved via each info XML's Name field
    against the merged text-*.xml index; falls back to a title-cased token."""

    # info file → token prefix it resolves
    FILES = [
        "law.xml", "tech.xml", "theology.xml", "religion.xml", "nation.xml",
        "improvement.xml", "improvementClass.xml", "unit.xml", "unitTrait.xml",
        "specialist.xml", "project.xml", "resource.xml", "culture.xml",
        "mission.xml", "tribe.xml", "diplomacy.xml", "gameOption.xml",
        "opinionFamily.xml", "familyClass.xml", "effectCity.xml",
        "occurrence.xml", "bonus.xml",
    ]

    # Tokens whose generic rendering reads badly — pinned phrasings.
    MANUAL = {
        "SUBJECT_CITY_POSITIVE_HAPPINESS": "Cities with positive Happiness",
        "SUBJECT_SEAT_EIGHT_ELDER_SPECIALISTS":
            "Family Seats with eight Elder Specialists",
        "SUBJECT_SEAT_FOUR_ELDER_ACOLYTES":
            "Family Seats with four Elder Acolytes",
        "EFFECTCITY_SPECIALIST_ELDER": "Elder Specialists",
    }

    def __init__(self, text_idx: dict[str, str]):
        self.text = text_idx
        self.idx: dict[str, str] = {}
        for fn in self.FILES:
            p = XML_DIR / fn
            if not p.exists():
                continue
            for e in ET.parse(p).getroot().findall("Entry"):
                z = e.findtext("zType") or ""
                if not z:
                    continue
                name = clean_text(text_idx.get(e.findtext("Name") or "", ""))
                if name:
                    self.idx[z] = name

    def get(self, token: str) -> str:
        if token in self.MANUAL:
            return self.MANUAL[token]
        if token in self.idx:
            return self.idx[token]
        # EFFECTCITY_RELIGION_X reads best as the religion's own name
        if token.startswith("EFFECTCITY_RELIGION_"):
            rel = token.replace("EFFECTCITY_", "")
            if rel in self.idx:
                return self.idx[rel] + " Cities"
        # TEXT fallback straight off the token
        t = self.text.get("TEXT_" + token)
        if t:
            return clean_text(t)
        return _prettify(token)


# ────────────────────────────────────────────────────────────────────────────
# Requirement humanizer
# ────────────────────────────────────────────────────────────────────────────

# Scalar integer fields → phrase template ({n} substituted).
SCALAR_REQS: dict[str, str] = {
    "iLegitimacy": "Reach {n} Legitimacy",
    "iCities": "Control {n} Cities",
    "iConnectedCities": "Control {n} connected Cities",
    "iWorldReligionHolyCities": "Control {n} World Religion Holy Cities",
    "iAgentNetworks": "Have {n} Agent Networks",
    "iCitizens": "Have {n} Citizens",
    "iSpecialists": "Have {n} Specialists",
    "iPopulation": "Reach {n} total Population",
    "iLuxuries": "Have {n} Luxuries",
    "iSentLuxuries": "Send {n} Luxuries to Families, Cities, Nations or Tribes",
    "iPlayerLuxuries": "Give {n} Luxuries to other Nations",
    "iTribeLuxuries": "Give {n} Luxuries to Tribes",
    "iFamilyLuxuries": "Give {n} Luxuries to Families",
    "iCityLuxuries": "Give {n} Luxuries to Cities",
    "iSaltWaterTiles": "Control {n} Coast or Ocean tiles",
    "iUrbanTiles": "Have {n} Urban tiles",
    "iUrbanImprovements": "Have {n} Urban Improvements",
    "iWonders": "Control {n} Wonders",
    "iLaws": "Have {n} Laws active",
    "iRevealLand": "Reveal {n}% of the land",
    "iRevealWater": "Reveal {n}% of the water",
    "iMilitaryUnits": "Have {n} military Units",
    "iMaxLevelUnits": "Have {n} Units at max level",
    "iGeneralCount": "Have {n} Generals",
    "iExplorerCount": "Have {n} Explorers",
    "iGovernorCount": "Have {n} Governors",
    "iAgentCount": "Have {n} Agents",
    # *Data fields count from goal activation against an event-chosen target
    "iPlayerCapturedData": "Capture {n} Cities from the target Nation",
    "iTribeClearedData": "Clear {n} sites of the target Tribe",
    "iTribeSettledData": "Settle {n} Cities on the target Tribe's former land",
    "iPlayerKilledData": "Kill {n} Units of the target Nation",
    "iTribeKilledData": "Kill {n} Units of the target Tribe",
    "iReligionSpreadData": "Spread the target Religion to {n} Cities",
}

# Boolean flag fields → phrase.
BOOL_REQS: dict[str, str] = {
    "bAllHolyCities": "Control all Holy Cities",
    "bStateReligion": "Have a State Religion",
    "bStateReligionData": "Adopt the target Religion as your State Religion",
    "bHolyCityData": "Control the Holy City of the target Religion",
    "bCouncilAllReligionData":
        "Fill all Council seats with followers of the target Religion",
    "bPlayerDead": "Eliminate the target Nation",
    "bTribeDead": "Destroy the target Tribe",
    "bCityControlled": "Control the target City",
}

# Pair-array fields → phrase template ({n}, {x} substituted per pair).
PAIR_REQS: dict[str, str] = {
    "aiDiplomacyCount": "Be at {x} with {n} other Nations",
    "aiYieldRate": "Produce {n} {x} per turn",
    "aiYieldCount": "Stockpile {n} {x}",
    "aiYieldProducedData": "Produce {n} {x} (counted after accepting)",
    "aiYieldSoldData": "Sell {n} {x} (counted after accepting)",
    "aiResourceRevealed": "Discover {n} {x}",
    "aiLuxuryCount": "Have {n} {x} connected",
    "aiPlayerLuxuryCount": "Give {n} {x} to other Nations",
    "aiTribeLuxuryCount": "Give {n} {x} to Tribes",
    "aiFamilyLuxuryCount": "Give {n} {x} to Families",
    "aiImprovementCount": "Control {n} × {x}",
    "aiCityImprovementCount": "Control {n} × {x} in one City",
    "aiImprovementClassCount": "Control {n} × {x}",
    "aiCityImprovementClassCount": "Control {n} {x} in one City",
    "aiCultureCount": "Control {n} {x} Cities",
    "aiCultureWonders": "Control {n} Wonders in {x} Cities",
    "aiSpecialistCount": "Have {n} × {x}",
    "aiCitySpecialistCount": "Have {n} × {x} in one City",
    "aiProjectCount": "Complete {n} × {x}",
    "aiCityProjectCount": "Complete {n} × {x} in one City",
    "aiEffectCityCount": "Have {n} Cities with {x}",
    "aiCityEffectCityCount": "Have {n} Cities with {x}",
    "aiCitySubjectCount": "Have {n} {x}",
    "aiUnitCount": "Have {n} × {x}",
    "aiUnitTraitCount": "Have {n} {x} Units",
    "aiUnitTraitMaxLevelCount": "Have {n} {x} Units at max level",
    "aiStatCount": "{x}: {n} (lifetime)",
    "aiStatCountData": "{x}: {n} (counted after accepting)",
    "aiMissionsCompletedData":
        "Complete {n} {x} Missions (counted after accepting)",
    "aiTribesKilledData": "Kill {n} {x} Units (counted after accepting)",
}

# Stat tokens used by goal thresholds, phrased like the F5 panel rows.
STAT_LABELS = {
    "STAT_CAPITAL_CAPTURED": "Capitals captured",
    "STAT_CARAVAN_ARRIVED": "Caravans arrived",
    "STAT_CITY_CAPTURED": "Cities captured",
    "STAT_CITY_FOUNDED": "Cities founded",
    "STAT_CITY_LOST": "Cities lost",
    "STAT_CITY_RECAPTURED": "Cities recaptured",
    "STAT_CLERGY_ADDED": "Clergy added",
    "STAT_COURTIER_ADDED": "Courtiers added",
    "STAT_CULTURE_LEVEL_INCREASED": "Culture levels gained",
    "STAT_IMPROVEMENT_PILLAGED": "Improvements pillaged",
    "STAT_IMPROVEMENT_REPAIRED": "Improvements repaired",
    "STAT_LANDMARK_DISCOVERED": "Landmarks discovered",
    "STAT_LANDMARK_NAMED": "Landmarks named",
    "STAT_MERCENARIES_HIRED": "Mercenaries hired",
    "STAT_MERCENARIES_RECRUITED": "Mercenaries recruited",
    "STAT_RELIGION_SPREAD": "Religion spreads",
    "STAT_RESOURCE_HARVESTED": "Resources harvested",
    "STAT_RUINS_EXPLORED": "Ruins explored",
    "STAT_TEAM_ALLIANCE": "National alliances",
    "STAT_TECH_DISCOVERED": "Techs discovered",
    "STAT_THEOLOGY_ESTABLISHED": "Theologies established",
    "STAT_TILES_BOUGHT": "Tiles bought",
    "STAT_TRIBE_ALLIANCE": "Tribal alliances",
    "STAT_TRIBE_CLEARED": "Tribal sites cleared",
    "STAT_TRIBE_PEACE": "Tribal peaces",
    "STAT_UNIT_MILITARY_KILLED": "Military Units killed",
    "STAT_UNIT_MILITARY_KILLED_ANY_GENERAL": "Enemy Generals killed",
    "STAT_UNIT_MILITARY_KILLED_GENERAL": "Units killed as General",
    "STAT_UNIT_PROMOTED": "Units promoted",
    "STAT_UNIT_TRAINED": "Units trained",
    "STAT_VEGETATION_REMOVED": "Vegetation cleared",
    "STAT_WORLD_RELIGION_FOUNDED": "World Religions founded",
}


def pair_items(node: ET.Element) -> list[tuple[str, int]]:
    out = []
    for p in node.findall("Pair"):
        z = p.findtext("zIndex") or ""
        v = int(p.findtext("iValue") or "0")
        if z:
            out.append((z, v))
    return out


def zvalues(node: ET.Element) -> list[str]:
    return [zv.text or "" for zv in node.findall("zValue") if zv.text]


def render_requirements(entry: ET.Element, names: Names) -> list[str]:
    """Walk the goal entry's children in XML order and humanize every
    completion-threshold field into a phrase."""
    reqs: list[str] = []
    # combined threshold fields are read out of order — grab them up front
    imp_thresh = int(entry.findtext("iImprovementClassThreshold") or "0")
    unit_thresh = int(entry.findtext("iUnitThreshold") or "0")

    for node in entry:
        tag, text = node.tag, (node.text or "").strip()

        if tag in SCALAR_REQS and text:
            reqs.append(SCALAR_REQS[tag].format(n=int(text)))
        elif tag in BOOL_REQS and text == "1":
            reqs.append(BOOL_REQS[tag])
        elif tag in PAIR_REQS:
            for z, v in pair_items(node):
                if tag in ("aiStatCount", "aiStatCountData"):
                    x = STAT_LABELS.get(z, _prettify(z))
                else:
                    x = names.get(z)
                fmt = PAIR_REQS[tag]
                if v == 1:  # "Control 1 × The Ziggurat" → "Control The Ziggurat"
                    fmt = fmt.replace("{n} × {x}", "{x}")
                reqs.append(fmt.format(n=f"{v:,}", x=x))
        elif tag == "StartLaw" and text:
            reqs.append(f"Enact {names.get(text)}")
        elif tag == "EstablishTheology" and text:
            reqs.append(f"Establish {names.get(text)}")
        elif tag == "DiplomacyAll" and text:
            reqs.append(f"Be at {names.get(text)} with every Nation")
        elif tag == "MinOpinionFamily" and text:
            reqs.append(f"Every Family at {names.get(text)} opinion or better")
        elif tag == "aeTechsAcquired":
            techs = [names.get(z) for z in zvalues(node)]
            if techs:
                reqs.append("Research " + " and ".join(techs))
        elif tag == "aeThresholdImprovementClasses" and imp_thresh:
            kinds = ", ".join(names.get(z) for z in zvalues(node))
            reqs.append(f"Control {imp_thresh} total among: {kinds}")
        elif tag == "aeThresholdUnits" and unit_thresh:
            kinds = ", ".join(names.get(z) for z in zvalues(node))
            reqs.append(f"Have {unit_thresh} Units among: {kinds}")
        elif tag == "bCharacterTarget" and text == "1":
            reqs.append("Resolve the fate of the target character (event-driven)")

    return reqs


# ────────────────────────────────────────────────────────────────────────────
# Ambition class labels — parsed from goal.xml's own CLASS comments, with
# pinned labels for the buckets the XML never annotated.
# ────────────────────────────────────────────────────────────────────────────

UNCOMMENTED_CLASS_LABELS = {
    32: "Pillaging",
    33: "Missions",
    34: "Harvesting and Clearing",
    36: "Spreading a Specific Religion",
    37: "Salt Water Tiles",
    40: "Lavish Lifestyle and Estates",
}


def load_class_labels() -> dict[int, str]:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.parse(XML_DIR / "goal.xml", parser=parser).getroot()
    labels: dict[int, str] = {}
    rx = re.compile(r"\s*CLASS\s*(\d+)\s*\.\s*(.*?)\s*$")
    for node in root:
        if node.tag is ET.Comment:
            m = rx.match(node.text or "")
            if m:
                labels[int(m.group(1))] = m.group(2)
    labels.update({k: v for k, v in UNCOMMENTED_CLASS_LABELS.items() if k not in labels})
    return labels


# ────────────────────────────────────────────────────────────────────────────
# Build
# ────────────────────────────────────────────────────────────────────────────

def load_globals_int() -> dict[str, int]:
    out: dict[str, int] = {}
    for e in ET.parse(XML_DIR / "globalsInt.xml").getroot().findall("Entry"):
        z = e.findtext("zType") or ""
        if z:
            out[z] = int(e.findtext("iValue") or "0")
    return out


def build_victories(text_idx: dict[str, str]) -> list[dict]:
    out = []
    for e in ET.parse(XML_DIR / "victory.xml").getroot().findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        raw_name = text_idx.get(e.findtext("Name") or "", "")
        # Victory names ship as "Points~a Points Victory~Points Victory" —
        # the last form is the display title. text_idx already holds only the
        # first form, so re-read the raw string from text-infos.xml.
        out.append({
            "id": z,
            "name": raw_name,
            "help": clean_text(text_idx.get(e.findtext("Help") or "", "")),
            "toggleable": e.findtext("bToggle") == "1",
            "conquest": e.findtext("bConquest") == "1",
            "ambitions": e.findtext("bAmbitions") == "1",
            "alliance": e.findtext("bAlliance") == "1",
            "mpDefaultDisabled": e.findtext("bMPDefaultDisable") == "1",
            "percentVP": int(e.findtext("iPercentVP") or "0"),
            "opponentMaxPointPercent":
                int(e.findtext("iOpponentMaxPointPercent") or "0"),
            "minTurns": int(e.findtext("iMinTurns") or "0"),
        })
    return out


def load_victory_names() -> dict[str, str]:
    """TEXT key → last ~form (display title), unstripped of links/icons."""
    out: dict[str, str] = {}
    for e in ET.parse(XML_DIR / "text-infos.xml").getroot().findall("Entry"):
        z = e.findtext("zType") or ""
        if z.startswith("TEXT_VICTORY"):
            forms = (e.findtext("en-US") or "").split("~")
            out[z] = clean_text(_first_form(forms[-1]))
    return out


def build_victory_point_options(text_idx: dict[str, str]) -> list[dict]:
    out = []
    for e in ET.parse(XML_DIR / "victoryPoint.xml").getroot().findall("Entry"):
        z = e.findtext("zType") or ""
        if not z:
            continue
        out.append({
            "id": z,
            "name": clean_text(text_idx.get(e.findtext("Name") or "", ""))
                    or _prettify(z),
            "modifier": int(e.findtext("iModifier") or "0"),
        })
    return out


def main() -> int:
    indexes = load_xml_indexes(XML_DIR)
    text_idx: dict[str, str] = indexes["__text__"]  # type: ignore[assignment]
    names = Names(text_idx)
    class_labels = load_class_labels()
    gi = load_globals_int()

    goals: list[dict] = []
    unnamed: list[str] = []
    root = ET.parse(XML_DIR / "goal.xml").getroot()

    for entry in root.findall("Entry"):
        zid = entry.findtext("zType") or ""
        if not zid:
            continue

        name = clean_text(text_idx.get(entry.findtext("Name") or "", ""),
                          resolver=names.get)
        if not name:
            unnamed.append(zid)
            name = _prettify(zid)
        short = clean_text(text_idx.get(entry.findtext("ShortName") or "", ""),
                           resolver=names.get)
        help_text = clean_text(text_idx.get(entry.findtext("HelpText") or "", ""),
                               resolver=names.get)

        cls = entry.findtext("iAmbitionClass")
        cls_num = int(cls) if cls and cls.strip() else None
        national = entry.findtext("bVictoryEligible") == "1"

        requirements = render_requirements(entry, names)

        notes: list[str] = []
        if entry.findtext("bBlockComplete") == "1":
            notes.append("Completed only via its event chain, not by thresholds")
        max_turns = int(entry.findtext("iMaxTurns") or "0")
        if max_turns:
            notes.append(f"Must be completed within {max_turns} turns")
        if entry.findtext("bRemoveYieldCountAmountsOnCompletion") == "1":
            notes.append("Stockpiled yields are consumed on completion")
        if entry.findtext("bGlobal") == "1":
            notes.append("Tracked globally (all players' progress counts)")
        if entry.findtext("bScenario") == "1":
            notes.append("Scenario goal")
        if entry.findtext("bDisabled") == "1":
            notes.append("Disabled")
        fb = entry.findtext("FinishBonus") or ""
        if fb:
            notes.append(f"On completion: {names.get(fb)}")
        if entry.find("RankedBonuses") is not None and len(entry.find("RankedBonuses")):
            notes.append("Ranked rewards by finishing order (scenario)")
        if entry.find("aiPlayerSubjectWeights") is not None:
            notes.append("Target Nation chosen by the offering event")
        bad_opts = entry.find("aeInvalidGameOptions")
        if bad_opts is not None:
            opts = ", ".join(names.get(z) for z in zvalues(bad_opts))
            if opts:
                notes.append(f"Not offered with game options: {opts}")

        fam_node = entry.find("aeFamilyClass")
        family_classes = [
            {"id": z, "name": names.get(z)}
            for z in (zvalues(fam_node) if fam_node is not None else [])
        ]
        rel_node = entry.find("aeReligion")
        religions = [
            {"id": z, "name": names.get(z)}
            for z in (zvalues(rel_node) if rel_node is not None else [])
        ]

        def ref(tag: str) -> dict | None:
            v = entry.findtext(tag) or ""
            return {"id": v, "name": names.get(v)} if v else None

        goals.append({
            "id": zid,
            "slug": zid.replace("GOAL_", "").lower().replace("_", "-"),
            "name": name,
            "shortName": short,
            "helpText": help_text,
            "ambitionClass": cls_num,
            "classLabel": class_labels.get(cls_num, "") if cls_num else "",
            "national": national,
            "minTier": int(entry.findtext("iMinTier") or "0"),
            "maxTier": int(entry.findtext("iMaxTier") or "0"),
            "weight": int(entry.findtext("iSubjectWeight") or "0"),
            "techPrereq": ref("TechPrereq"),
            "techObsolete": ref("TechObsolete"),
            "nationPrereq": ref("NationPrereq"),
            "familyClasses": family_classes,
            "religions": religions,
            "requirements": requirements,
            "notes": notes,
            "dlc": entry.findtext("GameContentRequired") or "",
            "notDlc": entry.findtext("NotGameContent") or "",
        })

    if unnamed:
        print(f"  (i) {len(unnamed)} goals with no resolvable Name text: "
              + ", ".join(unnamed[:8]) + ("…" if len(unnamed) > 8 else ""))

    # ── Grouping: National capstones, then ambition classes, then event goals
    groups: list[dict] = []
    national_goals = [g for g in goals if g["national"]]
    if national_goals:
        groups.append({
            "key": "national",
            "label": "National Ambitions",
            "blurb": "Victory-eligible capstones (bVictoryEligible). One must "
                     "be completed for an Ambitions victory; always offered as "
                     "the 10th ambition, sometimes earlier.",
            "goals": national_goals,
        })
    by_class: dict[int, list[dict]] = {}
    for g in goals:
        if g["national"] or g["ambitionClass"] is None:
            continue
        by_class.setdefault(g["ambitionClass"], []).append(g)
    for cls_num in sorted(by_class):
        glist = sorted(by_class[cls_num], key=lambda g: (g["minTier"], g["maxTier"], g["id"]))
        groups.append({
            "key": f"class-{cls_num}",
            "label": class_labels.get(cls_num, f"Class {cls_num}"),
            "blurb": "",
            "goals": glist,
        })
    event_goals = [g for g in goals
                   if not g["national"] and g["ambitionClass"] is None]
    if event_goals:
        groups.append({
            "key": "event",
            "label": "Event and Scenario Goals",
            "blurb": "Goals with no ambition class — granted by events, "
                     "scenarios and quests rather than the ambition picker.",
            "goals": event_goals,
        })

    victory_names = load_victory_names()
    victories = build_victories(text_idx)
    for v in victories:
        # swap in the display-title form ("Points Victory" not "Points")
        for e in ET.parse(XML_DIR / "victory.xml").getroot().findall("Entry"):
            if (e.findtext("zType") or "") == v["id"]:
                v["name"] = victory_names.get(e.findtext("Name") or "", v["name"])

    payload = {
        "globals": {
            "maxAmbitions": gi.get("MAX_AMBITIONS", 0),
            "ambitionDelayTurns": gi.get("AMBITION_DELAY_TURNS", 0),
            "ambitionOneCityMinTurns": gi.get("AMBITION_ONE_CITY_MIN_TURNS", 0),
            "nationalOfferThresholdPercent":
                gi.get("NATIONAL_AMBITION_OFFER_THRESHOLD_PERCENT", 0),
        },
        "groups": groups,
        "meta": {
            "ambitionGoals": sum(
                1 for g in goals if g["national"] or g["ambitionClass"] is not None),
            "eventGoals": len(event_goals),
            "nationalAmbitions": len(national_goals),
            "totalGoals": len(goals),
        },
        "victories": victories,
        "victoryPointOptions": build_victory_point_options(text_idx),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True,
                              ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(goals)} goals "
          f"({len(national_goals)} national, {len(event_goals)} event) "
          f"in {len(groups)} groups; {len(victories)} victory types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
