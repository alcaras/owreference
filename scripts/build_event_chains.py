#!/usr/bin/env python3
"""Build src/data/event-chains.json — event chains as laid-out graphs.

An event chain is a connected component of the game's EventLink graph: an option
(or story) with an EventLinkAdd grants a link token; a story with the matching
EventLinkPrereq becomes eligible. So choosing option X in event A "may trigger"
event B. Chains branch (one event, several options → several follow-ups), merge
(several options → one follow-up — the Ant's Gold "diamond"), and fan out into
per-rival/per-nation variants of one template ("Neighbors" ×31).

For each component we emit a ready-to-render layered DAG:
  · nodes are grouped — structurally identical siblings (same title, same parents,
    same children: the template fans) collapse into one node with a count, so a
    55-entry fan reads as one box "Neighbors ×31" instead of a wall.
  · layer = longest path from a root (top→bottom flow); col = ordered position in
    the layer (parent-barycenter ordering to reduce edge crossings).
  · edges carry the option text(s) that trigger them.
  · each node links to wherever that event actually renders (href + group come
    straight from event-search.json, the global index — so this MUST run after
    build_event_search.py).

Output (compact, deterministic):
  src/data/event-chains.json
    { "_meta": {...},
      "chains": [ {slug,title,size,branches,layers,width,dlc,nodes[],edges[]} ],
      "index": { "<EVENTSTORY_ID>": {"slug","key"} } }   # event → its chain/node

Node:  {key, title, count, ids[], href, group, dlc, layer, col, root}
Edge:  {fr, to, labels[]}   (keys; labels are option texts, deduped)
col is a float in [0,width-1], already centered per layer; the renderer maps
(layer,col) → pixels. Titles only — story prose stays an in-game discovery.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_missions as m  # noqa: E402  clean_text / load_text / _tok

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
DATA = ROOT / "src" / "data"
OUT = DATA / "event-chains.json"

STORY_FILES = ("eventStory.xml", "eventStory-sap.xml", "eventStory-btt.xml",
               "eventStory-eoti.xml", "eventStory-wd.xml", "eventStory-wog.xml")
OPT_FILES = ("eventOption.xml", "eventOption-sap.xml", "eventOption-btt.xml",
             "eventOption-eoti.xml", "eventOption-wd.xml", "eventOption-wog.xml")
OPT_TEXT = ("text-eventOption.xml", "text-eventOption-sap.xml",
            "text-eventOption-btt.xml", "text-eventOption-hittite.xml")
TITLE_TEXT = ("text-eventStoryTitle.xml", "text-eventStoryTitle-sap.xml",
              "text-eventStoryTitle-btt.xml", "text-eventStoryTitle-hittite.xml",
              "text-eventStory.xml")


def load_entries(files: tuple[str, ...]) -> dict[str, ET.Element]:
    idx: dict[str, ET.Element] = {}
    for fn in files:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            z = e.findtext("zType")
            if z and z not in idx:
                idx[z] = e
    return idx


def opt_links(o: ET.Element | None) -> set[str]:
    """EventLinkAdd + EventLinkSubjectsAdd targets on an option."""
    s: set[str] = set()
    if o is None:
        return s
    la = o.findtext("EventLinkAdd")
    if la and la != "NONE":
        s.add(la)
    for pr in o.findall("EventLinkSubjectsAdd/Pair"):
        zi = pr.findtext("zIndex")
        if zi and zi != "NONE":
            s.add(zi)
    return s


def main() -> int:
    story = load_entries(STORY_FILES)
    opt = load_entries(OPT_FILES)
    bonus = load_entries(("bonus.xml", "bonus-event.xml"))
    subj = load_entries(("subject.xml",))
    trait = load_entries(("trait.xml",))
    otext = m.load_text(*OPT_TEXT)
    ttext = m.load_text(*TITLE_TEXT)

    # Global index gives the canonical name + href + page-group per event.
    search = {r["i"]: r for r in json.loads((DATA / "event-search.json").read_text())}

    def name(z: str) -> str:
        if z in search:
            return search[z]["n"]
        s = story.get(z)
        return m.clean_text(ttext.get(s.findtext("Name") or "", m._tok(z, "EVENTSTORY_"))) \
            if s is not None else m._tok(z, "EVENTSTORY_")

    def dlc_of(z: str) -> str | None:
        s = story.get(z)
        if s is None:
            return None
        # build_events.dlc_label, but avoid importing it here; mirror the mapping.
        gc = (s.findtext("GameContentRequired") or "").strip()
        return {
            "GAME_CONTENT_HEROES_OF_THE_AEGEAN": "Aegean",
            "GAME_CONTENT_BEHIND_THE_THRONE": "Behind the Throne",
            "GAME_CONTENT_WONDERS_AND_DYNASTIES": "Wonders & Dynasties",
            "GAME_CONTENT_SACRED_AND_PROFANE": "Sacred & Profane",
            "GAME_CONTENT_PHARAOHS_OF_THE_NILE": "Pharaohs of the Nile",
            "GAME_CONTENT_EMPIRES_OF_THE_INDUS": "Empires of the Indus",
            "GAME_CONTENT_WRATH_OF_GODS": "Wrath of Gods",
        }.get(gc)

    # ── Edges: (src, dst, option-label) ──────────────────────────────────────
    by_prereq: dict[str, list[str]] = {}
    for z, s in story.items():
        lp = s.findtext("EventLinkPrereq")
        if lp and lp != "NONE":
            by_prereq.setdefault(lp, []).append(z)

    edges: list[tuple[str, str, str | None]] = []
    for z, s in story.items():
        la = s.findtext("EventLinkAdd")
        if la and la != "NONE":
            for dst in by_prereq.get(la, []):
                if dst != z:
                    edges.append((z, dst, None))
        labelled: list[tuple[ET.Element | None, str | None]] = []
        for oz in s.findall("aeOptions/zValue"):
            o = opt.get(oz.text or "")
            lbl = m.clean_text(otext.get(o.findtext("Text") or "", "")) if o is not None else ""
            labelled.append((o, lbl or None))
        for o in s.findall("EventOptions/EventOption"):
            labelled.append((o, m.clean_text(otext.get(o.findtext("Text") or "", "")) or None))
        for o, lbl in labelled:
            for L in opt_links(o):
                for dst in by_prereq.get(L, []):
                    if dst != z:
                        edges.append((z, dst, lbl))

    # ── Trait-token edges: the game also chains events through a granted trait,
    # not just EventLink. An option grants TRAIT_X (via a bonus's aeAddTraits);
    # later events gate on it through a subject whose only constraint is a
    # TraitPrereq (e.g. The Monkey's Paw → SUBJECT_MONKEY_PAW_OWNER follow-ups).
    # We only treat a trait as a chain token when it's granted by exactly ONE
    # event — that single event is then the unique entry point, exactly like an
    # EventLinkAdd. This excludes ambient personality traits (Imprisoned, Cruel,
    # …) that dozens of unrelated events grant, which would merge everything into
    # one blob. `_ARCHETYPE` traits (a single setup event grants them but they
    # gate 75+ personality events) are excluded for the same reason.
    subj_trait = {z: e.findtext("TraitPrereq") for z, e in subj.items()
                  if (e.findtext("TraitPrereq") or "NONE") != "NONE"}

    def bonus_traits(bz: str | None) -> set[str]:
        b = bonus.get(bz or "")
        if b is None:
            return set()
        return {v.text for v in b.findall("aeAddTraits/zValue") if v.text and v.text != "NONE"}

    def grant_traits(el: ET.Element | None) -> set[str]:
        """Traits an option/story grants directly or via its bonuses."""
        if el is None:
            return set()
        s = {v.text for v in el.findall("aeAddTraits/zValue") if v.text and v.text != "NONE"}
        for bz in el.findall("aeBonuses/zValue"):
            s |= bonus_traits(bz.text)
        return s

    # trait → set of stories that gate on it (subject TraitPrereq)
    trait_required: dict[str, set[str]] = defaultdict(set)
    for z, s in story.items():
        subs = [p.findtext("Second") for p in s.findall("SubjectExtras/Pair")]
        subs += [v.text for v in s.findall("aeSubjects/zValue")]
        for sub in subs:
            tp = subj_trait.get(sub or "")
            if tp:
                trait_required[tp].add(z)

    # trait → granting (story, option-label); collect to find single-grant tokens
    trait_grants: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    for z, s in story.items():
        recs: list[tuple[ET.Element | None, str | None]] = []
        for oz in s.findall("aeOptions/zValue"):
            o = opt.get(oz.text or "")
            lbl = m.clean_text(otext.get(o.findtext("Text") or "", "")) if o is not None else ""
            recs.append((o, lbl or None))
        for o in s.findall("EventOptions/EventOption"):
            recs.append((o, m.clean_text(otext.get(o.findtext("Text") or "", "")) or None))
        recs.append((s, None))  # story-level bonuses (no option label)
        for el, lbl in recs:
            for t in grant_traits(el):
                trait_grants[t].append((z, lbl))

    for t, grants in trait_grants.items():
        if t.endswith("_ARCHETYPE"):
            continue
        srcs = {z for z, _ in grants}
        if len(srcs) != 1:           # not a unique entry point → not a chain token
            continue
        if not trait_required.get(t):
            continue
        for z, lbl in grants:
            for dst in trait_required[t]:
                if dst != z:
                    edges.append((z, dst, lbl))

    out_adj: dict[str, set[str]] = defaultdict(set)
    in_adj: dict[str, set[str]] = defaultdict(set)
    und: dict[str, set[str]] = defaultdict(set)
    edge_labels: dict[tuple[str, str], set[str]] = defaultdict(set)
    for a, b, lbl in edges:
        out_adj[a].add(b); in_adj[b].add(a)
        und[a].add(b); und[b].add(a)
        if lbl:
            edge_labels[(a, b)].add(lbl)

    nodes = set(out_adj) | set(in_adj)

    # ── Connected components ────────────────────────────────────────────────
    seen: set[str] = set()
    comps: list[set[str]] = []
    for n in sorted(nodes):
        if n in seen:
            continue
        stack = [n]; comp: set[str] = set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.add(x)
            stack += [y for y in und[x] if y not in seen]
        comps.append(comp)

    used_slugs: set[str] = set()

    def slug_for(zid: str) -> str:
        base = zid.replace("EVENTSTORY_", "").lower().replace("_", "-")[:48].strip("-") or "chain"
        s = base; i = 2
        while s in used_slugs:
            s = f"{base}-{i}"; i += 1
        used_slugs.add(s)
        return s

    chains: list[dict] = []
    index: dict[str, dict] = {}

    for comp in comps:
        # roots = no incoming edge inside the component
        roots = sorted(n for n in comp if not (in_adj[n] & comp))
        if not roots:
            roots = [sorted(comp)[0]]  # degenerate cycle: pick a deterministic start

        # ── Collapse structurally identical siblings (template fans) ─────────
        # key by (title, parent-set, child-set) within the component.
        def grp_key(n: str) -> tuple:
            return (name(n),
                    frozenset(in_adj[n] & comp),
                    frozenset(out_adj[n] & comp))
        groups: dict[tuple, list[str]] = defaultdict(list)
        for n in sorted(comp):
            groups[grp_key(n)].append(n)
        node_group: dict[str, str] = {}   # raw id → group key (a stable string)
        gid_of: dict[tuple, str] = {}
        for k, members in groups.items():
            gid = "g_" + members[0]        # representative id
            gid_of[k] = gid
            for mem in members:
                node_group[mem] = gid

        gmembers: dict[str, list[str]] = {gid_of[k]: members for k, members in groups.items()}
        gout: dict[str, set[str]] = defaultdict(set)
        gin: dict[str, set[str]] = defaultdict(set)
        glabels: dict[tuple[str, str], set[str]] = defaultdict(set)
        for a, b, _lbl in edges:
            if a in comp and b in comp:
                ga, gb = node_group[a], node_group[b]
                if ga != gb:
                    gout[ga].add(gb); gin[gb].add(ga)
                    glabels[(ga, gb)] |= edge_labels.get((a, b), set())

        gnodes = list(gmembers)

        # ── Layer = longest path from a root (ignore back edges) ─────────────
        color: dict[str, str] = {}
        order: list[str] = []

        def dfs(u: str) -> None:
            color[u] = "grey"
            for v in sorted(gout[u]):
                if color.get(v) is None:
                    dfs(v)
            color[u] = "black"; order.append(u)

        groot = sorted({node_group[r] for r in roots})
        for r in groot:
            if color.get(r) is None:
                dfs(r)
        for u in sorted(gnodes):
            if color.get(u) is None:
                dfs(u)
        topo = list(reversed(order))
        layer: dict[str, int] = {}
        for u in topo:
            ps = [layer[p] for p in gin[u] if p in layer]
            layer[u] = (max(ps) + 1) if ps else 0

        # ── Order within each layer (parent barycenter, a few passes) ────────
        by_layer: dict[int, list[str]] = defaultdict(list)
        for u in gnodes:
            by_layer[layer[u]].append(u)
        col: dict[str, float] = {}
        for L in sorted(by_layer):
            by_layer[L].sort(key=name)
            for i, u in enumerate(by_layer[L]):
                col[u] = float(i)
        for _ in range(4):
            for L in sorted(by_layer):
                if L == 0:
                    continue
                def bary(u: str) -> float:
                    ps = [col[p] for p in gin[u] if p in col]
                    return sum(ps) / len(ps) if ps else col[u]
                by_layer[L].sort(key=lambda u: (bary(u), name(u)))
                for i, u in enumerate(by_layer[L]):
                    col[u] = float(i)

        width = max((len(v) for v in by_layer.values()), default=1)
        # center each layer within `width`
        for L, us in by_layer.items():
            off = (width - len(us)) / 2.0
            for u in us:
                col[u] = col[u] + off

        # ── Pick the chain's primary root (most reachable) for slug/title ────
        def reach(g: str) -> int:
            st = [g]; vis = set()
            while st:
                x = st.pop()
                if x in vis:
                    continue
                vis.add(x); st += list(gout[x])
            return len(vis)
        primary = max(groot, key=lambda g: (reach(g), -ord(name(g)[0]) if name(g) else 0, g)) \
            if groot else gnodes[0]
        primary_id = gmembers[primary][0]
        slug = slug_for(primary_id)
        title = name(primary_id)

        out_nodes = []
        for gid in sorted(gnodes, key=lambda g: (layer[g], col[g], g)):
            members = gmembers[gid]
            rep = members[0]
            r = search.get(rep)
            out_nodes.append({
                "key": gid,
                "title": name(rep),
                "count": len(members),
                "ids": members,
                "href": (r["h"] if r else None),
                "group": (r["g"] if r else None),
                "dlc": dlc_of(rep),
                "layer": layer[gid],
                "col": round(col[gid], 3),
                "root": gid in groot,
            })
        out_edges = []
        for (a, b), labs in sorted(glabels.items()):
            out_edges.append({"fr": a, "to": b, "labels": sorted(labs)})
        # edges without labels (story-level links) still need to render
        for a in gnodes:
            for b in sorted(gout[a]):
                if (a, b) not in glabels:
                    out_edges.append({"fr": a, "to": b, "labels": []})
        out_edges.sort(key=lambda e: (e["fr"], e["to"]))

        branches = sum(1 for g in gnodes if len(gout[g]) > 1)
        dlcs = sorted({n["dlc"] for n in out_nodes if n["dlc"]})
        chain = {
            "slug": slug,
            "title": title,
            "size": len(comp),
            "groupCount": len(gnodes),
            "branches": branches,
            "layers": max(layer.values()) + 1,
            "width": width,
            "roots": len(groot),
            "dlc": dlcs,
            "nodes": out_nodes,
            "edges": out_edges,
        }
        chains.append(chain)
        # Per-event lookup for the card banners — carries just enough to render
        # "part of a chain" without loading the full chains array on a card page.
        for gid in gnodes:
            for mem in gmembers[gid]:
                index[mem] = {"slug": slug, "key": gid, "title": title,
                              "size": len(comp), "branches": branches}

    chains.sort(key=lambda c: (-c["size"], c["title"], c["slug"]))

    meta = {
        "chains": len(chains),
        "eventsInChains": len(nodes),
        "multiBranch": sum(1 for c in chains if c["branches"] > 0),
        "largest": chains[0]["size"] if chains else 0,
    }
    payload = json.dumps({"_meta": meta, "chains": chains, "index": index},
                         sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")) + "\n"
    OUT.write_text(payload)
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(chains)} chains, "
          f"{len(nodes)} events, {meta['multiBranch']} multi-branch, "
          f"largest {meta['largest']} ({len(payload)/1e3:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
