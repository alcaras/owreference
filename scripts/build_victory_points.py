#!/usr/bin/env python3
"""Build src/data/victory_points.json — everything Game.cs getVPToWin() reads.

The Victory Point target is not a table in the XML; the engine computes it per
game from the map's city-site count and the game setup:

    for each culture level:        sites * culture.iVP / (cultures + (characters ? 0 : 1))
    for each buildable VP improvement (wonders, holy sites):
                                   min(sites*12, 1 if wonder, maxPlayer*players, ...) * iVP
    for each VP project:           (sites / 4, capped at players if unique) * iVP
    * 6 / (3 + teams)
    * 2/5 if exactly 2 players, else / 2
    modified by the Victory Point setup option (victoryPoint.xml iModifier)

Every division is C# integer division. We emit the *inputs* (culture VPs,
the VP-bearing improvements/projects with their caps and content gates, the
globals) so the page replays the routine client-side for any setup, rather
than a pre-baked table for one set of options.

Two wonder facts come from finishMapPlacement, not getVPToWin: only
AVAILABLE_WONDERS (13) of the content-enabled wonders are ever buildable in a
game — the rest are disabled at map placement, and getVPToWin skips disabled
improvements — and NO_WONDERS disables them all.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "victory_points.json"

WANTED_GLOBALS = ["AVAILABLE_WONDERS", "NO_WONDERS", "MAX_FAMILIES"]


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def entries(name: str) -> list[ET.Element]:
    # The first <Entry> of every info file is the blank schema template.
    return [e for e in parse(name).findall("Entry") if (e.findtext("zType") or "").strip()]


def load_text() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("text-*.xml")):
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        for e in root.findall("Entry"):
            k, v = e.findtext("zType"), e.findtext("en-US")
            if k and v and k not in out:
                v = re.sub(r"^icon\([^)]*\)", "", v.split("~")[0])
                v = re.sub(r"\{[^}]*\}", "", v)
                out[k] = re.sub(r"\s{2,}", " ", v).strip()
    return out


def flag(e: ET.Element, key: str) -> bool:
    return (e.findtext(key) or "0") == "1"


def num(e: ET.Element, key: str) -> int:
    return int(e.findtext(key) or "0")


def main() -> int:
    text = load_text()
    name = lambda e, fallback: text.get(e.findtext("Name") or "", fallback)  # noqa: E731

    globals_int = {}
    for e in entries("globalsInt.xml"):
        z = e.findtext("zType")
        if z in WANTED_GLOBALS:
            globals_int[z] = num(e, "iValue")
    missing = [g for g in WANTED_GLOBALS if g not in globals_int]
    if missing:
        print(f"✗ globalsInt.xml is missing {missing}", file=sys.stderr)
        return 1

    cultures = [{
        "id": e.findtext("zType"),
        "name": name(e, e.findtext("zType")),
        "vp": num(e, "iVP"),
    } for e in entries("culture.xml")]

    religions_num = len(entries("religion.xml"))

    # DLC → the GameContent flags it switches on, so the page can label a
    # content toggle by the product the player actually bought.
    contents: dict[str, dict] = {}
    for e in entries("additionalContent.xml"):
        for v in e.findall("aeGameContent/zValue"):
            if v.text:
                contents[v.text] = {
                    "dlc": e.findtext("zType"),
                    "dlcName": name(e, e.findtext("zType")),
                }

    effect_vp = {e.findtext("zType"): num(e, "iVP") for e in entries("effectPlayer.xml")}

    imp_class = {e.findtext("zType"): e for e in entries("improvementClass.xml")}

    # Infos.cs: an EffectPlayer shared by two improvements is the "source" of
    # neither (meSourceImprovement reset to NONE), so it contributes nothing.
    imp_by_effect: dict[str, list[ET.Element]] = {}
    for e in entries("improvement.xml"):
        ep = e.findtext("EffectPlayer")
        if ep:
            imp_by_effect.setdefault(ep, []).append(e)

    improvements = []
    skipped = []  # VP-bearing but failing a getVPToWin gate — the page lists why
    for ep, imps in imp_by_effect.items():
        if len(imps) != 1 or effect_vp.get(ep, 0) <= 0:
            continue
        e = imps[0]
        # getVPToWin's own gates: buildable, no nation/dynasty prereq.
        reason = ("not buildable" if not flag(e, "bBuild")
                  else "nation-specific" if e.findtext("NationPrereq")
                  else "dynasty-specific" if e.findtext("DynastyPrereq") else "")
        if reason:
            skipped.append({"id": e.findtext("zType"), "name": name(e, e.findtext("zType")),
                            "vp": effect_vp[ep], "reason": reason})
            continue
        cls = imp_class.get(e.findtext("Class") or "")
        improvements.append({
            "id": e.findtext("zType"),
            "name": name(e, e.findtext("zType")),
            "vp": effect_vp[ep],
            "wonder": flag(e, "bWonder"),
            "holyCity": flag(e, "bHolyCity"),
            "religionPrereq": e.findtext("ReligionPrereq") or "",
            "maxPlayerCount": num(e, "iMaxPlayerCount"),
            "maxFamilyCount": num(e, "iMaxFamilyCount"),
            "maxCityCount": num(e, "iMaxCityCount"),
            "classMaxCityCount": num(cls, "iMaxCityCount") if cls is not None else 0,
            "classMaxCultureCount": num(cls, "iMaxCultureCount") if cls is not None else 0,
            # finishMapPlacement disables these first when trimming to
            # AVAILABLE_WONDERS in a duel — affects which wonders, not how many.
            "duelDisable": flag(e, "bDuelDisable"),
            "content": e.findtext("GameContentRequired") or "",
        })
    improvements.sort(key=lambda i: (not i["wonder"], i["content"], i["name"]))

    proj_by_effect: dict[str, list[ET.Element]] = {}
    for e in entries("project.xml"):
        ep = e.findtext("EffectPlayer")
        if ep:
            proj_by_effect.setdefault(ep, []).append(e)

    projects = []
    for ep, projs in proj_by_effect.items():
        if len(projs) != 1 or effect_vp.get(ep, 0) <= 0:
            continue
        e = projs[0]
        if flag(e, "bHidden") or e.findall("abInvalidBy/zValue"):
            continue
        projects.append({
            "id": e.findtext("zType"),
            "name": name(e, e.findtext("zType")),
            "vp": effect_vp[ep],
            "unique": flag(e, "bUnique"),
            "content": e.findtext("GameContentRequired") or "",
        })
    projects.sort(key=lambda p: (p["content"], p["name"]))

    victory_point_options = [{
        "id": e.findtext("zType"),
        "name": name(e, e.findtext("zType")),
        "modifier": num(e, "iModifier"),
    } for e in entries("victoryPoint.xml")]

    # Victory conditions that are a share of the target (Points 100%, Double
    # 50% + twice any opponent). The rest don't read getVPToWin at all.
    victories = [{
        "id": e.findtext("zType"),
        "name": name(e, e.findtext("zType")),
        "percentVP": num(e, "iPercentVP"),
        "opponentMaxPointPercent": num(e, "iOpponentMaxPointPercent"),
    } for e in entries("victory.xml") if num(e, "iPercentVP") > 0]

    used_contents = sorted({i["content"] for i in improvements} | {p["content"] for p in projects})
    used_contents = [c for c in used_contents if c]
    unknown = [c for c in used_contents if c not in contents]
    if unknown:
        print(f"✗ additionalContent.xml has no DLC for {unknown}", file=sys.stderr)
        return 1

    out = {
        "globals": globals_int,
        "cultures": cultures,
        "religionsNum": religions_num,
        "contents": {c: contents[c] for c in used_contents},
        "improvements": improvements,
        "skippedImprovements": sorted(skipped, key=lambda i: i["name"]),
        "projects": projects,
        "victoryPointOptions": victory_point_options,
        "victories": victories,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    wonders = sum(1 for i in improvements if i["wonder"])
    holy = sum(1 for i in improvements if i["holyCity"])
    print(f"✓ victory_points.json — {len(cultures)} culture levels, {wonders} wonders "
          f"(cap {globals_int['AVAILABLE_WONDERS']}), {holy} holy sites, {len(projects)} projects, "
          f"{len(used_contents)} content gates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
