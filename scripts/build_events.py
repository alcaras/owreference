#!/usr/bin/env python3
"""Build src/data/events.json — the exploration + wonder event pages.

Three groups, each its own page:
  · Ruins        — stories with Trigger=EVENTTRIGGER_RUINS_EXPLORED, the
                   pop-up you get when a unit explores a Ruins tile.
  · Expeditions  — stories with Class=EVENTCLASS_EXPLORING, the scripted
                   "send a character off exploring distant lands" chains
                   (some are EventLink follow-ups to an earlier expedition).
  · Wonders      — the decision events that can fire when a wonder completes
                   (Trigger=EVENTTRIGGER_IMPROVEMENT_FINISHED on a bWonder
                   improvement, 2+ options — see wonder_events_util.py).
  · Projects     — the decision events fired by finishing a production Project
                   (Trigger=EVENTTRIGGER_PRODUCTION_PROJECT, 2+ options — see
                   project_events_util.py).
  · Buildings    — the decision events fired by finishing a NON-wonder building
                   (Trigger=EVENTTRIGGER_IMPROVEMENT_FINISHED on an ordinary
                   improvement, 2+ options — see building_events_util.py).
  · Family       — stories tied to a specific family class (non-exclusive
                   cross-cut — see family_events_util.py; also on Story Events).

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
import wonder_events_util as weu  # noqa: E402  shared wonder-event definition
import project_events_util as peu  # noqa: E402  shared project-event definition
import building_events_util as beu  # noqa: E402  shared building-event definition
import family_events_util as feu  # noqa: E402  shared family-event definition
import blessing_events_util as bcu  # noqa: E402  shared blessed/cursed definition
import trait_removal_util as tru  # noqa: E402  shared trait-removal definition

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
    "text-eventStoryTitle-sap.xml", "text-eventStoryTitle-btt.xml",
    "text-eventOption.xml", "text-eventOption-sap.xml", "text-eventOption-btt.xml",
    "text-eventOption-hittite.xml",
    # QUIRK: wd/wog packs ship story+option text in these oddly-named files.
    "text-wonders-dynasties-events.xml", "text-calamities-events.xml",
    "text-trait.xml", "text-unit.xml", "text-infos.xml",
    "text-improvement.xml", "text-improvement-sap.xml", "text-improvement-hittite.xml",
    # (wonder/building improvement names; family-class names live in text-infos)
    "text-project.xml", "text-project-event.xml", "text-project-event-sap.xml",
    "text-project-event-wog.xml", "text-eoti.xml", "text-misc-btt.xml",  # project names for the Project Events group
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


# ── Competitive-mode eligibility ──────────────────────────────────────────
# Tournament ("Competitive Mode") games turn on the Competitive Events option,
# which removes the swingy/random stories tagged GAMEOPTION_COMPETITIVE_EVENTS
# in aeGameOptionInvalid (~127 — tribe-alliance gifts, Neighbors, …). An event
# is "CM eligible" iff it is NOT so tagged.
def cm_ineligible(s: ET.Element) -> bool:
    return any((v.text or "") == "GAMEOPTION_COMPETITIVE_EVENTS"
               for v in s.findall("aeGameOptionInvalid/zValue"))


# ── Class-level earliest-fire turn ────────────────────────────────────────
# An event with no iMinTurns of its own still can't fire before its event class
# becomes active (eventClass.xml iMinTurns — Courtier 30, Mercenary 20, …), so
# fold that into the per-event earliest turn.
_CLASS_MIN_TURNS: dict[str, int] | None = None
def _class_min_turns() -> dict[str, int]:
    global _CLASS_MIN_TURNS
    if _CLASS_MIN_TURNS is None:
        _CLASS_MIN_TURNS = {}
        p = m.XML_DIR / "eventClass.xml"
        if p.exists():
            for e in ET.parse(p).getroot().findall("Entry"):
                z, mt = e.findtext("zType"), (e.findtext("iMinTurns") or "").strip()
                if z and mt and mt != "0":
                    _CLASS_MIN_TURNS[z] = int(mt)
    return _CLASS_MIN_TURNS


def timing(s: ET.Element) -> dict:
    """Surface the when-can-this-fire metadata as a flat, only-present dict."""
    out: dict = {}
    def ival(tag: str):
        v = s.findtext(tag)
        return int(v) if v and v.strip() and v.strip() != "0" else None
    if (v := ival("iMinTurns")) is not None:
        out["minTurns"] = v
    # Fold in the event class's own earliest-active turn (the effective floor).
    class_min = _class_min_turns().get((s.findtext("Class") or "").strip())
    if class_min:
        out["minTurns"] = max(out.get("minTurns", 0), class_min)
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

    def link_of(opt: ET.Element) -> list[str]:
        """Every event link this option adds: EventLinkAdd plus each
        EventLinkSubjectsAdd pair (e.g. Cult of Flame's Smash adds
        EVENTLINK_CLEARED_CAMP only via the subjects form)."""
        links: set[str] = set()
        la = opt.findtext("EventLinkAdd")
        if la and la != "NONE":
            links.add(la)
        for pr in opt.findall("EventLinkSubjectsAdd/Pair"):
            z = pr.findtext("zIndex")
            if z and z != "NONE":
                links.add(z)
        return sorted(links)

    # Old syntax: list of eventOption references.
    for oz in s.findall("aeOptions/zValue"):
        opt = eopt_idx.get(oz.text or "")
        if opt is None:
            continue
        out.append({
            "text": m.clean_text(text.get(opt.findtext("Text") or "", "")),
            "requirements": m.option_requirements(opt),
            "outcomes": m.option_outcomes(opt, eopt_idx, bonus_idx, text),
            "linkAdds": link_of(opt),
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
            "linkAdds": link_of(opt),
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
        # Competitive-Mode eligibility — False only for the excluded stories
        # (renderers treat anything !== false as eligible).
        "cmEligible": False if cm_ineligible(s) else None,
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

    # Wonder decision events: the choose-one pop-ups that can fire when a
    # wonder completes. Weighted-pool shares are meaningless here (each wonder's
    # event competes only against its own completion trigger, and the flat
    # +Legitimacy announcement fires regardless via bMultiples), so share is
    # dropped and the trigger label names the wonder instead.
    wonder_set = weu.wonder_ids(m.XML_DIR)
    wonder_names: dict[str, str] = {}
    for e in ET.parse(m.XML_DIR / "improvement.xml").getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        if zt in wonder_set:
            wonder_names[zt] = m.clean_text(text.get(e.findtext("Name") or "", m._tok(zt, "IMPROVEMENT_")))
    wonder_stories = [s for s in story_idx.values() if weu.is_wonder_decision_event(s, wonder_set)]
    wonder_events = []
    for s in wonder_stories:
        ev = build_event(s, 0, eopt_idx, bonus_idx, text)
        wid = s.findtext("TriggerData") or ""
        ev["share"] = None
        wname = wonder_names.get(wid, wid)
        ev["wonder"] = {"id": wid, "name": wname}
        # Wonder names already carry their article ("The Acropolis").
        ev["trigger"] = f"Completing {wname}" if wname.lower().startswith("the ") else f"Completing the {wname}"
        wonder_events.append(ev)
    wonder_events.sort(key=lambda e: (e["wonder"]["name"], e["name"]))

    # Project decision events: pop-ups fired by finishing a production Project.
    # Two kinds (peu.is_one_time): one-time building projects (Archive, Forum,
    # Walls, …) behave like wonder events; repeatable projects (Festival, Hunt,
    # Olympiad) are event generators whose stories share a weighted pool, so we
    # compute each story's share WITHIN its project's pool.
    proj_idx = peu.project_index(m.XML_DIR)
    def project_name(pid: str) -> str:
        e = proj_idx.get(pid)
        key = e.findtext("Name") if e is not None else None
        return m.clean_text(text.get(key or "", m._tok(pid, "PROJECT_")))
    proj_stories = [s for s in story_idx.values() if peu.is_project_event(s)]
    pool_total: dict[str, int] = {}
    for s in proj_stories:
        pid = s.findtext("TriggerData") or ""
        pool_total[pid] = pool_total.get(pid, 0) + max(1, int(s.findtext("iWeight") or "0"))
    project_events = []
    for s in proj_stories:
        ev = build_event(s, 0, eopt_idx, bonus_idx, text)
        pid = s.findtext("TriggerData") or ""
        pentry = proj_idx.get(pid)
        one_time = peu.is_one_time(pentry)
        pname = project_name(pid)
        ev["project"] = {"id": pid, "name": pname, "oneTime": one_time}
        # Pool share is meaningful only for repeatable multi-story pools.
        if one_time or pool_total.get(pid, 0) <= max(1, ev["weight"]):
            ev["share"] = None
        else:
            ev["share"] = max(1, ev["weight"]) / pool_total[pid]
        art = "an" if pname[:1].upper() in "AEIOU" else "a"
        ev["trigger"] = (f"Completing the {pname}" if one_time
                         else f"Completing {art} {pname}")
        project_events.append(ev)
    # One-time building projects first (alphabetical), then repeatable pools.
    project_events.sort(key=lambda e: (not e["project"]["oneTime"], e["project"]["name"], -e["weight"], e["name"]))

    # Building decision events: finishing a NON-wonder improvement. Each
    # building has its own weighted pool (a Quarry rolls Ancient Statue vs the
    # Dinosaur-Bones set vs Disturbed Rest), so share is computed within the
    # building's pool, like the repeatable projects.
    imp_idx = beu.improvement_index(m.XML_DIR)
    imp_ids = set(imp_idx.keys())
    def building_name(iid: str) -> str:
        e = imp_idx.get(iid)
        raw = text.get(e.findtext("Name") or "", "") if e is not None else ""
        return beu.clean_improvement_name(raw) or m.clean_text(m._tok(iid, "IMPROVEMENT_"))
    building_stories = [s for s in story_idx.values() if beu.is_building_event(s, wonder_set, imp_ids)]
    bpool_total: dict[str, int] = {}
    for s in building_stories:
        bid = s.findtext("TriggerData") or ""
        bpool_total[bid] = bpool_total.get(bid, 0) + max(1, int(s.findtext("iWeight") or "0"))
    building_events = []
    for s in building_stories:
        ev = build_event(s, 0, eopt_idx, bonus_idx, text)
        bid = s.findtext("TriggerData") or ""
        bname = building_name(bid)
        ev["building"] = {"id": bid, "name": bname}
        ev["share"] = (max(1, ev["weight"]) / bpool_total[bid]
                       if bpool_total.get(bid, 0) > max(1, ev["weight"]) else None)
        ev["trigger"] = f"Completing the {bname}"
        building_events.append(ev)
    building_events.sort(key=lambda e: (e["building"]["name"], -e["weight"], e["name"]))

    # Family decision events: stories tied to a specific family CLASS. This is a
    # NON-exclusive cross-cut (they also live under their class on Story Events),
    # so build_story_events does NOT drop them. Each carries the class(es) it
    # references; the trigger label names the family class.
    fam_names = {c: m.clean_text(text.get(f"TEXT_FAMILYCLASS_{c}", c.title())) for c in feu.CLASSES}
    family_stories = [s for s in story_idx.values() if feu.is_family_event(s)]
    family_events = []
    for s in family_stories:
        ev = build_event(s, 0, eopt_idx, bonus_idx, text)
        classes = feu.family_classes(s)
        names = [fam_names[c] for c in classes]
        ev["family"] = {"classes": classes, "names": names}
        ev["share"] = None  # not a completion pool; raw weight still shown
        ev["trigger"] = " · ".join(names) + (" family" if len(names) == 1 else " families")
        family_events.append(ev)
    family_events.sort(key=lambda e: (e["family"]["names"][0] if e["family"]["names"] else "", -e["weight"], e["name"]))

    # Blessed / Cursed: the two divine-favour traits. Like family events these
    # are a NON-exclusive cross-cut (the stories keep their own class on Story
    # Events), so build_story_events does not drop them. Each event records
    # whether it needs the trait, grants it, or removes it.
    blessing_sections = {}
    for key in ("BLESSED", "CURSED"):
        spec = bcu.TRAITS[key]
        evs = []
        for st in story_idx.values():
            rel = bcu.relation(st, key, eopt_idx, bonus_idx)
            if not rel:
                continue
            ev = build_event(st, 0, eopt_idx, bonus_idx, text)
            ev["blessing"] = rel
            ev["share"] = None
            bits = []
            if rel["needs"]:
                bits.append(f"Requires {spec['label']}")
            if rel["grants"]:
                bits.append(f"Can grant {spec['label']}")
            if rel["removes"]:
                bits.append(f"Can remove {spec['label']}")
            ev["trigger"] = " · ".join(bits)
            evs.append(ev)
        # gateway stories first (they need it), then the ones that hand it out
        evs.sort(key=lambda e: (not e["blessing"]["needs"], -e["weight"], e["name"]))
        blessing_sections[key] = evs

    # Trait removal: every story that can take a trait OFF a character, grouped
    # by the trait removed. Two paths (see trait_removal_util): a bonus listing
    # the trait in aeRemoveTraits, or one ADDING a trait whose aeTraitReplaces
    # names it. Both walk one level into aiEventOptionProb, where several
    # stories hide their per-trait variants.
    trait_roots = [m.parse(f) for f in ("trait.xml", "trait-btt.xml", "trait-eoti.xml",
                                        "trait-sap.xml", "trait-wd.xml", "trait-wog.xml")
                   if (m.XML_DIR / f).exists()]
    replaces = tru.replacement_map(trait_roots)
    # trait display names: GenderedName points at a GENDERED_TEXT_* key whose
    # masculine variant is the real TEXT_* key
    gendered: dict[str, str] = {}
    for gf in sorted(m.XML_DIR.glob("genderedText*.xml")):
        for e in ET.parse(gf).getroot().findall("Entry"):
            zid = e.findtext("zType") or ""
            for pair in e.findall("Texts/Pair"):
                if (pair.findtext("zIndex") or "").endswith("MASCULINE"):
                    gendered[zid] = pair.findtext("zValue") or ""
                    break
    trait_name = {}
    for root in trait_roots:
        for e in root.findall("Entry"):
            z = e.findtext("zType")
            if z:
                key = e.findtext("GenderedName") or e.findtext("Name") or ""
                trait_name[z] = m.clean_text(text.get(gendered.get(key, key), "")) or \
                    z.replace("TRAIT_", "").replace("_", " ").title()

    removal_events = []
    for st in story_idx.values():
        rem = tru.removals(st, eopt_idx, bonus_idx, replaces)
        if not rem:
            continue
        for trait_id, how in sorted(rem.items(), key=lambda kv: trait_name.get(kv[0], kv[0])):
            ev = build_event(st, 0, eopt_idx, bonus_idx, text)
            tname = trait_name.get(trait_id, trait_id)
            ev["removes"] = {
                "id": trait_id, "name": tname,
                "direct": how["direct"], "variant": how["variant"],
                "via": [trait_name.get(v, v) for v in how["via"]],
            }
            ev["share"] = None
            bits = [f"Removes {tname}"]
            if how["via"]:
                bits.append("by granting " + " / ".join(ev["removes"]["via"]))
            if how["variant"] and not how["direct"]:
                pass
            ev["trigger"] = " · ".join(bits)
            # the same story can clear several traits — keep ids unique per row
            ev["id"] = f"{ev['id']}::{trait_id}"
            removal_events.append(ev)
    removal_events.sort(key=lambda e: (e["removes"]["name"], not e["removes"]["direct"],
                                       -e["weight"], e["name"]))

    # Compact, trait-grouped projection — 2,000+ full event cards would be
    # unreadable, so this page links each story to where it already renders.
    tr_search = ROOT / "src" / "data" / "story-events" / "search.json"
    tr_part = {}
    if tr_search.exists():
        for row in json.loads(tr_search.read_text()):
            tr_part[row["i"]] = row["s"]
    tr_groups: dict[str, dict] = {}
    for ev in removal_events:
        sid = ev["id"].split("::")[0]
        r = ev["removes"]
        grp = tr_groups.setdefault(r["id"], {
            "id": r["id"], "name": r["name"],
            # same convention as traits.json, so /trait-removal/<slug> lines up
            # with the trait's own slug elsewhere on the site
            "slug": r["id"].replace("TRAIT_", "").lower().replace("_", "-"),
            "direct": [], "via": [],
        })
        row = {
            "id": sid, "name": ev["name"], "weight": ev["weight"],
            "dlc": ev["dlc"], "variant": r["variant"], "via": r["via"],
            "part": tr_part.get(sid),
        }
        (grp["direct"] if r["direct"] else grp["via"]).append(row)
    tr_out = sorted(tr_groups.values(), key=lambda g: g["name"])
    (ROOT / "src" / "data" / "trait_removal.json").write_text(
        json.dumps({
            "traits": tr_out,
            "counts": {
                "traits": len(tr_out),
                "direct": sum(len(g["direct"]) for g in tr_out),
                "via": sum(len(g["via"]) for g in tr_out),
            },
        }, indent=2, sort_keys=True) + "\n")
    print(f"  · Trait removal  {len(tr_out)} traits · "
          f"{sum(len(g['direct']) for g in tr_out)} direct · "
          f"{sum(len(g['via']) for g in tr_out)} via replacement"
          "  → src/data/trait_removal.json")

    sections = [
        group(ruins, "ruins", "Ruins",
              "Fires when one of your units explores a Ruins tile. One story is "
              "drawn by weight from those whose conditions are met; the percentage "
              "is each story's share of the eligible-by-weight pool."),
        group(expeditions, "expeditions", "Expeditions",
              "The scripted “send a character off to explore distant lands” chains. "
              "Some entries are follow-ups that only fire after an earlier expedition "
              "via an event link."),
        {"key": "wonders", "label": "Wonders", "totalWeight": 0,
         "blurb": "Decision events that can fire when a wonder is completed.",
         "events": wonder_events},
        {"key": "projects", "label": "Projects", "totalWeight": 0,
         "blurb": "Decision events fired by finishing a production Project.",
         "events": project_events},
        {"key": "buildings", "label": "Buildings", "totalWeight": 0,
         "blurb": "Decision events fired by finishing a (non-wonder) building.",
         "events": building_events},
        {"key": "family", "label": "Family", "totalWeight": 0,
         "blurb": "Stories tied to a specific family class.",
         "events": family_events},
        {"key": "blessed", "label": "Blessed", "totalWeight": 0,
         "blurb": "Stories that require, grant or remove the Blessed trait.",
         "events": blessing_sections["BLESSED"]},
        {"key": "cursed", "label": "Cursed", "totalWeight": 0,
         "blurb": "Stories that require, grant or remove the Cursed trait.",
         "events": blessing_sections["CURSED"]},
    ]

    # ── Locate any story by id ──────────────────────────────────────────────
    # A chain link (leadsTo / followsFrom / canLeadTo) can point at a story that
    # renders on ANY of the five event pages, not just this one. Resolve each to
    # {ext, anchor} (a dedicated page) or {cat} (a story-events category part) so
    # the page builds a real cross-page href instead of a dead same-page anchor.
    # Part slugs come from the generated story-events/search.json — `make data`
    # runs build_story_events before build_events, so this read is fresh.
    search_path = ROOT / "src" / "data" / "story-events" / "search.json"
    part_of: dict[str, str] = {}
    if search_path.exists():
        for row in json.loads(search_path.read_text()):
            part_of[row["i"]] = row["s"]

    wonder_event_ids = {e["id"] for e in wonder_events}
    project_event_ids = {e["id"] for e in project_events}
    building_event_ids = {e["id"] for e in building_events}
    # Family events are NOT an exclusive home (non-exclusive cross-cut), so a
    # chain link to one still resolves to its primary page — not listed here.

    def can_location(zid: str) -> dict | None:
        if zid in ruin_ids:
            return {"ext": "ruin-events", "anchor": zid}
        if zid in exp_ids:
            return {"ext": "expedition-events", "anchor": zid}
        if zid in wonder_event_ids:
            return {"ext": "wonder-events", "anchor": zid}
        if zid in project_event_ids:
            return {"ext": "project-events", "anchor": zid}
        if zid in building_event_ids:
            return {"ext": "building-events", "anchor": zid}
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

    def located(ref: dict) -> dict:
        """Tag a {id, name} chain ref with its page location (if resolvable)."""
        loc = can_location(ref["id"])
        return {**ref, **loc} if loc else dict(ref)

    # ── Wire up chains ──────────────────────────────────────────────────────
    # Forward: a choice with linkAdd L "may trigger" each story whose prereq is L.
    # Backward: a follow-up (linkPrereq L) "follows from" each event whose choice
    # adds L. Self-links are dropped. Every ref carries its page location so the
    # link resolves even when the target lives on a different page.
    all_events = [e for sec in sections for e in sec["events"]]
    add_sources: dict[str, list[dict]] = {}
    for e in all_events:
        for opt in e["options"]:
            lts: list[dict] = []
            for la in opt.get("linkAdds") or []:
                for t in prereq_targets.get(la, []):
                    if t["id"] != e["id"] and all(x["id"] != t["id"] for x in lts):
                        lts.append(located(t))
                if any(t["id"] != e["id"] for t in prereq_targets.get(la, [])):
                    add_sources.setdefault(la, []).append({"id": e["id"], "name": e["name"]})
            if lts:
                opt["leadsTo"] = lts
    for e in all_events:
        lp = e.get("linkPrereq")
        ff: list[dict] = []
        for src in (add_sources.get(lp, []) if lp else []):
            if src["id"] != e["id"] and all(x["id"] != src["id"] for x in ff):
                ff.append(located(src))
        e["followsFrom"] = ff

    # ── Potential follow-ups via memories (canLeadTo) ───────────────────────
    # An option that grants a memory makes its holder eligible for any story
    # whose cast subjects require it (subject.xml MemoryPrereq) — an
    # eligibility hint, NOT a guaranteed chain like leadsTo. MemoryInvalid
    # consumers are blockers, deliberately not listed.
    CAN_LEAD_CAP = 6
    chain = m.memory_chain()

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
