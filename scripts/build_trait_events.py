#!/usr/bin/env python3
"""Build src/data/trait_events.json — which events a TRAIT opens up.

Two questions this answers, and they are mechanically different:

  1. "gates"  — the event only exists for a character with the trait.
  2. "options" — the event happens anyway, but the trait adds a choice.

Both route through subject.xml, never through trait.xml. A Subject is the
casting template an event slots its actors into, and a Subject may carry a
trait filter:

  TraitPrereq  TRAIT_HUMBLE            → a SOLO gate: only Humble satisfies it
  aeTraitAny   [RIGHTEOUS, GRACIOUS,   → a CLUSTER: any one member satisfies it
                LOYAL, COMPASSIONATE]

The cluster is not our abstraction — it is a named, player-facing object.
Every cluster subject carries a GenderedName ("Honorable", "Charming",
"Terrifying", …) and the game prints it verbatim in the option tooltip via
HelpText.Game.cs getGenderedSubjectNameVariable → TEXT_HELPTEXT_REQUIRES
("Requires {0_singleOrList}"). So we surface the cluster by its own name and
list its members, rather than flattening it onto each member trait.

Where the two gate kinds attach
-------------------------------
  · story gate   eventStory aeSubjects[i] plus the SubjectExtras /
                 SubjectAny layered onto slot i. SubjectExtras is a HARD AND,
                 not a weight nudge — PlayerEvent.cs:1000 returns false when
                 the extra subject fails to validate. The new <Subjects>
                 syntax expresses the same thing as <Extra>/<Any> children.
  · option gate  eventOption LeaderSubject / LeaderSubjectAny / PlayerSubject.

Counting rule (load-bearing)
----------------------------
The gate lives on the SUBJECT, so this file keys everything by subject and the
page unions on read. Never sum a trait's subjects: a story with both a
"Charming" option and a "Covert" option would be counted twice for Cunning,
which is in both clusters. 53 of the 104 clustered traits sit in 2+ clusters.

Competitive Mode
----------------
Every story carries cm: 1/0 using the same rule as build_events.py — an event
is CM-eligible unless aeGameOptionInvalid lists GAMEOPTION_COMPETITIVE_EVENTS.
The pages default to CM-only; the flag is per-story so the toggle is free.

Runs AFTER build_event_search.py — hrefs come from src/data/event-search.json
so every event links to wherever it actually renders.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
DATA = ROOT / "src" / "data"
OUT = DATA / "trait_events.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_missions as m  # noqa: E402  shared event/bonus humanizer


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ── gendered names ─────────────────────────────────────────────────────────
# Subjects and traits name themselves through genderedText.xml, which maps a
# GENDERED_TEXT_* key to one TEXT_* per grammatical gender. We take masculine
# as the canonical form (it is the bare noun; the _F variants are the
# inflected ones) and strip the "Hero~a Hero~Heroes" article/plural forms.
def gendered_names(text: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("genderedText*.xml")):
        for e in ET.parse(p).getroot().findall("Entry"):
            z = e.findtext("zType")
            if not z:
                continue
            for pair in e.findall("Texts/Pair"):
                if pair.findtext("zIndex") == "GRAMMATICAL_GENDER_MASCULINE":
                    key = pair.findtext("zValue") or ""
                    val = m.clean_text(text.get(key, "")) or ""
                    if val:
                        out[z] = val.split("~")[0].strip()
                    break
    return out


def cm_ok(s: ET.Element) -> bool:
    """Same rule as build_events.py cm_ineligible(), inverted."""
    return not any((v.text or "") == "GAMEOPTION_COMPETITIVE_EVENTS"
                   for v in s.findall("aeGameOptionInvalid/zValue"))


def zvals(e: ET.Element, tag: str) -> list[str]:
    return [x.text for x in e.findall(f"{tag}/zValue") if x.text]


def main() -> int:
    # Load EVERY text-*.xml rather than a hand-listed subset: the DLC packs
    # scatter strings unpredictably (SUBJECT_CHARACTER_HIGH_STRUNG's label
    # lives in text-misc-btt.xml), and a missing file silently degrades a
    # cluster to its raw token instead of failing loudly.
    text = m.load_text(*sorted(p.name for p in XML_DIR.glob("text-*.xml")))
    gname = gendered_names(text)

    subj = m.index_many("subject.xml")
    stories_x = m.index_many(
        "eventStory.xml", "eventStory-btt.xml", "eventStory-eoti.xml",
        "eventStory-sap.xml", "eventStory-wd.xml", "eventStory-wog.xml")
    eopt = m.index_many(
        "eventOption.xml", "eventOption-btt.xml", "eventOption-eoti.xml",
        "eventOption-sap.xml", "eventOption-wd.xml", "eventOption-wog.xml")
    bonus_idx = m.bonus_index()

    # ── which subjects carry a trait filter ────────────────────────────────
    # extra[] records the NON-trait conditions riding along on the same
    # subject (bLeader, Religion, iMinAge …) so the page can say "and must be
    # your leader" instead of implying the trait alone is the whole gate.
    # bHidden only suppresses the "Requires …" line; it is not a condition
    # the character has to satisfy, so it never belongs in extra[].
    IGNORE = {"zType", "GenderedName", "Name", "Class", "TraitPrereq",
              "aeTraitAny", "bHidden"}
    gate: dict[str, dict] = {}
    for sid, e in subj.items():
        solo = e.findtext("TraitPrereq")
        anyt = zvals(e, "aeTraitAny")
        if not solo and not anyt:
            continue
        gate[sid] = {
            "traits": [solo] if solo else anyt,
            "solo": bool(solo),
            "name": gname.get(e.findtext("GenderedName") or "", ""),
            "extra": sorted({c.tag for c in e if c.tag not in IGNORE}),
            "hidden": e.findtext("bHidden") == "1",
        }

    # ── trait metadata (name/slug/category shared with the Traits page) ────
    traits_json = json.loads((DATA / "traits.json").read_text())
    tmeta: dict[str, dict] = {}
    for cat, rows in traits_json.items():
        for t in rows:
            tmeta[t["id"]] = {"name": t["name"], "slug": t["slug"], "cat": cat}

    def tname(tid: str) -> str:
        if tid in tmeta:
            return tmeta[tid]["name"]
        return (gname.get(f"GENDERED_TEXT_{tid}", "")
                or tid.replace("TRAIT_", "").replace("_", " ").title())

    # ── event hrefs (already resolved for every page the events live on) ──
    search = json.loads((DATA / "event-search.json").read_text())
    href = {r["i"]: r["h"] for r in search}
    ename = {r["i"]: r["n"] for r in search}
    egroup = {r["i"]: r.get("g", "") for r in search}

    # ── walk every story ──────────────────────────────────────────────────
    stories: dict[str, dict] = {}
    gates_by_subject: dict[str, list[dict]] = defaultdict(list)
    opts_by_subject: dict[str, list[dict]] = defaultdict(list)

    def note_story(sid: str, s: ET.Element) -> None:
        if sid in stories:
            return
        stories[sid] = {
            "n": ename.get(sid) or m.clean_text(text.get(s.findtext("Name") or "", "")) or sid,
            "h": href.get(sid, ""),
            "w": int(s.findtext("iWeight") or 0),
            "cm": 1 if cm_ok(s) else 0,
            "dlc": s.findtext("GameContentRequired") or "",
            "trg": egroup.get(sid, ""),
        }

    for sid, s in stories_x.items():
        if not s.findtext("zType"):
            continue  # the schema-template first Entry

        # Slot list: legacy aeSubjects, then the newer <Subjects><Subject>
        # form. Extras/Any attach to a slot index in both syntaxes.
        slots = zvals(s, "aeSubjects")
        per: dict[int, list[tuple[str, str]]] = defaultdict(list)
        for p in s.findall("SubjectExtras/Pair"):
            per[int(p.findtext("First") or 0)].append((p.findtext("Second") or "", "and"))
        for p in s.findall("SubjectAny/Pair"):
            per[int(p.findtext("First") or 0)].append((p.findtext("Second") or "", "or"))
        for sub in s.findall("Subjects/Subject"):
            i = len(slots)
            slots = slots + [sub.findtext("Type") or ""]
            for x in sub.findall("Extra"):
                per[i].append((x.text or "", "and"))
            for x in sub.findall("Any"):
                per[i].append((x.text or "", "or"))

        trig = s.findtext("iTriggerSubject")
        trig = int(trig) if trig and trig.lstrip("-").isdigit() else None

        for i, base in enumerate(slots):
            be = subj.get(base)
            # Whose character must carry the trait. bIsUs / bIsNotUs live on
            # the BASE subject of the slot; the trait-carrying extra inherits
            # the slot's ownership.
            owner = "any"
            if be is not None:
                if be.findtext("bIsUs") == "1":
                    owner = "you"
                elif be.findtext("bIsNotUs") == "1":
                    owner = "them"
            for gsid, mode in [(base, "and")] + per[i]:
                if gsid not in gate:
                    continue
                note_story(sid, s)
                gates_by_subject[gsid].append({
                    "s": sid, "owner": owner, "mode": mode,
                    "trigger": i == trig, "slot": i,
                })

        for oz in (zvals(s, "aeOptions")
                   + [x.text for x in s.findall("EventOptions/EventOption/Type") if x.text]):
            o = eopt.get(oz)
            if o is None:
                continue
            refs = ([(o.findtext("LeaderSubject"), "leader")]
                    + [(v, "leader") for v in zvals(o, "LeaderSubjectAny")]
                    + [(o.findtext("PlayerSubject"), "player")])
            for gsid, who in refs:
                if not gsid or gsid not in gate:
                    continue
                note_story(sid, s)
                rewards: list[str] = []
                for out in m.option_outcomes(o, eopt, bonus_idx, text):
                    for r in out["rewards"]:
                        t = r.get("text") if isinstance(r, dict) else str(r)
                        if t and t not in rewards:
                            rewards.append(t)
                opts_by_subject[gsid].append({
                    "s": sid,
                    "o": oz,
                    "t": m.clean_text(text.get(o.findtext("Text") or "", "")),
                    "r": rewards,
                    "who": who,
                    # An option that hides its prereq (or hides itself when
                    # invalid) is one you never learn you missed.
                    "hid": o.findtext("bHidePrereqs") == "1" or o.findtext("bHideInvalid") == "1",
                })

    # ── clusters ──────────────────────────────────────────────────────────
    # Several clusters ship more than once: a bHidden twin used where the game
    # suppresses the "Requires …" line (SUBJECT_CHARACTER_CARNAL_HIDDEN), and
    # occasionally a second copy under a second name (the four martial
    # archetypes are both "Martial" and "Military"). Same members + same
    # non-trait conditions ⇒ same gate, so collapse them and keep the extra
    # names as alsoCalled. bHidden is excluded from the key precisely because
    # it is the thing that differs between a cluster and its twin; GenderPrereq
    # and friends are NOT, so SUBJECT_NOT_STRAIGHT_MAN stays its own cluster.
    groups: dict[tuple, list[str]] = defaultdict(list)
    for sid, g in gate.items():
        if g["solo"]:
            continue
        key = (tuple(sorted(g["traits"])),
               tuple(x for x in g["extra"] if x != "bHidden"))
        groups[key].append(sid)

    canon: dict[tuple, str] = {}
    alias: dict[str, list[str]] = {}
    also: dict[str, list[str]] = {}
    for key, ids in groups.items():
        # Prefer a visible, named subject as the head — that is the one whose
        # label the player actually sees in a "Requires …" line.
        head = sorted(ids, key=lambda s: (not gate[s]["name"], gate[s]["hidden"], s))[0]
        canon[key] = head
        alias[head] = sorted(s for s in ids if s != head)
        also[head] = sorted({gate[s]["name"] for s in ids
                             if gate[s]["name"] and gate[s]["name"] != gate[head]["name"]})

    # Role/condition clusters (clergy, study, wounds, cult, orientation) are
    # real trait clusters but they are not personality picks — separate group
    # so the personality ones aren't buried.
    ROLEISH = ("TRAIT_CLERGY", "TRAIT_STUDY_", "TRAIT_MYSTERY", "TRAIT_MITHRAS",
               "TRAIT_WOUNDED", "TRAIT_SEVERELY", "TRAIT_BLINDED", "TRAIT_CRIPPLED",
               "TRAIT_POISONED", "TRAIT_GAY", "TRAIT_BISEXUAL")

    # name → distinct trait ids sharing it (the pagan clergies all render as
    # "Priest"); only an actually-ambiguous name gets qualified.
    tname_counts: dict[str, set] = defaultdict(set)
    for g in gate.values():
        for t in g["traits"]:
            tname_counts[tname(t)].add(t)

    clusters = []
    for key, head in canon.items():
        g = gate[head]
        ids = [head] + alias[head]
        gl, ol = [], []
        for sid in ids:
            gl += gates_by_subject.get(sid, [])
            ol += opts_by_subject.get(sid, [])
        # A handful of clusters carry no GenderedName at all — the game never
        # shows them a "Requires" line. Label from the id and say so, rather
        # than inventing a name for them.
        name = g["name"] or m._tok(head, "SUBJECT_").replace(" Hidden", "")
        clusters.append({
            "id": head,
            "aliases": sorted(alias[head]),
            "alsoCalled": also[head],
            "unnamed": not g["name"],
            "name": name,
            "slug": slugify(name),
            "kind": "role" if all(t.startswith(ROLEISH) for t in g["traits"]) else "personality",
            "extra": g["extra"],
            # The ten pagan clergies are all literally named "Priest" in the
            # game text; inside one cluster that reads as a rendering bug, so
            # qualify a repeated name with its own token (Priest · Aksum).
            "members": [{"id": t,
                         "name": (tname(t) if len(tname_counts[tname(t)]) == 1
                                  else f"{tname(t)} · {m._tok(t, 'TRAIT_CLERGY_PAGAN_', 'TRAIT_CLERGY_', 'TRAIT_')}"),
                         "slug": tmeta.get(t, {}).get("slug", slugify(tname(t)))}
                        for t in g["traits"]],
            "gates": gl,
            "options": ol,
        })
    clusters.sort(key=lambda c: (c["kind"] != "personality",
                                 -(len({x['s'] for x in c["gates"]}) + len(c["options"])),
                                 c["name"]))

    # a slug can repeat across kinds (Carnal/Carnal_HIDDEN already merged, but
    # e.g. two role clusters can share a label) — disambiguate deterministically
    used: dict[str, int] = {}
    for c in clusters:
        n = used.get(c["slug"], 0)
        used[c["slug"]] = n + 1
        if n:
            c["slug"] = f"{c['slug']}-{n + 1}"

    cluster_of_trait: dict[str, list[str]] = defaultdict(list)
    for c in clusters:
        for mem in c["members"]:
            cluster_of_trait[mem["id"]].append(c["slug"])

    # ── traits: SOLO access only (cluster access is read off the clusters) ─
    solo_gates: dict[str, list[dict]] = defaultdict(list)
    solo_opts: dict[str, list[dict]] = defaultdict(list)
    for sid, g in gate.items():
        if not g["solo"]:
            continue
        t = g["traits"][0]
        for row in gates_by_subject.get(sid, []):
            solo_gates[t].append({**row, "via": sid, "extra": g["extra"]})
        for row in opts_by_subject.get(sid, []):
            solo_opts[t].append({**row, "via": sid, "extra": g["extra"]})

    traits = []
    for tid in sorted(set(solo_gates) | set(solo_opts) | set(cluster_of_trait)):
        meta = tmeta.get(tid, {})
        traits.append({
            "id": tid,
            "name": tname(tid),
            "slug": meta.get("slug", slugify(tname(tid))),
            "cat": meta.get("cat", "status"),
            "clusters": cluster_of_trait.get(tid, []),
            "gates": solo_gates.get(tid, []),
            "options": solo_opts.get(tid, []),
        })

    cm_stories = sum(1 for s in stories.values() if s["cm"])
    payload = {
        "meta": {
            "traits": len(traits),
            "clusters": sum(1 for c in clusters if c["kind"] == "personality"),
            "roleClusters": sum(1 for c in clusters if c["kind"] == "role"),
            "stories": len(stories),
            "storiesCM": cm_stories,
            "soloSubjects": sum(1 for g in gate.values() if g["solo"]),
            "clusterSubjects": len(canon),
        },
        "stories": stories,
        "clusters": clusters,
        "traits": traits,
    }
    OUT.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(traits)} traits, "
          f"{payload['meta']['clusters']} personality clusters "
          f"(+{payload['meta']['roleClusters']} role), "
          f"{len(stories)} stories ({cm_stories} competitive-eligible)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
