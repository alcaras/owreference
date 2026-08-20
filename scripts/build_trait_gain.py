#!/usr/bin/env python3
"""Build src/data/trait_gain.json — how to GET a trait onto a character.

The inverse of trait_removal.json, and the answer to "I want Compassionate on
this heir; what do I actually do?". Routes, per trait (see trait_gain_util for
the mechanics and the canAddTrait eligibility gate):

  choose      an event option grants it outright (aeAddTraits) — the actionable one
  chance      an option rolls for it later (aiTraitProbDelay, N%)
  random      an option draws one trait from a pool (aeRandomTrait[Delay])
  religion    an option grants it if the character follows a given religion
  automatic   the STORY's own aeBonuses grant it — the event happens TO you
  fromTrait   another trait rolls into it (trait.xml aiTraitProb)
  occurrence  an occurrence rolls for it (occurrence.xml aiTraitProb)

plus the innate routes already derived by build_traits.py (childhood adjective
roll, tribal roll, min age) and inheritance, which has its own page.

Runs AFTER build_event_search.py (hrefs) and build_traits.py (names, slugs,
categories, innate acquisition strings).
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
DATA = ROOT / "src" / "data"
OUT = DATA / "trait_gain.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_missions as m  # noqa: E402  shared event/bonus humanizer
import trait_gain_util as tgu  # noqa: E402


def cm_ok(s: ET.Element) -> bool:
    """Same rule as build_events.py: CM-eligible unless explicitly excluded."""
    return not any((v.text or "") == "GAMEOPTION_COMPETITIVE_EVENTS"
                   for v in s.findall("aeGameOptionInvalid/zValue"))


def main() -> int:
    text = m.load_text(*sorted(p.name for p in XML_DIR.glob("text-*.xml")))
    stories_x = m.index_many(
        "eventStory.xml", "eventStory-btt.xml", "eventStory-eoti.xml",
        "eventStory-sap.xml", "eventStory-wd.xml", "eventStory-wog.xml")
    eopt = m.index_many(
        "eventOption.xml", "eventOption-btt.xml", "eventOption-eoti.xml",
        "eventOption-sap.xml", "eventOption-wd.xml", "eventOption-wog.xml")
    traits_x = m.index_many("trait.xml")
    occ_x = m.index_many("occurrence.xml")
    bonus_idx = m.bonus_index()

    traits_json = json.loads((DATA / "traits.json").read_text())
    meta: dict[str, dict] = {}
    for cat, rows in traits_json.items():
        for t in rows:
            meta[t["id"]] = {"name": t["name"], "slug": t["slug"], "cat": cat,
                             "innate": t["acquisition"], "dlc": t.get("dlc", "")}

    def tname(tid: str) -> str:
        return meta.get(tid, {}).get("name") or tid.replace("TRAIT_", "").title()

    search = json.loads((DATA / "event-search.json").read_text())
    href = {r["i"]: r["h"] for r in search}
    ename = {r["i"]: r["n"] for r in search}

    subj_x = m.index_many("subject.xml")

    def owner_of(sid: str) -> str:
        """Whose character sits in this subject slot. The recipient of a trait
        grant is decided by the bonus's POSITION in aeBonuses, so this is the
        difference between 'you gain Gracious' and 'your rival does'."""
        e = subj_x.get(sid)
        if e is None:
            return "any"
        if e.findtext("bIsUs") == "1":
            return "you"
        if e.findtext("bIsNotUs") == "1":
            return "them"
        return "any"

    routes: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    seen_keys: set = set()

    def add(tid: str, route: str, row: dict) -> None:
        # One row per (trait, route, story, option, recipient): an option whose
        # variants all grant the same trait to the same person is still one
        # thing you click — but the same click landing the trait on two
        # different subjects is two different facts.
        key = (tid, route, row.get("id"), row.get("opt"), row.get("who"))
        if key in seen_keys:
            return
        seen_keys.add(key)
        routes[tid][route].append(row)

    for sid, s in stories_x.items():
        if not s.findtext("zType"):
            continue
        slots = [x.text or "" for x in s.findall("aeSubjects/zValue")]
        for sub in s.findall("Subjects/Subject"):
            slots.append(sub.findtext("Type") or "")
        who_at = [owner_of(x) for x in slots]

        def recipient(i: int) -> str:
            return who_at[i] if i < len(who_at) else "any"

        base = {
            "id": sid,
            "name": ename.get(sid) or m.clean_text(text.get(s.findtext("Name") or "", "")) or sid,
            "href": href.get(sid, ""),
            "weight": int(s.findtext("iWeight") or 0),
            "cm": 1 if cm_ok(s) else 0,
            "dlc": s.findtext("GameContentRequired") or "",
        }

        # Story-level bonuses: no choice involved, the event just does it.
        # Positional against the same subject list (PlayerEvent.cs:11987).
        for i, ref in enumerate([x.text or "" for x in s.findall("aeBonuses/zValue")]):
            if not ref:
                continue
            g = tgu.grants_of_bonus(ref, bonus_idx)
            who = recipient(i)
            for t in g["direct"]:
                add(t, "automatic", {**base, "opt": None, "who": who})
            for t, pct in g["chance"]:
                add(t, "chance", {**base, "opt": None, "pct": pct, "auto": True, "who": who})
            for t, pool in g["random"]:
                add(t, "random", {**base, "opt": None, "auto": True, "who": who,
                                  "pool": [tname(x) for x in pool]})

        for oz in [x.text for x in s.findall("aeOptions/zValue") if x.text]:
            o = eopt.get(oz)
            if o is None:
                continue
            otext = m.clean_text(text.get(o.findtext("Text") or "", ""))
            rewards: list[str] = []
            for out in m.option_outcomes(o, eopt, bonus_idx, text):
                for r in out["rewards"]:
                    lbl = r.get("text") if isinstance(r, dict) else str(r)
                    if lbl and lbl not in rewards:
                        rewards.append(lbl)
            row = {**base, "opt": oz, "text": otext, "rewards": rewards}

            for i, ref, variant in tgu.option_bonuses(o, eopt):
                g = tgu.grants_of_bonus(ref, bonus_idx)
                who = recipient(i)
                # A variant branch is one arm of a weighted draw: report its
                # odds and ONLY its own payload, never the parent option's
                # flattened outcome list (which would show a dozen mutually
                # exclusive "Gain trait: …" chips as if they all landed).
                vr = None
                if variant:
                    sub = eopt.get(variant["sub"])
                    vr = []
                    if sub is not None:
                        for out in m.option_outcomes(sub, eopt, bonus_idx, text):
                            for r in out["rewards"]:
                                lbl = r.get("text") if isinstance(r, dict) else str(r)
                                if lbl and lbl not in vr:
                                    vr.append(lbl)
                vrow = dict(row)
                if variant:
                    vrow["variant"] = True
                    vrow["draw"] = [variant["weight"], variant["total"]]
                    vrow["rewards"] = vr
                for t in g["direct"]:
                    add(t, "choose", {**vrow, "who": who})
                for t, pct in g["chance"]:
                    add(t, "chance", {**vrow, "pct": pct, "who": who})
                for t, pool in g["random"]:
                    add(t, "random", {**vrow, "who": who,
                                      "pool": [tname(x) for x in pool]})
                for t, rel in g["religion"]:
                    add(t, "religion", {**vrow, "who": who,
                                        "religion": m._tok(rel or "", "RELIGION_")})

    # Trait → trait (trait.xml aiTraitProb) and occurrence → trait.
    for tid, e in traits_x.items():
        for p in e.findall("aiTraitProb/Pair"):
            got, pct = p.findtext("zIndex"), p.findtext("iValue")
            if got and pct and int(pct) > 0:
                routes[got]["fromTrait"].append(
                    {"id": tid, "name": tname(tid),
                     "slug": meta.get(tid, {}).get("slug", ""), "pct": int(pct)})
    for oid, e in occ_x.items():
        for p in e.findall("aiTraitProb/Pair"):
            got, pct = p.findtext("zIndex"), p.findtext("iValue")
            if got and pct and int(pct) > 0:
                routes[got]["occurrence"].append(
                    {"id": oid, "name": m.clean_text(text.get(e.findtext("Name") or "", ""))
                     or m._tok(oid, "OCCURRENCE_"), "pct": int(pct)})

    ROUTES = ["choose", "chance", "random", "religion", "automatic",
              "fromTrait", "occurrence"]
    EVENT_ROUTES = {"choose", "chance", "random", "religion", "automatic"}

    out_traits = []
    for tid in sorted(set(routes) | set(meta)):
        rt = routes.get(tid, {})
        if not any(rt.get(r) for r in ROUTES) and not meta.get(tid, {}).get("innate"):
            continue  # nothing to say about this trait
        info = meta.get(tid, {})
        for r in ROUTES:
            rt.setdefault(r, [])
            rt[r].sort(key=lambda x: (-x.get("weight", 0), x.get("name", "")))
        cm_events = {x["id"] for r in EVENT_ROUTES for x in rt[r] if x["cm"]}
        yours = {x["id"] for r in EVENT_ROUTES for x in rt[r]
                 if x["cm"] and x.get("who") != "them"}
        out_traits.append({
            "id": tid,
            "name": tname(tid),
            "slug": info.get("slug") or tid.lower().replace("trait_", ""),
            "cat": info.get("cat", "status"),
            "dlc": info.get("dlc", ""),
            "innate": info.get("innate", []),
            "prereqs": tgu.preconditions(traits_x[tid], tname) if tid in traits_x else {},
            "routes": {r: rt[r] for r in ROUTES},
            "counts": ({r: len(rt[r]) for r in ROUTES}
                       | {"cmEvents": len(cm_events), "yours": len(yours)}),
        })
    out_traits.sort(key=lambda t: t["name"])

    payload = {
        "traits": out_traits,
        "counts": {
            "traits": len(out_traits),
            "choosable": sum(1 for t in out_traits if t["counts"]["choose"]),
            "yoursOnly": sum(1 for t in out_traits if t["counts"]["yours"]),
            "noEventRoute": sum(1 for t in out_traits
                                if not any(t["counts"][r] for r in EVENT_ROUTES)),
            "events": len({x["id"] for t in out_traits for r in EVENT_ROUTES
                           for x in t["routes"][r]}),
        },
    }
    OUT.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    c = payload["counts"]
    print(f"wrote {OUT.relative_to(ROOT)}: {c['traits']} traits "
          f"({c['choosable']} directly choosable, {c['noEventRoute']} with no event route), "
          f"{c['events']} distinct events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
