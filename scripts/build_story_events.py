#!/usr/bin/env python3
"""Build src/data/story-events/ — the general Story Events browser.

Covers EVERY EventStory entry across the base game + DLC files EXCEPT the ones
already rendered by the four specialized pages:
  · Ruins        — Trigger=EVENTTRIGGER_RUINS_EXPLORED + chain follow-ups
                   (same transitive closure build_events.py uses)  → /ruin-events
  · Expeditions  — Class=EVENTCLASS_EXPLORING                      → /expedition-events
  · Harvest      — Class=EVENTCLASS_HARVESTING                     → /harvest-events
  · Study        — Class=EVENTCLASS_STUDY                          → /study-events (+ /tutor-events)

Categories come from the game's own taxonomy, never invented:
  · Class    — the EVENTCLASS_* pool the story is drawn from (eventClass.xml
               carries the per-turn probability / repeat metadata, included).
  · Trigger  — for class-less stories, the EVENTTRIGGER_* moment that fires it.
  · Special  — class-less, trigger-less stories: chain follow-ups
               (EventLinkPrereq) and engine-invoked scripted stories.

Output (compact JSON, deterministic, sort_keys=True):
  src/data/story-events/index.json        — _meta + category/part catalog
  src/data/story-events/parts/<slug>.json — events for one category page
                                            (categories >400 events split
                                            alphabetically into parts)
  src/data/story-events/search.json       — lightweight client search index

Rendering helpers are REUSED from build_missions (option requirements /
outcomes / raw view / bonus humanizing) and build_events (conditions, timing,
options, DLC labels) — both import side-effect free.
"""
from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_events as bev   # noqa: E402  conditions/timing/options/dlc_label
import build_missions as m   # noqa: E402  text/index/bonus/clean_text helpers
import wonder_events_util as weu  # noqa: E402  shared wonder-event definition
import project_events_util as peu  # noqa: E402  shared project-event definition
import building_events_util as beu  # noqa: E402  shared building-event definition

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT_DIR = ROOT / "src" / "data" / "story-events"

# eventStory file → DLC pack the entry ships with (base game = None).
STORY_FILE_PACKS = (
    ("eventStory.xml", None),
    ("eventStory-sap.xml", "The Sacred and the Profane"),
    ("eventStory-btt.xml", "Behind the Throne"),
    ("eventStory-eoti.xml", "Empires of the Indus"),
    ("eventStory-wd.xml", "Wonders and Dynasties"),
    ("eventStory-wog.xml", "Wrath of Gods"),
)

TEXT_FILES = (
    # Story prose + titles (base + every DLC/scenario text file that exists).
    "text-eventStory.xml", "text-eventStory-sap.xml", "text-eventStory-btt.xml",
    "text-eventStory-eoti.xml", "text-eventStory-hittite.xml", "text-eventStory-hittite-2.xml",
    "text-eventStoryTitle.xml", "text-eventStoryTitle-sap.xml",
    "text-eventStoryTitle-btt.xml", "text-eventStoryTitle-hittite.xml",
    # QUIRK: the wd/wog packs do NOT ship text-eventStory-wd/-wog files — their
    # story/title/option text lives in these two oddly-named files instead.
    "text-wonders-dynasties-events.xml", "text-calamities-events.xml",
    # Option prose.
    "text-eventOption.xml", "text-eventOption-sap.xml",
    "text-eventOption-btt.xml", "text-eventOption-hittite.xml",
    # Reward / gating vocabulary.
    "text-trait.xml", "text-unit.xml", "text-infos.xml", "text-subject.xml",
    # TriggerData vocabulary (mission results, improvements, projects, …).
    "text-mission.xml", "text-missionResult.xml", "text-missionResult-sap.xml",
    "text-missionResult-btt.xml", "text-missionResult-wog.xml",
    "text-improvement.xml", "text-improvement-sap.xml", "text-tech.xml",
    "text-project.xml", "text-project-event.xml", "text-project-event-sap.xml",
    "text-project-event-wog.xml", "text-stat.xml",
)

