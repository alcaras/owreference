#!/usr/bin/env python3
"""Build src/data/events.json — the Exploration Events tab.

Scope is exploration only, in two groups:
  · Ruins        — stories with Trigger=EVENTTRIGGER_RUINS_EXPLORED, the
                   pop-up you get when a unit explores a Ruins tile.
  · Expeditions  — stories with Class=EVENTCLASS_EXPLORING, the scripted
                   "send a character off exploring distant lands" chains
                   (some are EventLink follow-ups to an earlier expedition).

Reuses the mission-event humanizer (build_missions) so reward/option/condition
text matches the Rally / Hold Court / Steal Research pages exactly, and layers
on the trigger + timing metadata the user asked for (when can it fire, DLC,
repeat rules, background reading link).

Two option syntaxes exist in the XML and both appear here:
  · old:  <aeOptions><zValue>EVENTOPTION_*</zValue>  → eventOption.xml entries
  · new:  <EventOptions><EventOption> with inline Text + <SubjectBonuses>
We normalise both into one {text, requirements, outcomes} shape.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_missions as m  # noqa: E402  reuse the mission-event humanizer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "events.json"

STORY_FILES = (
    "eventStory.xml", "eventStory-sap.xml", "eventStory-btt.xml",
    "eventStory-eoti.xml", "eventStory-wd.xml", "eventStory-wog.xml",
)
OPT_FILES = (
    "eventOption.xml", "eventOption-sap.xml", "eventOption-btt.xml",
    "eventOption-eoti.xml", "eventOption-wd.xml", "eventOption-wog.xml",
)
TEXT_FILES = (
    "text-eventStory.xml", "text-eventStory-sap.xml", "text-eventStory-eoti.xml",
    "text-eventStory-wd.xml", "text-eventStory-wog.xml", "text-eventStoryTitle.xml",
    "text-eventStoryTitle-sap.xml", "text-eventOption.xml", "text-eventOption-sap.xml",
    "text-trait.xml", "text-unit.xml", "text-infos.xml",
)

# Trigger token → readable "what makes this fire" label.
TRIGGER_LABELS = {
    "EVENTTRIGGER_RUINS_EXPLORED": "Exploring ruins",
    "EVENTTRIGGER_NEW_TURN": "On a new turn",
    "EVENTTRIGGER_NEW_TURN_CHARACTER": "On a new turn (character)",
}

# GameContentRequired token → DLC / content-pack name.
DLC_LABELS = {
    "EVENTPACK_RELIGION": "Religion event pack",
    "EVENTPACK_SCANDAL": "Behind the Throne",
    "EMPIRES_OF_THE_INDUS": "Empires of the Indus",
    "WONDERS_DYNASTIES": "Wonders & Dynasties",
    "AKSUM": "Sacred & the Profane (Aksum)",
}


def dlc_label(token: str) -> str | None:
    if not token:
        return None
    return DLC_LABELS.get(token, m._tok(token, "EVENTPACK_", "EVENTCLASS_"))


def trigger_label(trigger: str, link_prereq: str | None) -> str:
    if link_prereq:
        return "Expedition follow-up"
    if not trigger:
        return "Expedition"
    return TRIGGER_LABELS.get(trigger, m._tok(trigger, "EVENTTRIGGER_"))


def conditions(s: ET.Element) -> list[str]:
    """Gating tests that must hold for the story to be eligible. SubjectExtras
    must be true; SubjectAny is an at-least-one-of group. Deduped, readable."""
    out: list[str] = []
    for tag in ("SubjectExtras", "SubjectAny"):
        for p in s.findall(f"{tag}/Pair"):
            second = p.findtext("Second")
            if second:
                out.append(m.subject_label(second))
    # NotExtras read as negations.
    for p in s.findall("SubjectNotExtras/Pair"):
        second = p.findtext("Second")
        if second:
            out.append("Not " + m.subject_label(second))
    seen: set[str] = set()
    return [c for c in out if not (c in seen or seen.add(c))]


def timing(s: ET.Element) -> dict:
    """Surface the when-can-this-fire metadata as a flat, only-present dict."""
    out: dict = {}
    def ival(tag: str):
        v = s.findtext(tag)
        return int(v) if v and v.strip() and v.strip() != "0" else None
    if (v := ival("iMinTurns")) is not None:
        out["minTurns"] = v
    if (v := ival("iMaxTurns")) is not None:
        out["maxTurns"] = v
    if (v := ival("iMinLeader")) is not None:
        out["minLeader"] = v
    rep = s.findtext("iRepeatTurns")
    if rep and rep.strip():
        r = int(rep)
        out["repeat"] = "Once per game" if r < 0 else f"Every {r} turns"
    if (law := s.findtext("LawPrereq")):
        out["law"] = m._tok(law, "LAW_")
    if (opp := s.findtext("MinOpponentLevel")):
        out["minOpponentLevel"] = m._tok(opp, "OPPONENTLEVEL_")
    return out


def options(s: ET.Element, eopt_idx: dict, bonus_idx: dict, text: dict) -> list[dict]:
    """Both option syntaxes → [{text, requirements, outcomes}]."""
    out: list[dict] = []

    def link_of(opt: ET.Element):
        link = opt.findtext("EventLinkAdd")
        return link if link and link != "NONE" else None

    # Old syntax: list of eventOption references.
    for oz in s.findall("aeOptions/zValue"):
        opt = eopt_idx.get(oz.text or "")
        if opt is None:
            continue
        out.append({
            "text": m.clean_text(text.get(opt.findtext("Text") or "", "")),
            "requirements": m.option_requirements(opt),
            "outcomes": m.option_outcomes(opt, eopt_idx, bonus_idx, text),
            "linkAdd": link_of(opt),
            "raw": m.option_raw(opt, eopt_idx, bonus_idx),
        })

    # New syntax: inline EventOption with SubjectBonuses pairs.
    for opt in s.findall("EventOptions/EventOption"):
        rewards: list[dict] = []
        for p in opt.findall("SubjectBonuses/Pair"):
            rewards += m.humanize_bonus(p.findtext("Second") or "", bonus_idx, text)
        out.append({
            "text": m.clean_text(text.get(opt.findtext("Text") or "", "")),
            "requirements": m.option_requirements(opt),
            "outcomes": [{"probability": 1.0, "weight": None, "rewards": rewards, "label": None}],
            "linkAdd": link_of(opt),
            "raw": m.option_raw(opt, eopt_idx, bonus_idx),
        })

    return out


def build_event(s: ET.Element, group_weight: int, eopt_idx: dict,
                bonus_idx: dict, text: dict) -> dict:
    zt = s.findtext("zType") or ""
    weight = int(s.findtext("iWeight") or "0")
    link_prereq = s.findtext("EventLinkPrereq") or None

    guaranteed: list[str] = []
    for bz in s.findall("aeBonuses/zValue"):
        if bz.text and bz.text != "NONE":
            guaranteed += m.humanize_bonus(bz.text, bonus_idx, text)

    url = (s.findtext("zEventURL") or "").strip() or None
    prob = s.findtext("iProb")
    # NOTE: no "text" field — story narrative bodies stay an in-game discovery;
    # the reference renders title + choices only.
    return {
        "id": zt,
        "name": m.clean_text(text.get(s.findtext("Name") or "", m._tok(zt, "EVENTSTORY_"))),
        "weight": weight,
        # Follow-ups fire deterministically via a chain link, not from the
        # weighted pool, so they have no meaningful share.
        "share": None if link_prereq else (weight / group_weight if group_weight else 0),
        "prob": int(prob) if prob and prob.strip() and prob.strip() != "0" else None,
        "trigger": trigger_label(s.findtext("Trigger") or "", link_prereq),
        "isFollowup": bool(link_prereq),
        "linkPrereq": link_prereq,
        "dlc": dlc_label(s.findtext("GameContentRequired") or ""),
        "url": url,
        "timing": timing(s),
        "conditions": conditions(s),
        "guaranteed": guaranteed,
        "options": options(s, eopt_idx, bonus_idx, text),
    }


def main() -> int:
    text = m.load_text(*TEXT_FILES)
    story_idx = m.index_many(*STORY_FILES)
    eopt_idx = m.index_many(*OPT_FILES)
    bonus_idx = m.bonus_index()

    def story_link_adds(s: ET.Element) -> set[str]:
        """Every EventLink a story can set — story-level + each of its options."""
        links: set[str] = set()
        for la in [s.findtext("EventLinkAdd")]:
            if la and la != "NONE":
                links.add(la)
        for oz in s.findall("aeOptions/zValue"):
            opt = eopt_idx.get(oz.text or "")
            la = opt.findtext("EventLinkAdd") if opt is not None else None
            if la and la != "NONE":
                links.add(la)
        for opt in s.findall("EventOptions/EventOption"):
            la = opt.findtext("EventLinkAdd")
            if la and la != "NONE":
                links.add(la)
        return links

    by_prereq: dict[str, list[ET.Element]] = {}
    for s in story_idx.values():
        lp = s.findtext("EventLinkPrereq")
        if lp and lp != "NONE":
            by_prereq.setdefault(lp, []).append(s)

    # Expeditions: the EXPLORING class (incl. weight-0 follow-ups). Ruins: the
    # RUINS_EXPLORED pop-ups PLUS the chain follow-ups they link to (transitive
    # closure over EventLinkAdd→EventLinkPrereq), which carry no weight of their
    # own so wouldn't otherwise surface.
    expeditions = [s for s in story_idx.values() if (s.findtext("Class") or "") == "EVENTCLASS_EXPLORING"]
    exp_ids = {s.findtext("zType") for s in expeditions}

    ruins = [s for s in story_idx.values()
             if (s.findtext("Trigger") or "") == "EVENTTRIGGER_RUINS_EXPLORED"]
    ruin_ids = {s.findtext("zType") for s in ruins}
    frontier = list(ruins)
    while frontier:
        links: set[str] = set()
        for s in frontier:
            links |= story_link_adds(s)
        nxt = []
        for ln in links:
            for s in by_prereq.get(ln, []):
                zt = s.findtext("zType")
                if zt not in ruin_ids and zt not in exp_ids:
                    ruin_ids.add(zt); ruins.append(s); nxt.append(s)
        frontier = nxt

    # Map every EventLinkPrereq to the story (id+name) that needs it — used to
    # resolve where a choice's EventLinkAdd leads. Spans ALL stories so a chain
    # link resolves even if the target sits in the other group.
    def story_name(s: ET.Element) -> str:
        zt = s.findtext("zType") or ""
        return m.clean_text(text.get(s.findtext("Name") or "", m._tok(zt, "EVENTSTORY_")))
    prereq_targets: dict[str, list[dict]] = {}
    for s in story_idx.values():
        lp = s.findtext("EventLinkPrereq")
        if lp and lp != "NONE":
            prereq_targets.setdefault(lp, []).append({"id": s.findtext("zType") or "", "name": story_name(s)})

    def group(stories: list[ET.Element], key: str, label: str, blurb: str) -> dict:
        total = sum(int(s.findtext("iWeight") or "0") for s in stories) or 1
        events = [build_event(s, total, eopt_idx, bonus_idx, text) for s in stories]
        events.sort(key=lambda e: (e["isFollowup"], -e["weight"], e["name"]))
        return {"key": key, "label": label, "blurb": blurb,
                "totalWeight": total, "events": events}

    sections = [
        group(ruins, "ruins", "Ruins",
              "Fires when one of your units explores a Ruins tile. One story is "
              "drawn by weight from those whose conditions are met; the percentage "
              "is each story's share of the eligible-by-weight pool."),
        group(expeditions, "expeditions", "Expeditions",
              "The scripted “send a character off to explore distant lands” chains. "
              "Some entries are follow-ups that only fire after an earlier expedition "
              "via an event link."),
    ]

    # ── Wire up chains ──────────────────────────────────────────────────────
    # Forward: a choice with linkAdd L "may trigger" each story whose prereq is L.
    # Backward: a follow-up (linkPrereq L) "follows from" each event whose choice
    # adds L. Self-links are dropped.
    all_events = [e for sec in sections for e in sec["events"]]
    add_sources: dict[str, list[dict]] = {}
    for e in all_events:
        for opt in e["options"]:
            la = opt.get("linkAdd")
            if la:
                opt["leadsTo"] = [t for t in prereq_targets.get(la, []) if t["id"] != e["id"]]
                if opt["leadsTo"]:
                    add_sources.setdefault(la, []).append({"id": e["id"], "name": e["name"]})
    for e in all_events:
        lp = e.get("linkPrereq")
        e["followsFrom"] = [src for src in add_sources.get(lp, []) if src["id"] != e["id"]] if lp else []

    # ── Potential follow-ups via memories (canLeadTo) ───────────────────────
    # An option that grants a memory makes its holder eligible for any story
    # whose cast subjects require it (subject.xml MemoryPrereq) — an
    # eligibility hint, NOT a guaranteed chain like leadsTo. MemoryInvalid
    # consumers are blockers, deliberately not listed.
    # Locating targets: the two groups here anchor by id; harvest/study pages
    # use their builders' anchor schemes; everything else lives in a
    # story-events category part. Part slugs come from the generated
    # search.json — `make data` runs build_events before build_story_events,
    # so this read can be one build stale; it self-corrects next run
    # (category part slugs only move when the game's taxonomy shifts).
    CAN_LEAD_CAP = 6
    chain = m.memory_chain()
    search_path = ROOT / "src" / "data" / "story-events" / "search.json"
    part_of: dict[str, str] = {}
    if search_path.exists():
        for row in json.loads(search_path.read_text()):
            part_of[row["i"]] = row["s"]

    def can_location(zid: str) -> dict | None:
        if zid in ruin_ids:
            return {"ext": "ruin-events", "anchor": zid}
        if zid in exp_ids:
            return {"ext": "expedition-events", "anchor": zid}
        s = story_idx.get(zid)
        cls = (s.findtext("Class") or "") if s is not None else ""
        if cls == "EVENTCLASS_HARVESTING":
            return {"ext": "harvest-events",
                    "anchor": zid.replace("EVENTSTORY_HARVEST_", "").replace("EVENTSTORY_", "").lower()}
        if cls == "EVENTCLASS_STUDY":
            return {"ext": "study-events", "anchor": zid.replace("EVENTSTORY_STUDY_", "").lower()}
        if zid in part_of:
            return {"cat": part_of[zid]}
        return None

    for e in all_events:
        for opt in e["options"]:
            toks: list[str] = []
            for oc in opt.get("outcomes", []):
                for r in oc.get("rewards", []):
                    mem = r.get("memory")
                    if mem and mem not in toks:
                        toks.append(mem)
            ids: list[str] = []
            for t in toks:
                ids += chain.get(t, {}).get("enables", [])
            targets = []
            for zid in sorted(set(ids)):
                if zid == e["id"]:
                    continue
                loc = can_location(zid)
                if loc is None or story_idx.get(zid) is None:
                    continue
                targets.append({"id": zid, "name": story_name(story_idx[zid]), **loc})
            if targets:
                opt["canLeadTo"] = targets[:CAN_LEAD_CAP]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sections, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)}")
    for sec in sections:
        opt_total = sum(len(e["options"]) for e in sec["events"])
        print(f"  · {sec['label']:12} {len(sec['events']):3} events · {opt_total} options")
    return 0


if __name__ == "__main__":
    sys.exit(main())
