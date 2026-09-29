#!/usr/bin/env python3
"""Build src/data/leaders.json — every playable dynasty (the leader you pick
on the single-player setup screen), grouped by nation.

Per dynasty, straight from the XML:
  dynasty.xml     Name, Description (the setup-screen pitch), Nation, Founder,
                  FirstRuler, FirstCityName, PreferredReligion, EffectPlayer,
                  GameContentRequired (DLC label via scripts/dlc.py)
  nation.xml      aeDynasties order + DefaultDynasty (the leader you get when
                  the setup screen is left on "default")
  character.xml   the first ruler (age, traits, portrait, Wikipedia URL) and
                  the starting court (aePlayerDynasties members, relations
                  from build_data.load_dynasty_courts)
  traits.json     each leader trait's role effects (build_traits.py)
  improvement.xml DynastyPrereq → improvements only that dynasty can build
  project.xml     EffectPlayerPrereq = the dynasty's EffectPlayer → projects
  subject.xml +   events cast for this dynasty: a subject with DynastyPrereq,
  eventStory*.xml a subject naming the ruler, founder or a court member as its
                  Character, or one gated on the dynasty's EffectPlayer.
                  Links come from event-search.json (never re-derived).

Descriptions keep the game's link(TOKEN) markup as segments (build_hints'
SegmentingCleaner), so the page links exactly what the game links instead of
printing "link(RELIGION_CHRISTIANITY)".

Run after build_data.py, build_traits.py and build_event_search.py.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_data as bd  # noqa: E402
import dlc  # noqa: E402
from build_concepts import load_full_text_index, load_globals_int  # noqa: E402
from build_hints import SegmentingCleaner, segment  # noqa: E402
from humanize import load_xml_indexes, render_effect_player  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
DATA = ROOT / "src" / "data"
OUT = DATA / "leaders.json"


def parse(name: str) -> list[ET.Element]:
    return ET.parse(XML_DIR / name).getroot().findall("Entry")


def first_form(s: str) -> str:
    return re.sub(r"<[^>]+>", "", (s or "").split("~")[0]).strip()


def main() -> int:
    text = load_full_text_index()
    cleaner = SegmentingCleaner(text, load_globals_int())
    indexes = load_xml_indexes(XML_DIR)
    characters = bd.load_characters(None)
    portrait_map = bd.load_portrait_map()
    courts = bd.load_dynasty_courts(structured=True)

    traits: dict[str, dict] = {}
    for cat, items in json.loads((DATA / "traits.json").read_text()).items():
        for t in items if isinstance(items, list) else []:
            traits[t["id"]] = {**t, "category": cat}
    nations_json = json.loads((DATA / "nations.json").read_text())
    nations_json = nations_json["nations"] if isinstance(nations_json, dict) else nations_json
    search = {e["i"]: e for e in json.loads((DATA / "event-search.json").read_text())}

    def tname(key: str, default: str = "") -> str:
        return first_form(text.get(key, "")) or default

    def trait_label(tid: str) -> str:
        t = traits.get(tid)
        return t["name"] if t else tname(f"TEXT_{tid}", tid.replace("TRAIT_", "").replace("_", " ").title())

    # ── dynasties ────────────────────────────────────────────────────────────
    dyn: dict[str, ET.Element] = {}
    for e in parse("dynasty.xml"):
        z = e.findtext("zType") or ""
        if z.startswith("DYNASTY_") and e.findtext("Nation"):
            dyn[z] = e
    dyn_ep = {e.findtext("EffectPlayer"): z for z, e in dyn.items() if e.findtext("EffectPlayer")}

    nation_order: dict[str, list[str]] = {}
    default_dyn: dict[str, str] = {}
    for e in parse("nation.xml"):
        n = e.findtext("zType") or ""
        nation_order[n] = [v.text for v in e.findall("aeDynasties/zValue") if v.text]
        default_dyn[n] = e.findtext("DefaultDynasty") or ""

    # Improvements / projects only one dynasty unlocks.
    unlocks: dict[str, list[dict]] = defaultdict(list)
    for e in parse("improvement.xml"):
        d = e.findtext("DynastyPrereq")
        if d in dyn:
            z = e.findtext("zType") or ""
            unlocks[d].append({"id": z, "kind": "Improvement",
                               "name": tname(e.findtext("Name") or "", z)})
    for e in parse("project.xml"):
        d = dyn_ep.get(e.findtext("EffectPlayerPrereq") or "")
        if d:
            z = e.findtext("zType") or ""
            unlocks[d].append({"id": z, "kind": "Project",
                               "name": tname(e.findtext("Name") or "", z)})

    # ── events cast for a dynasty ────────────────────────────────────────────
    char_dyn: dict[str, set[str]] = defaultdict(set)
    for z, e in dyn.items():
        for f in ("FirstRuler", "Founder"):
            if e.findtext(f):
                char_dyn[e.findtext(f)].add(z)
    for e in parse("character.xml"):
        for v in e.findall("aePlayerDynasties/zValue"):
            if v.text in dyn:
                char_dyn[e.findtext("zType") or ""].add(v.text)

    subj_dyn: dict[str, set[str]] = {}
    for e in parse("subject.xml"):
        ds: set[str] = set()
        if e.findtext("DynastyPrereq") in dyn:
            ds.add(e.findtext("DynastyPrereq"))
        ds |= char_dyn.get(e.findtext("Character") or "", set())
        for t in e.iter():
            if (t.text or "").strip() in dyn_ep:
                ds.add(dyn_ep[t.text.strip()])
        if ds:
            subj_dyn[e.findtext("zType") or ""] = ds

    events: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(XML_DIR.glob("eventStory*.xml")):
        for e in ET.parse(p).getroot().findall("Entry"):
            sid = e.findtext("zType") or ""
            hit = search.get(sid)
            if not hit:
                continue
            ds: set[str] = set()
            for t in e.iter():
                ds |= subj_dyn.get((t.text or "").strip(), set())
            for d in ds:
                events[d].append({"id": sid, "name": hit["n"], "href": hit["h"], "trigger": hit.get("g", "")})

    def event_rows(z: str, nation_name: str) -> list[dict]:
        rows = []
        for ev in events.get(z, []):
            # The opening story is titled "[nation] in the Old World" — the
            # player slot is always you, so name it.
            if ev["trigger"] in ("Start Game", "City Founded"):
                ev = {**ev, "name": re.sub(r"\[(nation|rival)\]", nation_name, ev["name"])}
            rows.append(ev)
        return sorted(rows, key=lambda ev: (ev["trigger"] not in ("Start Game", "City Founded"),
                                            ev["trigger"] != "Start Game", ev["trigger"], ev["name"], ev["id"]))

    def describe(raw: str) -> list[dict]:
        # Gendered link forms keep their "{0_character}" slot ("Terrified of
        # {0_character}"); the sentence already names the person, so drop it.
        segs = segment(cleaner.clean(raw)) if raw else []
        return [{**sg, "text": re.sub(r"\s*\{\d+_\w+\}", "", sg["text"])} for sg in segs]

    # ── assemble ─────────────────────────────────────────────────────────────
    def trait_card(tid: str) -> dict:
        t = traits.get(tid, {})
        ratings, seen = [], set()
        for r in sorted(t.get("ratings") or [], key=lambda r: r.get("fallback", False)):
            if r["rating"] not in seen:
                seen.add(r["rating"])
                ratings.append(f"{r['value']:+d} {r['rating']}")
        return {
            "id": tid, "name": trait_label(tid),
            "leader": t.get("leaderEffects") or [],
            "governor": t.get("governorEffects") or [],
            "general": t.get("generalEffects") or [],
            "ratings": ratings,
        }

    def court_member(c: dict) -> dict:
        ch = characters.get(c["id"], {})
        return {
            "name": ch.get("name") or bd._format_id_name(c["id"], "CHARACTER_"),
            "relation": c.get("relation", "spouse"),
            "age": c["age"],
            "traits": [trait_label(t) for t in c["traits"] if t != "TRAIT_EXCLUDED"],
        }

    out_nations = []
    for n in nations_json:
        nid = n["id"]
        ids = [d for d in nation_order.get(nid, []) if d in dyn]
        ids += [d for d, e in dyn.items() if e.findtext("Nation") == nid and d not in ids]
        rows = []
        for z in ids:
            e = dyn[z]
            ruler_id = e.findtext("FirstRuler") or e.findtext("Founder") or ""
            ruler = characters.get(ruler_id, {})
            founder = characters.get(e.findtext("Founder") or "", {})
            trait_ids = [t["id"] for t in ruler.get("traits", [])]
            arch = next((t for t in trait_ids if t.endswith("_ARCHETYPE")), "")
            portrait = bd.find_portrait(ruler.get("name", ""), ruler_id,
                                        ruler.get("preferredPortrait", ""), portrait_map)
            desc_raw = text.get(e.findtext("Description") or "", "")
            court = courts.get(z, {"spouses": [], "kin": []})
            ep = e.findtext("EffectPlayer") or ""
            rel = e.findtext("PreferredReligion") or ""
            rows.append({
                "id": z,
                "slug": z.removeprefix("DYNASTY_").lower(),
                "name": tname(e.findtext("Name") or "", ruler.get("name", z)),
                "isDefault": default_dyn.get(nid) == z,
                "dlc": dlc.label(e.findtext("GameContentRequired") or "", "") or "",
                "leader": {
                    "id": ruler_id, "name": ruler.get("name", ""), "age": ruler.get("age") or None,
                    "female": ruler.get("gender") == "GENDER_FEMALE", "url": ruler.get("url", ""),
                },
                "founder": founder.get("name") if founder and founder is not ruler else None,
                "portrait": portrait,
                "archetype": arch,
                "traits": [trait_card(t) for t in trait_ids if not t.endswith("_ARCHETYPE")],
                "description": describe(desc_raw),
                "bonus": render_effect_player(ep, indexes) if ep else [],
                "capital": tname(f"TEXT_{e.findtext('FirstCityName')}", "") if e.findtext("FirstCityName") else "",
                "religion": {"id": rel, "name": tname(f"TEXT_{rel}", rel)} if rel else None,
                "unlocks": unlocks.get(z, []),
                "court": [court_member(c) for c in court["spouses"]] + [court_member(c) for c in court["kin"]],
                "events": event_rows(z, n["name"]),
            })
        if rows:
            out_nations.append({"id": nid, "name": n["name"], "slug": n["slug"],
                                "color": n.get("color"), "dynasties": rows})

    # The setup screen's other choices (Default / Random / Pick Later) are
    # nation-less dynasty.xml entries.
    setup = [{"id": e.findtext("zType"), "name": tname(e.findtext("Name") or ""),
              "description": tname(e.findtext("Description") or "")}
             for e in parse("dynasty.xml")
             if (e.findtext("zType") or "").startswith("DYNASTY_") and not e.findtext("Nation")]

    OUT.write_text(json.dumps({"nations": out_nations, "setupOptions": setup}, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    total = sum(len(n["dynasties"]) for n in out_nations)
    evs = sum(len(d["events"]) for n in out_nations for d in n["dynasties"])
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {total} dynasties across {len(out_nations)} nations, {evs} event links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