# Big categories get split alphabetically into parts of roughly this size so
# no generated HTML page balloons past ~400 event cards.
SPLIT_THRESHOLD = 400
PART_TARGET = 300

# Token-derived labels that need a human touch (game-native names, not invented
# taxonomy — EP = the optional "event pack" toggles in game setup).
CLASS_LABEL_OVERRIDES = {
    "EVENTCLASS_EP_RELIGION": "Religion (Event Pack)",
}

SPECIAL_CATS = {
    "FOLLOWUP": ("follow-ups", "Chain Follow-ups",
                 "Stories with no class or trigger of their own — they only fire as the "
                 "next link of an event chain (EventLinkPrereq), set up by an earlier "
                 "story's choice."),
    "SCRIPTED": ("scripted", "Scripted & Special",
                 "Stories with no class, trigger, or chain link in the XML — invoked "
                 "directly by game systems (tribe diplomacy, scenario scripts, traits, "
                 "and other engine hooks)."),
}


def slug_of(token: str, prefix: str) -> str:
    return token.replace(prefix, "", 1).lower().replace("_", "-")


def load_stories() -> tuple[dict[str, ET.Element], dict[str, str | None]]:
    """zType → Entry across all story files (first wins), plus zType → pack."""
    idx: dict[str, ET.Element] = {}
    packs: dict[str, str | None] = {}
    for fn, pack in STORY_FILE_PACKS:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            z = e.findtext("zType")
            if z and z not in idx:
                idx[z] = e
                packs[z] = pack
    return idx, packs


def event_class_meta() -> dict[str, dict]:
    """EVENTCLASS_* → eventClass.xml scheduling metadata (only-present keys)."""
    out: dict[str, dict] = {}
    p = XML_DIR / "eventClass.xml"
    if not p.exists():
        return out
    for e in ET.parse(p).getroot().findall("Entry"):
        z = e.findtext("zType")
        if not z:
            continue
        meta: dict = {}
        for tag, key in (("iLevelProb", "levelProb"), ("iPlayerProb", "playerProb"),
                         ("iCharacterProb", "characterProb"), ("iMinTurns", "minTurns"),
                         ("iMinRepeat", "minRepeat")):
            v = (e.findtext(tag) or "").strip()
            if v and v != "0":
                meta[key] = int(v)
        out[z] = meta
    return out


def trigger_data_label(td: str, text: dict) -> str | None:
    if not td or td == "NONE":
        return None
    t = text.get("TEXT_" + td)
    if t:
        return m.clean_text(t)
    head = td.split("_", 1)[0]
    return m._tok(td, head + "_")


def excluded_sets(story_idx: dict[str, ET.Element], eopt_idx: dict) -> dict[str, set[str]]:
    """ids covered by the specialized pages — same criteria those builders use."""
    study = {z for z, s in story_idx.items() if (s.findtext("Class") or "") == "EVENTCLASS_STUDY"}
    harvest = {z for z, s in story_idx.items() if (s.findtext("Class") or "") == "EVENTCLASS_HARVESTING"}
    expeditions = {z for z, s in story_idx.items() if (s.findtext("Class") or "") == "EVENTCLASS_EXPLORING"}
    wonder_set = weu.wonder_ids(m.XML_DIR)
    wonders = {z for z, s in story_idx.items() if weu.is_wonder_decision_event(s, wonder_set)}
    projects = {z for z, s in story_idx.items() if peu.is_project_event(s)}
    imp_ids = beu.improvement_ids(m.XML_DIR)
    buildings = {z for z, s in story_idx.items() if beu.is_building_event(s, wonder_set, imp_ids)}

    # Ruins + transitive chain closure, copied from build_events.py main() so
    # the excluded set matches the ruin-events page exactly.
    def _opt_links(opt: ET.Element | None) -> set[str]:
        """EventLinkAdd plus EventLinkSubjectsAdd pairs on an option."""
        links: set[str] = set()
        if opt is None:
            return links
        la = opt.findtext("EventLinkAdd")
        if la and la != "NONE":
            links.add(la)
        for pr in opt.findall("EventLinkSubjectsAdd/Pair"):
            z = pr.findtext("zIndex")
            if z and z != "NONE":
                links.add(z)
        return links

    def story_link_adds(s: ET.Element) -> set[str]:
        links: set[str] = set()
        la = s.findtext("EventLinkAdd")
        if la and la != "NONE":
            links.add(la)
        for oz in s.findall("aeOptions/zValue"):
            links |= _opt_links(eopt_idx.get(oz.text or ""))
        for opt in s.findall("EventOptions/EventOption"):
            links |= _opt_links(opt)
        return links

    by_prereq: dict[str, list[ET.Element]] = {}
    for s in story_idx.values():
        lp = s.findtext("EventLinkPrereq")
        if lp and lp != "NONE":
            by_prereq.setdefault(lp, []).append(s)

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
                if zt not in ruin_ids and zt not in expeditions:
                    ruin_ids.add(zt)
                    nxt.append(s)
        frontier = nxt

    return {"ruins": ruin_ids, "expeditions": expeditions,
            "harvest": harvest, "study": study, "wonders": wonders,
            "projects": projects, "buildings": buildings}


