#!/usr/bin/env python3
"""
Build src/data/autobuild.json — everything the Grand Vizier and Autonomous Rule
pages need about the game's *forced city autobuild* mechanism.

Both features are the same engine flag: an EffectCity with <bAutoBuild>. The
game has exactly two carriers (grep bAutoBuild in effectCity.xml):

  • EFFECTCITY_SHARED_POWER            — reached via COUNCIL_GRAND_VIZIER →
    EFFECTPLAYER_SHARED_POWER_VIZIER → <NoGovernorEffectCity>; applied to every
    city with no governor (City.cs resetPlayerEffectCity / Player.cs changeEffectPlayerCount).
    Also names the Vizier <DefaultGovernor> (acting governor).
  • EFFECTCITY_PROJECT_AUTONOMOUS_RULE — carried by the hidden, event-granted
    PROJECT_AUTONOMOUS_RULE (project-event.xml). Adds <bNoBuildUnits>.

The picker itself lives in PlayerAI.cs (doAutomatedCityBuilds → doCityBuildPlanning
→ getBestBuild → isBuildProjectValid / isBuildUnitValid / getValidBuildSpecialist,
valued by getProjectBuildValue / getUnitBuildValue / getSpecialistBuildValue through
getBuildValue). Its tunables are globalsAI.xml entries, exported here so the pages
never hard-code them. verify_source_constants.py watches the functions.

Also exported:
  • traits with iUnitBuildModifier — the ONLY character influence on the picker
    (PlayerAI.calculateTargetMilitaryUnitNumber, gated by council bTraitsAffectAutobuild,
    which only the Grand Vizier seat sets);
  • the "defensive" projects the AI restricts itself to when a city is in danger
    (isDefensiveCityEffect: effect iCityHP>0 or iStrengthModifier>0);
  • projects with bRequiresGovernor (buildable under an acting governor — City.canBuildProject
    tests isGoverned(), which counts the default governor);
  • traits with a <GovernorEffectCity> (the Vizier's own traits apply in every city he runs);
  • the Autonomous Rule event lifecycle (grant / end) with option outcomes.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    load_xml_indexes, render_effect_city, _lookup_name, _first_form, yield_name, fmt_decimal,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "autobuild.json"

PROJECT_FILES = ["project.xml", "project-event.xml", "project-event-eoti.xml",
                 "project-event-sap.xml", "project-event-wd.xml", "project-event-wog.xml"]
EVENT_FILES = ["eventStory.xml", "eventStory-btt.xml", "eventStory-eoti.xml",
               "eventStory-sap.xml", "eventStory-wd.xml", "eventStory-wog.xml"]
OPTION_FILES = ["eventOption.xml", "eventOption-btt.xml", "eventOption-eoti.xml",
                "eventOption-sap.xml", "eventOption-wd.xml", "eventOption-wog.xml"]

AI_CONSTANTS = [
    "AI_MIN_PROJECT_BUILD_TURNS", "AI_HALF_VALUE_PROJECT_BUILD_TURNS",
    "AI_MIN_SPECIALIST_BUILD_TURNS", "AI_HALF_VALUE_SPECIALIST_BUILD_TURNS",
    "AI_MIN_UNIT_BUILD_TURNS", "AI_HALF_VALUE_UNIT_BUILD_TURNS",
    "AI_NO_UNIT_BUILD_PERCENT", "AI_CITY_MIN_DANGER", "AI_CITY_AUTOBUILD_VALUE",
    "AI_MAX_NUM_WORKERS_PER_HUNDRED_CITIES", "AI_MAX_NUM_WORKERS_PER_HUNDRED_ORDERS",
    "AI_MAX_NUM_DISCIPLES_PER_HUNDRED_CITIES", "AI_MAX_NUM_DISCIPLES_PER_HUNDRED_ORDERS",
    "AI_MAX_ALLOWED_EXPENSE_IN_SHORTAGE",
]

DLC_LABELS = {
    "EVENTPACK_RELIGION": "The Sacred and the Profane",
    "EVENTPACK_SCANDAL": "Behind the Throne",
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus",
    "WONDERS_DYNASTIES": "Wonders & Dynasties",
    "CALAMITIES": "Wrath of Gods",
}

# The Autonomous Rule lifecycle is DETECTED, not listed: every event whose
# options (transitively, through nested aeBonuses) add or remove
# PROJECT_AUTONOMOUS_RULE, plus events gated on SUBJECT_CITY_AUTONOMOUS_RULE.
# (A hand list missed Demand for Autonomy and Independent City on first pass.)
AUTONOMY_PROJECT = "PROJECT_AUTONOMOUS_RULE"
AUTONOMY_SUBJECT = "SUBJECT_CITY_AUTONOMOUS_RULE"
ROLE_ORDER = {"grant": 0, "during": 1, "end": 2}


def index(files: list[str]) -> dict[str, ET.Element]:
    out: dict[str, ET.Element] = {}
    for fn in files:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            z = e.findtext("zType")
            if z and z not in out:
                out[z] = e
    return out


def main() -> None:
    indexes = load_xml_indexes(XML_DIR)
    text = indexes["__text__"]
    T = lambda k: _lookup_name(indexes, k or "")  # noqa: E731

    effect_city = indexes["effectCity.xml"]
    effect_player = indexes["effectPlayer.xml"]
    traits = indexes["trait.xml"]
    projects = index(PROJECT_FILES)
    bonuses = indexes["bonus.xml"]
    events = index(EVENT_FILES)
    options = index(OPTION_FILES)
    councils = index(["council.xml", "council-btt.xml"])
    subjects = index(["subject.xml"])
    globals_ai = {e.findtext("zType"): int(e.findtext("iValue") or "0")
                  for e in ET.parse(XML_DIR / "globalsAI.xml").getroot().findall("Entry")
                  if e.findtext("zType")}

    projects_json = {p["id"]: p for p in json.loads((ROOT / "src" / "data" / "projects.json").read_text())}
    council_json = json.loads((ROOT / "src" / "data" / "council.json").read_text())
    try:
        event_hrefs = {r["i"]: r["h"] for r in json.loads((ROOT / "src" / "data" / "event-search.json").read_text())}
    except Exception:  # pragma: no cover — event index is optional
        event_hrefs = {}

    def project_ref(pid: str) -> dict:
        pj = projects_json.get(pid)
        e = projects.get(pid)
        name = (pj or {}).get("name") or (T(e.findtext("Name")) if e is not None else "") or pid
        return {"id": pid, "name": name, "slug": (pj or {}).get("slug", pid.replace("PROJECT_", "").lower())}

    def trait_name(tid: str) -> str:
        return T(f"TEXT_{tid}") or tid.replace("TRAIT_", "").replace("_ARCHETYPE", "").replace("_", " ").title()

    # ── constants ──────────────────────────────────────────────────────────
    constants = {k: globals_ai.get(k, 0) for k in AI_CONSTANTS}

    # ── the two carriers ───────────────────────────────────────────────────
    carriers = []
    for cid, e in effect_city.items():
        if (e.findtext("bAutoBuild") or "0") != "1":
            continue
        dg = e.findtext("DefaultGovernor") or ""
        yields = []
        for pr in e.findall("aiYieldRatePopulation/Pair"):
            v = int(pr.findtext("iValue") or "0") / 10
            yields.append(f"{fmt_decimal(v)} {yield_name(pr.findtext('zIndex'))}/Pop")
        carriers.append({
            "id": cid,
            "name": T(e.findtext("Name")),
            "autoBuild": True,
            "noHurry": (e.findtext("bNoHurry") or "0") == "1",
            "noBuildUnits": (e.findtext("bNoBuildUnits") or "0") == "1",
            "defaultGovernor": dg,
            "defaultGovernorName": next((c["name"] for c in council_json["seats"] if c["id"] == dg), ""),
            "yields": yields,
            "effects": render_effect_city(e, indexes=indexes),
        })
    carriers.sort(key=lambda c: c["id"])

    # ── the Grand Vizier seat ──────────────────────────────────────────────
    vz = councils["COUNCIL_GRAND_VIZIER"]
    ep_id = vz.findtext("EffectPlayer") or ""
    ep = effect_player.get(ep_id)
    seat_json = next((s for s in council_json["seats"] if s["id"] == "COUNCIL_GRAND_VIZIER"), {})
    vizier = {
        "id": "COUNCIL_GRAND_VIZIER",
        "name": seat_json.get("name") or "Grand Vizier",
        "slug": seat_json.get("slug", "grand_vizier"),
        "dlc": DLC_LABELS.get(vz.findtext("GameContentRequired") or "", ""),
        "traitPrereqs": [{"id": p.findtext("zIndex"), "name": trait_name(p.findtext("zIndex") or "")}
                         for p in vz.findall("abTraitPrereq/Pair") if (p.findtext("bValue") or "0") == "1"],
        "assignOpinion": int(vz.findtext("iOpinion") or "0"),
        "xpPerTurn": int(vz.findtext("iXP") or "0"),
        "traitsAffectAutobuild": (vz.findtext("bTraitsAffectAutobuild") or "0") == "1",
        "noNotifications": (vz.findtext("bNoNotifications") or "0") == "1",
        "effectPlayer": ep_id,
        "effectPlayerName": T(ep.findtext("Name")) if ep is not None else "",
        "noGovernorEffectCity": ep.findtext("NoGovernorEffectCity") if ep is not None else "",
        "help": {
            "cannotChange": text.get("TEXT_HELPTEXT_AUTO_BUILD_CITY_EFFECT", ""),
            "cannotChoose": text.get("TEXT_HELPTEXT_EFFECT_CITY_HELP_NO_YIELDS_AUTO_BUILD", ""),
            "actsAsGovernor": text.get("TEXT_HELPTEXT_EFFECT_CITY_HELP_NO_YIELDS_DEFAULT_GOVERNOR", ""),
            "noUnits": text.get("TEXT_HELPTEXT_EFFECT_CITY_HELP_NO_UNIT_BUILD", ""),
            "citiesWithoutGovernor": text.get("TEXT_HELPTEXT_EFFECT_PLAYER_HELP_NO_GOVERNOR_EFFECT", ""),
            "automateButton": text.get("TEXT_UI_TOGGLE_CITY_AUTOMATION", ""),
        },
    }
    # Only seats with bTraitsAffectAutobuild feed getUnitBuildModifier for humans.
    vizier["seatsAffectingAutobuild"] = sorted(
        cid for cid, c in councils.items() if (c.findtext("bTraitsAffectAutobuild") or "0") == "1")

    # ── iUnitBuildModifier traits ──────────────────────────────────────────
    ubm = []
    for tid, e in traits.items():
        v = int(e.findtext("iUnitBuildModifier") or "0")
        if v:
            ubm.append({"id": tid, "name": trait_name(tid), "modifier": v,
                        "archetype": tid.endswith("_ARCHETYPE")})
    ubm.sort(key=lambda t: (-t["modifier"], t["name"]))

    # ── defensive projects (isDefensiveCityEffect) ─────────────────────────
    def defensive(eid: str | None) -> bool:
        e = effect_city.get(eid or "")
        if e is None:
            return False
        return int(e.findtext("iCityHP") or "0") > 0 or int(e.findtext("iStrengthModifier") or "0") > 0

    defensive_projects = []
    for pid, e in projects.items():
        if defensive(e.findtext("EffectCity")) or defensive(e.findtext("EffectCityExtra")):
            r = project_ref(pid)
            r["eventOnly"] = (e.findtext("bHidden") or "0") == "1"
            r["dlc"] = DLC_LABELS.get(e.findtext("GameContentRequired") or "", "")
            defensive_projects.append(r)
    defensive_projects.sort(key=lambda p: p["name"])

    # ── bRequiresGovernor projects ─────────────────────────────────────────
    gov_required = []
    for pid, e in projects.items():
        if (e.findtext("bRequiresGovernor") or "0") == "1":
            r = project_ref(pid)
            r["dlc"] = DLC_LABELS.get(e.findtext("GameContentRequired") or "", "")
            pre = e.findtext("EffectCityPrereq") or ""
            r["needsEffect"] = T(effect_city[pre].findtext("Name")) if pre in effect_city else ""
            costs = [f"{pr.findtext('iValue')} {yield_name(pr.findtext('zIndex'))}" for pr in e.findall("aiYieldCost/Pair")]
            r["cost"] = ", ".join(costs)
            gov_required.append(r)
    gov_required.sort(key=lambda p: p["name"])

    # ── traits with a governor effect ──────────────────────────────────────
    gov_traits = []
    for tid, e in traits.items():
        gec = e.findtext("GovernorEffectCity") or ""
        if gec and gec in effect_city:
            lines = render_effect_city(effect_city[gec], indexes=indexes)
            gov_traits.append({"id": tid, "name": trait_name(tid), "effectCity": gec,
                               "archetype": tid.endswith("_ARCHETYPE"), "effects": lines})
    gov_traits.sort(key=lambda t: (not t["archetype"], t["name"]))

    # ── Autonomous Rule lifecycle ──────────────────────────────────────────
    def describe_bonus(bid: str, depth: int = 0) -> list[str]:
        b = bonuses.get(bid)
        if b is None or depth > 3:
            return []
        out: list[str] = []
        for z in b.findall("aeAddProjects/zValue"):
            out.append(f"grants {project_ref(z.text or '')['name']}")
        for z in b.findall("aeRemoveProjects/zValue"):
            out.append(f"removes {project_ref(z.text or '')['name']}")
        n = int(b.findtext("iRebelUnits") or "0")
        if n:
            out.append(f"{n} rebel unit{'s' if n != 1 else ''} spawn")
        hl = int(b.findtext("iHappinessLevels") or "0")
        if hl:
            out.append(f"{hl:+d} Happiness level")
        for pr in b.findall("aiCityYields/Pair"):
            out.append(f"{int(pr.findtext('iValue') or '0'):+d} {yield_name(pr.findtext('zIndex'))} in the city")
        for pr in b.findall("aiGlobalYieldsBase/Pair"):
            out.append(f"{int(pr.findtext('iValue') or '0'):+d} {yield_name(pr.findtext('zIndex'))} (scales)")
        leg = int(b.findtext("iLegitimacy") or "0")
        if leg:
            out.append(f"{leg:+d} Legitimacy")
        xp = int(b.findtext("iXPCharacter") or "0")
        if xp:
            out.append(f"+{xp} XP")
        for z in b.findall("aeAddTraits/zValue"):
            out.append(f"gains {trait_name(z.text or '')}")
        for z in b.findall("aeRemoveTraits/zValue"):
            out.append(f"loses {trait_name(z.text or '')}")
        rel = b.findtext("AddLeaderRelationship") or ""
        if rel:
            nice = re.sub(r"\s*\{[^}]*\}", "", T(f"TEXT_{rel}")).strip().lower() or \
                rel.replace("RELATIONSHIP_", "").replace("_", " ").lower()
            out.append(f"leader becomes {nice} them")
        if b.findtext("iGovernorOfSubject") is not None:
            out.append("becomes the city's Governor")
        for pr in b.findall("aiRatings/Pair"):
            out.append(f"{int(pr.findtext('iValue') or '0'):+d} {(pr.findtext('zIndex') or '').replace('RATING_', '').title()}")
        if (b.findtext("bStartCivilWar") or "0") == "1" or bid == "BONUS_START_CIVIL_WAR":
            out.append("civil war")
        mem = b.findtext("Memory") or ""
        if mem:
            out.append("family remembers it")
        for z in b.findall("aeBonuses/zValue"):
            out.extend(describe_bonus(z.text or "", depth + 1))
        return out

    def resolve_option(oid: str) -> ET.Element | None:
        """_BTT wrapper options pick a real option by weight (aiEventOptionProb)."""
        o = options.get(oid)
        if o is None:
            return None
        probs = o.findall("aiEventOptionProb/Pair")
        if probs and o.findtext("Text") is None:
            best = max(probs, key=lambda p: int(p.findtext("iValue") or "0"))
            return options.get(best.findtext("zIndex") or "")
        return o

    def bonus_touches(bid: str, tag: str, depth: int = 0) -> bool:
        b = bonuses.get(bid)
        if b is None or depth > 3:
            return False
        if any(z.text == AUTONOMY_PROJECT for z in b.findall(f"{tag}/zValue")):
            return True
        return any(bonus_touches(z.text or "", tag, depth + 1) for z in b.findall("aeBonuses/zValue"))

    def option_row(text_key: str, bonus_ids: list[str], link_add: str) -> dict:
        outcomes: list[str] = []
        for bid in bonus_ids:
            outcomes.extend(describe_bonus(bid))
        return {"text": text.get(text_key, text_key), "outcomes": outcomes,
                "grants": any(bonus_touches(b, "aeAddProjects") for b in bonus_ids),
                "removes": any(bonus_touches(b, "aeRemoveProjects") for b in bonus_ids),
                "eventLink": link_add}

    def event_options(e: ET.Element) -> list[dict]:
        rows = []
        for z in e.findall("aeOptions/zValue"):            # classic: aeOptions → eventOption entries
            o = resolve_option(z.text or "")
            if o is not None:
                rows.append(option_row(o.findtext("Text") or "",
                                       [b.text for b in o.findall("aeBonuses/zValue") if b.text],
                                       o.findtext("EventLinkAdd") or ""))
        for o in e.findall("EventOptions/EventOption"):    # inline (EotI files)
            rows.append(option_row(o.findtext("Text") or "",
                                   [p.findtext("Second") or "" for p in o.findall("SubjectBonuses/Pair")],
                                   o.findtext("EventLinkAdd") or ""))
        return rows

    autonomy_events = []
    for eid, e in events.items():
        rows = event_options(e)
        extras = [p.findtext("Second") for p in e.findall("SubjectExtras/Pair")] + \
                 [s.findtext("Extra") for s in e.findall("Subjects/Subject")]
        not_extras = [p.findtext("Second") for p in e.findall("SubjectNotExtras/Pair")] + \
                     [s.findtext("NotExtra") for s in e.findall("Subjects/Subject")]
        grants = any(r["grants"] for r in rows)
        removes = any(r["removes"] for r in rows)
        gated = AUTONOMY_SUBJECT in extras
        if not (grants or removes or gated):
            continue
        role = "grant" if grants else ("end" if removes else "during")
        autonomy_events.append({
            "id": eid,
            "role": role,
            "title": T(e.findtext("Name")),
            "text": _first_form(text.get(e.findtext("Text") or "", "")),
            "dlc": DLC_LABELS.get(e.findtext("GameContentRequired") or "", ""),
            "trigger": (e.findtext("Trigger") or "").replace("EVENTTRIGGER_", "").replace("_", " ").title(),
            "prob": int(e.findtext("iProb") or "0"),
            "repeatTurns": int(e.findtext("iRepeatTurns") or "0"),
            "eventLinkPrereq": e.findtext("EventLinkPrereq") or "",
            "eventLinkTurns": int(e.findtext("iEventLinkTurns") or "0"),
            "requires": [x for x in extras if x],
            "excludes": [x for x in not_extras if x],
            "options": rows,
            "href": event_hrefs.get(eid, ""),
            "author": e.findtext("zAuthor") or "",
            "url": e.findtext("zEventURL") or "",
        })
    autonomy_events.sort(key=lambda ev: (ROLE_ORDER[ev["role"]], ev["title"], ev["id"]))

    ar = projects["PROJECT_AUTONOMOUS_RULE"]
    autonomy_project = dict(projects_json.get("PROJECT_AUTONOMOUS_RULE", {}))
    autonomy_project.update({
        "captureDestroy": (ar.findtext("bCaptureDestroy") or "0") == "1",
        "hidden": (ar.findtext("bHidden") or "0") == "1",
        "maxCount": int(ar.findtext("iMaxCount") or "0"),
        "effectCity": ar.findtext("EffectCity") or "",
    })

    out = {
        "constants": constants,
        "carriers": carriers,
        "vizier": vizier,
        "unitBuildModifierTraits": ubm,
        "defensiveProjects": defensive_projects,
        "governorRequiredProjects": gov_required,
        "governorTraitEffects": gov_traits,
        "autonomy": {"project": autonomy_project, "events": autonomy_events},
        "examples": {
            "opulence": project_ref("PROJECT_LAVISH_LIFESTYLE"),
            "decree": project_ref("PROJECT_DECREE_1"),
            "festival": project_ref("PROJECT_FESTIVAL_1"),
            "inquiry": project_ref("PROJECT_INQUIRY_1"),
            "treasury": project_ref("PROJECT_TREASURY_1"),
        },
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(carriers)} carriers, {len(ubm)} build-modifier traits, "
          f"{len(defensive_projects)} defensive projects, {len(gov_required)} governor-gated projects, "
          f"{len(gov_traits)} governor traits, {len(autonomy_events)} events")


if __name__ == "__main__":
    main()