def categorize(s: ET.Element) -> tuple[str, str]:
    """→ (kind, token): ('class', EVENTCLASS_*) | ('trigger', EVENTTRIGGER_*)
    | ('special', FOLLOWUP|SCRIPTED)."""
    cls = (s.findtext("Class") or "").strip()
    if cls:
        return ("class", cls)
    trig = (s.findtext("Trigger") or "").strip()
    if trig:
        return ("trigger", trig)
    lp = (s.findtext("EventLinkPrereq") or "").strip()
    if lp and lp != "NONE":
        return ("special", "FOLLOWUP")
    return ("special", "SCRIPTED")


def build_event(s: ET.Element, pack: str | None, eopt_idx: dict,
                bonus_idx: dict, text: dict) -> dict:
    """One story → compact dict. Empty/None fields are omitted to keep the
    dataset small; the page renders with safe fallbacks."""
    zt = s.findtext("zType") or ""
    link_prereq = s.findtext("EventLinkPrereq")
    link_prereq = link_prereq if link_prereq and link_prereq != "NONE" else None
    trig = (s.findtext("Trigger") or "").strip()

    guaranteed: list[dict] = []
    for bz in s.findall("aeBonuses/zValue"):
        if bz.text and bz.text != "NONE":
            guaranteed += m.humanize_bonus(bz.text, bonus_idx, text)

    subjects = [m.subject_label(z.text) for z in s.findall("aeSubjects/zValue") if z.text]

    # NOTE: the story's narrative body (<Text>) is deliberately NOT emitted —
    # the reference shows title + choices only; the prose stays an in-game
    # discovery (owner's call, 2026-06).
    ev: dict = {
        "id": zt,
        "name": m.clean_text(text.get(s.findtext("Name") or "", m._tok(zt, "EVENTSTORY_"))),
        "weight": int(s.findtext("iWeight") or "0"),
        "options": bev.options(s, eopt_idx, bonus_idx, text),
    }
    if trig:
        ev["trigger"] = m._tok(trig, "EVENTTRIGGER_")
    td = trigger_data_label((s.findtext("TriggerData") or "").strip(), text)
    if td:
        ev["triggerData"] = td
    if subjects:
        ev["subjects"] = subjects
    conds = bev.conditions(s)
    if conds:
        ev["conditions"] = conds
    tim = bev.timing(s)
    if tim:
        ev["timing"] = tim
    # Competitive-Mode eligibility: only flag the exceptions (most are eligible).
    if bev.cm_ineligible(s):
        ev["cmEligible"] = False
    prob = s.findtext("iProb")
    if prob and prob.strip() and prob.strip() != "0":
        ev["prob"] = int(prob)
    dlc = bev.dlc_label(s.findtext("GameContentRequired") or "")
    if dlc:
        ev["dlc"] = dlc
    if pack:
        ev["pack"] = pack
    author = (s.findtext("zAuthor") or "").strip()
    if author:
        ev["author"] = author
    url = (s.findtext("zEventURL") or "").strip()
    if url:
        ev["url"] = url
    if link_prereq:
        ev["linkPrereq"] = link_prereq
        ev["isFollowup"] = True
    if guaranteed:
        ev["guaranteed"] = guaranteed
    return ev


def main() -> int:
    text = m.load_text(*TEXT_FILES)
    story_idx, packs = load_stories()
    eopt_idx = m.index_many(*bev.OPT_FILES)
    bonus_idx = m.bonus_index()
    class_meta = event_class_meta()

    excluded = excluded_sets(story_idx, eopt_idx)
    excluded_all: set[str] = set().union(*excluded.values())
    included = {z: s for z, s in story_idx.items() if z not in excluded_all}

    # ── Categorize ──────────────────────────────────────────────────────────
    cats: dict[tuple[str, str], list[str]] = {}
    for z, s in included.items():
        cats.setdefault(categorize(s), []).append(z)

    cat_defs: list[dict] = []
    for (kind, token), ids in cats.items():
        if kind == "class":
            slug = slug_of(token, "EVENTCLASS_")
            label = CLASS_LABEL_OVERRIDES.get(token, m._tok(token, "EVENTCLASS_"))
            blurb = None
        elif kind == "trigger":
            slug = "on-" + slug_of(token, "EVENTTRIGGER_")
            label, blurb = m._tok(token, "EVENTTRIGGER_"), None
        else:
            slug, label, blurb = SPECIAL_CATS[token]
        cat: dict = {"kind": kind, "token": token, "slug": slug, "label": label,
                     "count": len(ids), "ids": ids}
        if blurb:
            cat["blurb"] = blurb
        if kind == "class" and class_meta.get(token):
            cat["schedule"] = class_meta[token]
        cat_defs.append(cat)
    # Stable order: classes A–Z, then triggers A–Z, then specials.
    kind_rank = {"class": 0, "trigger": 1, "special": 2}
    cat_defs.sort(key=lambda c: (kind_rank[c["kind"]], c["label"]))

    slugs = [c["slug"] for c in cat_defs]
    assert len(slugs) == len(set(slugs)), "category slug collision"

    # ── Build event dicts ───────────────────────────────────────────────────
    events_by_id: dict[str, dict] = {}
    for z, s in included.items():
        events_by_id[z] = build_event(s, packs.get(z), eopt_idx, bonus_idx, text)

    # ── Split categories into parts (alphabetical by event name) ───────────
    part_of: dict[str, str] = {}  # event id → part slug
    for cat in cat_defs:
        evs = sorted((events_by_id[z] for z in cat["ids"]),
                     key=lambda e: (e["name"], e["id"]))
        n = len(evs)
        nparts = 1 if n <= SPLIT_THRESHOLD else math.ceil(n / PART_TARGET)
        size = math.ceil(n / nparts)
        parts = []
        for i in range(nparts):
            chunk = evs[i * size:(i + 1) * size]
            if not chunk:
                continue
            pslug = cat["slug"] if nparts == 1 else f"{cat['slug']}-{i + 1}"
            part = {"slug": pslug, "count": len(chunk),
                    "first": chunk[0]["name"], "last": chunk[-1]["name"]}
            if nparts > 1:
                part["label"] = (f"Part {i + 1} · "
                                 f"{chunk[0]['name'][:1].upper()}–{chunk[-1]['name'][:1].upper()}")
            parts.append(part)
            for e in chunk:
                part_of[e["id"]] = pslug
        cat["parts"] = parts
        cat["_chunks"] = [evs[i * size:(i + 1) * size] for i in range(nparts)]

    # ── Wire chains (leadsTo / followsFrom) across the whole dataset ───────
    # Location of every story an option link may point at: an included part, or
    # one of the specialized pages (ruin/expedition pages anchor cards by id,
    # harvest/study by their builders' slug schemes).
    def location(zid: str) -> dict | None:
        if zid in part_of:
            return {"cat": part_of[zid]}
        if zid in excluded["ruins"]:
            return {"ext": "ruin-events", "anchor": zid}
        if zid in excluded["expeditions"]:
            return {"ext": "expedition-events", "anchor": zid}
        if zid in excluded["harvest"]:
            return {"ext": "harvest-events",
                    "anchor": zid.replace("EVENTSTORY_HARVEST_", "").replace("EVENTSTORY_", "").lower()}
        if zid in excluded["study"]:
            return {"ext": "study-events",
                    "anchor": zid.replace("EVENTSTORY_STUDY_", "").lower()}
        if zid in excluded["wonders"]:
            return {"ext": "wonder-events", "anchor": zid}
        if zid in excluded["projects"]:
            return {"ext": "project-events", "anchor": zid}
        if zid in excluded["buildings"]:
            return {"ext": "building-events", "anchor": zid}
        return None

    def story_name(zid: str) -> str:
        s = story_idx[zid]
        return m.clean_text(text.get(s.findtext("Name") or "", m._tok(zid, "EVENTSTORY_")))

    prereq_targets: dict[str, list[str]] = {}
    for z, s in story_idx.items():
        lp = s.findtext("EventLinkPrereq")
        if lp and lp != "NONE":
            prereq_targets.setdefault(lp, []).append(z)

    add_sources: dict[str, list[str]] = {}
    def _xml_opt_links(opt):
        links = set()
        if opt is None:
            return links
        la = opt.findtext("EventLinkAdd")
        if la and la != "NONE":
            links.add(la)
        for pr in opt.findall("EventLinkSubjectsAdd/Pair"):
            zx = pr.findtext("zIndex")
            if zx and zx != "NONE":
                links.add(zx)
        return links
    for z, s in story_idx.items():
        la = s.findtext("EventLinkAdd")
        if la and la != "NONE":
            add_sources.setdefault(la, []).append(z)
        for oz in s.findall("aeOptions/zValue"):
            for l in _xml_opt_links(eopt_idx.get(oz.text or "")):
                add_sources.setdefault(l, []).append(z)
        for opt in s.findall("EventOptions/EventOption"):
            for l in _xml_opt_links(opt):
                add_sources.setdefault(l, []).append(z)

    def refs(zids: list[str], skip: str) -> list[dict]:
        out = []
        for zid in sorted(set(zids)):
            if zid == skip:
                continue
            loc = location(zid)
            if loc is None:
                continue
            out.append({"id": zid, "name": story_name(zid), **loc})
        return out

    for z, ev in events_by_id.items():
        for opt in ev["options"]:
            lts: list[dict] = []
            for la in opt.get("linkAdds") or []:
                for t in refs(prereq_targets.get(la, []), skip=z):
                    if all(x["id"] != t["id"] for x in lts):
                        lts.append(t)
            if lts:
                opt["leadsTo"] = lts
        lp = ev.get("linkPrereq")
        if lp:
            ff = refs(add_sources.get(lp, []), skip=z)
            if ff:
                ev["followsFrom"] = ff

    # ── Chains via a granted trait (not EventLink) ───────────────────────────
    # Some chains hand off through a trait rather than an EventLink: an option
    # grants TRAIT_X (its bonus's aeAddTraits), and a later story casts a subject
    # whose only gate is that trait (subject.xml TraitPrereq) — e.g. God's Consort
    # → Cult of / Influence of God's Consort. Mirror build_event_chains.py: treat
    # a trait as a chain token only when exactly ONE story grants it (a unique
    # entry point, like an EventLinkAdd) and skip _ARCHETYPE traits (one setup
    # event grants them, but they gate dozens of unrelated personality events).
    subj_idx = m.index_many("subject.xml")
    subj_trait = {z: e.findtext("TraitPrereq") for z, e in subj_idx.items()
                  if (e.findtext("TraitPrereq") or "NONE") != "NONE"}

    def granted_traits(el: ET.Element | None) -> set[str]:
        """Traits an option/story grants directly (aeAddTraits) or via a bonus."""
        if el is None:
            return set()
        ts = {v.text for v in el.findall("aeAddTraits/zValue") if v.text and v.text != "NONE"}
        for bz in el.findall("aeBonuses/zValue"):
            b = bonus_idx.get(bz.text or "")
            if b is not None:
                ts |= {v.text for v in b.findall("aeAddTraits/zValue")
                       if v.text and v.text != "NONE"}
        return ts

    def story_opts(s: ET.Element) -> list[ET.Element]:
        """Option elements in the SAME order/length as bev.options() emits:
        resolvable aeOptions refs first, then inline EventOptions."""
        opts: list[ET.Element] = []
        for oz in s.findall("aeOptions/zValue"):
            o = eopt_idx.get(oz.text or "")
            if o is not None:
                opts.append(o)
        opts += list(s.findall("EventOptions/EventOption"))
        return opts

    trait_required: dict[str, set[str]] = {}  # trait → stories gating on it
    for z, s in story_idx.items():
        subs = [p.findtext("Second") for p in s.findall("SubjectExtras/Pair")]
        subs += [v.text for v in s.findall("aeSubjects/zValue")]
        for sub in subs:
            tp = subj_trait.get(sub or "")
            if tp:
                trait_required.setdefault(tp, set()).add(z)

    trait_src: dict[str, set[str]] = {}             # trait → granting stories
    grant_at_opt: dict[str, list[tuple[str, int]]] = {}  # trait → [(story, opt index)]
    for z, s in story_idx.items():
        for t in granted_traits(s):                 # story-level (guaranteed) grant
            trait_src.setdefault(t, set()).add(z)
        for i, o in enumerate(story_opts(s)):
            for t in granted_traits(o):
                trait_src.setdefault(t, set()).add(z)
                grant_at_opt.setdefault(t, []).append((z, i))

    for t, srcs in trait_src.items():
        dsts = trait_required.get(t)
        if t.endswith("_ARCHETYPE") or len(srcs) != 1 or not dsts:
            continue
        src_story = next(iter(srcs))
        for z, i in grant_at_opt.get(t, []):        # leadsTo on the granting option
            ev = events_by_id.get(z)
            if ev is None or i >= len(ev["options"]):
                continue
            lts = ev["options"][i].get("leadsTo") or []
            for ref in refs(sorted(dsts), skip=z):
                if all(x["id"] != ref["id"] for x in lts):
                    lts.append(ref)
            if lts:
                ev["options"][i]["leadsTo"] = lts
        for d in dsts:                              # followsFrom on the gated story
            ev = events_by_id.get(d)
            if ev is None:
                continue
            ff = ev.get("followsFrom") or []
            for ref in refs([src_story], skip=d):
                if all(x["id"] != ref["id"] for x in ff):
                    ff.append(ref)
            if ff:
                ev["followsFrom"] = ff

    # ── Potential follow-ups via memories (canLeadTo) ───────────────────────
    # An option that grants a memory makes its holder eligible for any story
    # whose cast subjects require that memory (subject.xml MemoryPrereq) — an
    # eligibility hint, NOT a guaranteed chain like leadsTo. MemoryInvalid
    # consumers are blockers, deliberately not listed. Capped to keep cards
    # honest about being a sample, deduped via refs().
    CAN_LEAD_CAP = 6
    chain = m.memory_chain()
    for z, ev in events_by_id.items():
        for opt in ev["options"]:
            toks: list[str] = []
            for oc in opt.get("outcomes", []):
                for r in oc.get("rewards", []):
                    mem = r.get("memory")
                    if mem and mem not in toks:
                        toks.append(mem)
            ids: list[str] = []
            for t in toks:
                ids += chain.get(t, {}).get("enables", [])
            if ids:
                cl = refs(ids, skip=z)[:CAN_LEAD_CAP]
                if cl:
                    opt["canLeadTo"] = cl

    # Compact: across ~5k events the always-emitted null fields from the shared
    # option helpers add real megabytes. Drop them; the page renders with safe
    # fallbacks (e.g. a missing probability means a guaranteed outcome).
    for ev in events_by_id.values():
        for opt in ev["options"]:
            if not opt.get("linkAdds"):
                opt.pop("linkAdds", None)
            for oc in opt.get("outcomes", []):
                if oc.get("label") is None:
                    oc.pop("label", None)
                if oc.get("weight") is None:
                    oc.pop("weight", None)
                if oc.get("probability") == 1.0:
                    oc.pop("probability", None)

    # ── Write output ────────────────────────────────────────────────────────
    parts_dir = OUT_DIR / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for old in parts_dir.glob("*.json"):
        old.unlink()  # drop stale parts from a previous taxonomy

    def dump(obj) -> str:
        return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")) + "\n"

    total_bytes = 0
    for cat in cat_defs:
        public_cat = {k: v for k, v in cat.items() if k not in ("ids", "_chunks")}
        for i, chunk in enumerate(cat["_chunks"]):
            if not chunk:
                continue
            part = cat["parts"][i]
            payload = dump({"category": public_cat, "part": part, "events": chunk})
            (parts_dir / f"{part['slug']}.json").write_text(payload)
            total_bytes += len(payload.encode())

    meta = {
        "totalStories": len(story_idx),
        "included": len(events_by_id),
        "excludedCovered": {
            "ruin-events": len(excluded["ruins"]),
            "expedition-events": len(excluded["expeditions"]),
            "harvest-events": len(excluded["harvest"]),
            "study-events": len(excluded["study"]),
            "wonder-events": len(excluded["wonders"]),
            "project-events": len(excluded["projects"]),
            "building-events": len(excluded["buildings"]),
            "total": len(excluded_all),
        },
        "note": "excluded = stories already rendered by the five specialized "
                "pages (same trigger/class criteria as their builders)",
    }
    index_payload = json.dumps(
        {"_meta": meta,
         "categories": [{k: v for k, v in c.items() if k not in ("ids", "_chunks")}
                        for c in cat_defs]},
        indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (OUT_DIR / "index.json").write_text(index_payload)

    search = []
    for cat in cat_defs:
        for chunk in cat["_chunks"]:
            for e in chunk:
                # Titles only — story body prose is not shipped (see build_event),
                # so the search index carries no text snippet either.
                entry = {"i": e["id"], "n": e["name"], "s": part_of[e["id"]],
                         "g": cat["label"]}
                search.append(entry)
    search.sort(key=lambda r: (r["n"], r["i"]))
    search_payload = dump(search)
    (OUT_DIR / "search.json").write_text(search_payload)

    # ── Report ──────────────────────────────────────────────────────────────
    print(f"✓ wrote {OUT_DIR.relative_to(ROOT)}/ — {len(events_by_id)} events, "
          f"{len(cat_defs)} categories, {sum(len(c['parts']) for c in cat_defs)} pages")
    print(f"  parts {total_bytes / 1e6:.1f} MB · index {len(index_payload) / 1e3:.0f} KB · "
          f"search {len(search_payload) / 1e6:.1f} MB")
    print(f"  excluded as already covered: {meta['excludedCovered']}")
    missing_name = sum(
        1 for z in events_by_id
        if (story_idx[z].findtext("Name") or "") not in text)
    if missing_name:
        print(f"  ⚠ {missing_name} events fell back to token names (no TEXT entry)")
    for c in cat_defs:
        tag = {"class": "class", "trigger": "trig ", "special": "spec "}[c["kind"]]
        parts = f" · {len(c['parts'])} pages" if len(c["parts"]) > 1 else ""
        print(f"  · [{tag}] {c['label']:42} {c['count']:4}{parts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
