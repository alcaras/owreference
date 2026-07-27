#!/usr/bin/env python3
"""Build public/data/overlay-cards.json — display cards for the streamer overlay.

Based on PR #1 by machinefolly, rebuilt on the entity registry: identity, icon
and page routing come from src/data/entities.json (which already resolved them
for Term/LinkedText); card bodies come from the per-tab catalogs, read with
their actual field names.

Output lives under public/ (not src/data/) because the two overlay pages fetch
it at runtime — it is a projection of already-changelogged data, so it is not
snapshotted itself.

Card shape (all fields always present):
  { id, name, type, page, slug, icon, accent, aliases[], chips[],
    stats{}, cost[], lines[], event }
- accent: in-game hex (nation / family / tribe / yield colour) for the header
  strip — same rule as the site: identity colour lives in the header only.
- chips: short mono metadata (era, tech, law pair, chain, …).
- event: null for entities; for events a structured
  { trigger, category, dlc, chain:{title,size}|null,
    options:[{text, rewards[], reqs[], leadsTo[]}] }
  so the overlay can render options the way the event pages do.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
OUT = ROOT / "public" / "data" / "overlay-cards.json"

TYPE_LABEL = {
    "unit": "Unit", "tech": "Technology", "trait": "Trait", "archetype": "Archetype",
    "family": "Family", "shrine": "Shrine", "resource": "Resource", "law": "Law",
    "wonder": "Wonder", "improvement": "Improvement", "yield": "Yield",
    "nation": "Nation", "tribe": "Tribe", "theology": "Theology",
    "promotion": "Promotion", "project": "Project", "event": "Event",
}


def load(name: str):
    return json.loads((DATA / name).read_text())


def clean(name: str) -> str:
    """Strip unresolved text templates ("{UNIT-RELIGION,1} Disciple")."""
    return re.sub(r"\s{2,}", " ", re.sub(r"\{[^}]*\}", "", name or "")).strip()


def icon_exists(rel: str) -> bool:
    return bool(rel) and (ROOT / "public" / rel).exists()


def main() -> int:
    reg = load("entities.json")
    entities = reg["entities"]
    yield_colors = reg.get("yieldColors") or {}

    units = {u["id"]: u for u in load("units.json")}
    techs = {t["id"]: t for t in load("technologies.json")}
    wonders = {w["id"]: w for w in load("wonders.json")}
    resources = {r["id"]: r for r in load("resources.json")}
    promotions = {p["id"]: p for p in load("promotions.json")}
    urban = {u["id"]: u for u in load("urban_improvements.json")}
    rural = {r["id"]: r for r in load("rural_improvements.json")}
    archetypes = {a["id"]: a for a in load("archetypes.json")}
    projects = {p["id"]: p for p in load("projects.json")}
    tribes = {t["id"]: t for t in load("tribes.json")}
    family_classes = {f["name"]: f for f in load("families.json")}

    traits = {}
    for cat, lst in load("traits.json").items():
        for t in lst:
            traits[t["id"]] = t

    # law id -> (law, tier label, partner names in its class)
    laws = {}
    for g in load("laws.json")["groups"]:
        for c in g["classes"]:
            names = [l["name"] for l in c["laws"]]
            for l in c["laws"]:
                laws[l["id"]] = (l, g.get("label") or "", [n for n in names if n != l["name"]])

    shrines = {s["id"]: s for s in load("shrines.json")["shrines"]}

    theologies = {}
    for tier in load("theologies.json")["tiers"]:
        for th in tier.get("theologies") or []:
            th["_tier"] = tier.get("label") or ""
            theologies[th["id"]] = th

    nations = {n["id"]: n for n in load("nations.json")}
    nation_color_by_label = {n["name"]: (n.get("color") or {}).get("bg") or "" for n in nations.values()}
    # family instance -> (class name, nation name, in-game hex)
    family_home = {}
    for n in nations.values():
        for f in n.get("families") or []:
            family_home[f["id"]] = (f.get("class") or "", n.get("name") or "",
                                    f.get("ingameColor") or "")
    # nation name -> its unique units, era order
    uu_by_nation: dict[str, list] = {}
    for u in units.values():
        if u.get("category") == "unique" and u.get("nationLabel"):
            uu_by_nation.setdefault(u["nationLabel"], []).append(u)
    for lst in uu_by_nation.values():
        lst.sort(key=lambda u: (u.get("eraOrder") or 0, u["name"]))

    cards: dict[str, dict] = {}

    def base_card(eid, name, etype, slug="", page="", aliases=None):
        return {
            "id": eid, "name": name, "type": TYPE_LABEL.get(etype, etype.title()),
            "slug": slug, "page": page, "icon": "", "accent": "",
            "aliases": aliases or [], "chips": [], "stats": {}, "cost": [],
            "lines": [], "event": None,
        }

    def yields_label(items) -> str:
        return ", ".join(f"{x['value']} {x['yield'].title()}" for x in items or [])

    # ── entity-registry cards ────────────────────────────────────────────────
    for e in entities:
        eid, etype = e["id"], e["type"]
        c = base_card(eid, clean(e["name"]), etype, e.get("slug") or "", e.get("page") or "",
                      [clean(a) for a in (e.get("aliases") or [])
                       if clean(a) and clean(a) != clean(e["name"])])
        c["icon"] = e.get("icon") or ""

        if etype == "unit" and eid in units:
            u = units[eid]
            c["icon"] = c["icon"] or f"img/icons/units/{u.get('iconSlug') or u['slug']}.png"
            for label, key, scale in (("Strength", "strength", 10), ("Move", "movement", 1),
                                      ("Range", "range", 1), ("HP", "hp", 1)):
                v = u.get(key)
                if v:
                    c["stats"][label] = v // scale if scale > 1 else v
            # production cost first (the Training/Growth price), then goods
            if u.get("production"):
                c["cost"].append(f"{u['production']} {(u.get('trainingYield') or 'training').title()}")
            c["cost"] += [f"{x['value']} {x['yield'].title()}" for x in u.get("costs") or []]
            if u.get("era"):
                c["chips"].append(u["era"])
            if u.get("techLabel"):
                c["chips"].append(u["techLabel"])
            if u.get("nationLabel"):
                c["chips"].append(u["nationLabel"])
                c["accent"] = nation_color_by_label.get(u["nationLabel"]) or ""
            for ab in u.get("abilities") or []:
                lines = ab.get("lines") or []
                label = ab.get("label") or ""
                if label and lines:
                    c["lines"].append(f"{label} — {'; '.join(lines)}")
                elif label:
                    c["lines"].append(label)
                else:
                    c["lines"].extend(lines)
            if u.get("consumption"):
                c["lines"].append("Upkeep: " + yields_label(u["consumption"]))
            # everything src/lib/combat.ts needs to run the matchup math
            if u.get("isCombat"):
                c["combat"] = {
                    "strength": u.get("strength") or 0,
                    "traits": u.get("traits") or [],
                    "isMelee": bool(u.get("isMelee")),
                    "counters": [{"kind": x.get("kind") or "", "target": x.get("target") or "",
                                  "value": x.get("value") or 0}
                                 for x in u.get("counters") or []],
                }

        elif etype == "tech" and eid in techs:
            t = techs[eid]
            c["icon"] = c["icon"] or t.get("icon") or ""
            if t.get("cost"):
                c["cost"] = [f"{t['cost']} Science"]
            # technologies.json "era" (Bronze/Iron/…) is an invented label from
            # the legacy spreadsheet, NOT game data — tech.xml only has iColumn.
            # The overlay stays strictly on what the game names.
            unlocks = t.get("unlocks") or []
            if unlocks:
                names = [x.get("name", x) if isinstance(x, dict) else str(x) for x in unlocks]
                c["lines"].append("Unlocks: " + ", ".join(names))

        elif etype in ("trait", "archetype") and eid in traits:
            t = traits[eid]
            for r in t.get("ratings") or []:
                key = r.get("rating") or ""
                if key:
                    suffix = " (fallback)" if r.get("fallback") else ""
                    c["stats"][key + suffix] = f"{r['value']:+d}"
            for field, tag in (("leaderEffects", "Leader"), ("governorEffects", "Governor"),
                               ("generalEffects", "General"), ("modifiers", "")):
                for line in t.get(field) or []:
                    c["lines"].append(f"{tag}: {line}" if tag else str(line))
            ops = [f"{o['label']} {o['value']:+d}" for o in t.get("opinions") or []]
            if ops:
                c["lines"].append("Opinions: " + ", ".join(ops))
            if not c["lines"] and t.get("description"):
                c["lines"].append(t["description"])
            if t.get("category") and etype == "trait":
                c["chips"].append(str(t["category"]).title())
            if etype == "archetype" and eid in archetypes:
                c["icon"] = c["icon"] or archetypes[eid].get("icon") or ""

        elif etype == "law" and eid in laws:
            l, tier, partners = laws[eid]
            if l.get("switchCost"):
                c["cost"] = [f"{l['switchCost']} Civics"]
            # (no tier chip — "Tier 1 (early civic techs)" is our laws-page
            # grouping, not a game term; the law PAIR is game structure)
            for p in partners:
                c["chips"].append(f"vs {p}")
            c["lines"].extend(l.get("effects") or [])

        elif etype == "wonder" and eid in wonders:
            w = wonders[eid]
            c["icon"] = c["icon"] or w.get("icon") or ""
            c["cost"] = [x["label"] for x in w.get("cost") or []]
            if w.get("vp"):
                c["stats"]["VP"] = w["vp"]
            if w.get("era"):
                c["chips"].append(str(w["era"]))
            if w.get("buildTurns"):
                c["chips"].append(f"{w['buildTurns']} turns")
            # output is a list of {label,...}; otherOutput is a subset of it
            for x in w.get("output") or []:
                c["lines"].append(x["label"] if isinstance(x, dict) else str(x))
            c["lines"].extend(w.get("effects") or [])
            if w.get("location"):
                c["lines"].append(f"Location: {w['location']}")

        elif etype == "shrine" and eid in shrines:
            s = shrines[eid]
            if s.get("typeLabel"):
                c["chips"].append(f"{s['typeLabel']} shrine")
            if s.get("deity"):
                c["chips"].append(s["deity"])
            c["lines"].extend(s.get("outputs") or [])
            c["lines"].extend(s.get("effects") or [])
            c["cost"] = [x if isinstance(x, str) else x.get("label", "")
                         for x in s.get("costs") or []]

        elif etype == "resource" and eid in resources:
            r = resources[eid]
            c["icon"] = c["icon"] or r.get("icon") or ""
            if r.get("category"):
                c["chips"].append(r["category"].title())
            for h in r.get("harvest") or []:
                c["lines"].append(f"Harvest: {h}")
            c["lines"].extend(r.get("effects") or [])

        elif etype == "improvement":
            imp = urban.get(eid) or rural.get(eid)
            if imp:
                c["icon"] = c["icon"] or imp.get("icon") or ""
                cost = imp.get("cost")
                if isinstance(cost, list):
                    c["cost"] = [x["label"] if isinstance(x, dict) else str(x) for x in cost]
                if imp.get("tech"):
                    c["chips"].append(str(imp["tech"]))
                spec = imp.get("specialist")
                if isinstance(spec, str) and spec:
                    c["chips"].append(spec)
                c["lines"].extend(imp.get("effects") or [])

        elif etype == "nation" and eid in nations:
            n = nations[eid]
            c["accent"] = (n.get("color") or {}).get("bg") or ""
            # effectsXml is the XML-derived truth; yaml `bonuses` only fills in
            # where XML coverage is partial (source-of-truth rule #1)
            c["lines"].extend(n.get("effectsXml") or n.get("bonuses") or [])
            uus = uu_by_nation.get(n["name"]) or []
            if uus:
                c["lines"].append("Unique units: " + ", ".join(
                    f"{u['name']} (str {u['strength'] // 10})" for u in uus))
            fams = n.get("families") or []
            if fams:
                c["lines"].append("Families: " + ", ".join(
                    f"{f['name']} ({f['class']})" for f in fams))

        elif etype == "family" and eid in family_home:
            cls, nat, hexcolor = family_home[eid]
            c["accent"] = hexcolor
            c["chips"] = [x for x in (cls, nat) if x]
            fc = family_classes.get(cls)
            if fc:
                # the class icon, not the -seat variant (that's seat flair)
                c["icon"] = c["icon"] or fc.get("icon") or f"img/archetypes/{cls.lower()}.png"
                for b in fc.get("cityBonus") or []:
                    c["lines"].append(f"City: {b}")
                for b in fc.get("seatBonus") or []:
                    c["lines"].append(f"Seat: {b}")

        elif etype == "tribe" and eid in tribes:
            t = tribes[eid]
            c["icon"] = c["icon"] or f"img/tribes/{e.get('slug') or ''}.png"
            c["accent"] = t.get("color") or ""
            if t.get("defaultDiplomacy"):
                c["lines"].append(f"Default diplomacy: {t['defaultDiplomacy']}")

        elif etype == "theology" and eid in theologies:
            th = theologies[eid]
            if th.get("_tier"):
                c["chips"].append(th["_tier"])
            if th.get("cost"):
                c["cost"] = [f"{th['cost']} Civics"]
            c["lines"].extend(th.get("effects") or [])
            for be in th.get("buildingEffects") or []:
                effs = "; ".join(be.get("effects") or [])
                if be.get("building") and effs:
                    c["lines"].append(f"{be['building']}: {effs}")

        elif etype == "yield":
            key = eid.replace("YIELD_", "")
            c["accent"] = yield_colors.get(key) or ""

        elif etype == "promotion" and eid in promotions:
            c["lines"].extend(promotions[eid].get("effects") or [])

        elif etype == "project" and eid in projects:
            p = projects[eid]
            c["icon"] = c["icon"] or p.get("icon") or ""
            if p.get("cost"):
                c["cost"] = [f"{p['cost']} Civics"]
            c["lines"].extend(p.get("effects") or [])

        if not icon_exists(c["icon"]):
            c["icon"] = ""
        cards[eid] = c

    # ── promotions not in the entity registry (only 3 of 41 have aliases) ────
    for pid, p in promotions.items():
        if pid in cards:
            continue
        c = base_card(pid, p["name"], "promotion", p.get("slug") or "", "promotions")
        c["lines"] = list(p.get("effects") or [])
        if p.get("prereqName"):
            c["chips"].append(f"after {p['prereqName']}")
        cards[pid] = c

    # ── events: story parts + harvest + study ────────────────────────────────
    def trait_summary(t) -> str:
        bits = [f"{r['value']:+d} {r['rating']}" for r in t.get("ratings") or []
                if r.get("rating") and not r.get("fallback")]
        for field in ("leaderEffects", "governorEffects", "generalEffects", "modifiers"):
            bits += [str(x) for x in t.get(field) or []]
        return "; ".join(bits[:2])

    trait_names = {t["name"]: t for t in traits.values()}

    def resolve_grants(opt) -> list[tuple[str, str]]:
        """One level deeper: what a granted project/improvement/trait DOES.
        Only grant-shaped raw fields are read (aeAddProjects, AddImprovement,
        SetImprovement, aeAddTraits) — conditions never resolve."""
        found: list[tuple[str, str]] = []
        seen = set()
        for b in (opt.get("raw") or {}).get("bonuses") or []:
            for f in b.get("fields") or []:
                f = str(f)
                for rex, kind in ((r"aeAddProjects[: ]+\s*(PROJECT_[A-Z0-9_]+)", "project"),
                                  (r"(?:AddImprovement|SetImprovement)[: ]+\s*(IMPROVEMENT_[A-Z0-9_]+)", "improvement"),
                                  (r"aeAddTraits[: ]+\s*(TRAIT_[A-Z0-9_]+)", "trait")):
                    for tok in re.findall(rex, f):
                        if tok in seen:
                            continue
                        seen.add(tok)
                        if kind == "project" and tok in projects:
                            pr = projects[tok]
                            eff = "; ".join((pr.get("effects") or [])[:2])
                            if eff:
                                found.append((pr["name"], eff))
                        elif kind == "improvement":
                            imp = wonders.get(tok) or urban.get(tok) or rural.get(tok) or shrines.get(tok)
                            if imp:
                                eff = "; ".join([x for x in (imp.get("effects") or imp.get("outputs") or [])][:2])
                                if eff:
                                    found.append((imp.get("name") or imp.get("fullName") or tok, eff))
                        elif kind == "trait" and tok in traits:
                            t = traits[tok]
                            eff = trait_summary(t)
                            if eff:
                                found.append((t["name"], eff))
        return found

    def opt_rewards(opt) -> list[str]:
        out = []
        # harvest/study events carry rewards on the option; story events nest
        # them under outcomes[].rewards. Harvest trait rewards ship their
        # effect lines as `tip` — that IS the one-level-deeper description.
        for r in opt.get("rewards") or []:
            if isinstance(r, dict):
                t = r.get("text") or ""
                tips = [str(x) for x in r.get("tip") or []][:2]
                if t and tips:
                    t = f"{t} — {'; '.join(tips)}"
            else:
                t = str(r)
            if t:
                out.append(t)
        for oc in opt.get("outcomes") or []:
            if isinstance(oc, str):
                # study events humanize outcomes to plain strings
                if oc:
                    out.append(oc)
            elif isinstance(oc, dict):
                for r in oc.get("rewards") or []:
                    t = r.get("text") if isinstance(r, dict) else str(r)
                    if t:
                        out.append(t)
        return out

    def event_card(ev, category, icon=""):
        eid = ev.get("id")
        if not eid:
            return
        name = clean(ev.get("name") or ev.get("title") or "") or eid
        c = base_card(eid, name, "event")
        c["icon"] = icon if icon_exists(icon) else ""
        trig = ev.get("trigger")
        c["event"] = {
            "trigger": trig if isinstance(trig, str) else "",
            "category": category or "",
            "dlc": ev.get("dlc") or "",
            "chain": None,
            "options": [],
        }
        # study/harvest events carry their conditions on the event itself —
        # without them a card like "Inspired by Great Ziggurat" says nothing
        for pre in ev.get("prereqs") or []:
            pre = clean(str(pre))
            if pre and not pre.startswith("Study "):
                c["chips"].append(pre)
        for cond in (ev.get("conditions") or [])[:4]:
            cond = clean(str(cond))
            if cond:
                c["chips"].append(cond)
        # rewards every option gets, before any choice — tips are the trait's
        # effect lines, same one-level-deeper treatment as option rewards
        gs = []
        for g in ev.get("guaranteed") or []:
            if not (isinstance(g, dict) and g.get("text")):
                continue
            t = g["text"]
            tips = [str(x) for x in g.get("tip") or []][:2]
            gs.append(f"{t} — {'; '.join(tips)}" if tips else t)
        c["event"]["guaranteed"] = gs
        if ev.get("prob"):
            c["chips"].append(f"{ev['prob']}% · w{ev.get('weight') or 1}")
        seen_opts = {}
        for opt in ev.get("options") or []:
            rewards = opt_rewards(opt)
            for name, detail in resolve_grants(opt):
                # attach to the reward line that grants it; else its own line
                for i, r in enumerate(rewards):
                    if name in r and detail not in r:
                        rewards[i] = f"{r} — {detail}"
                        break
                else:
                    rewards.append(f"{name} — {detail}")
            o = {
                "text": clean(opt.get("text") or ""),
                "rewards": rewards,
                "reqs": [str(r) for r in opt.get("requirements") or []],
                "leadsTo": [],
            }
            # study events can list the same rolled option 3x (three offered
            # choices, one roll each) — collapse and say so
            key = (o["text"], tuple(o["rewards"]), tuple(o["reqs"]))
            if key in seen_opts:
                seen_opts[key]["_dupes"] += 1
                seen_opts[key]["text"] = f"{seen_opts[key]['_dupes']} choices — {o['text']}"
                continue
            o["_dupes"] = 1
            seen_opts[key] = o
            c["event"]["options"].append(o)
        for o in c["event"]["options"]:
            o.pop("_dupes", None)
        cards[eid] = c

    for part in sorted((DATA / "story-events" / "parts").glob("*.json")):
        d = json.loads(part.read_text())
        label = (d.get("category") or {}).get("label") or part.stem.replace("-", " ").title()
        for ev in d.get("events") or []:
            event_card(ev, label)
    # the curated trigger groups (ruins, expeditions, wonder/project/building
    # completions, family stories) — 211 of these aren't in the parts corpus,
    # and where both exist this version has the richer resolved rewards
    for group in load("events.json"):
        for ev in group.get("events") or []:
            event_card(ev, group.get("label") or "")
    for ev in load("harvest_events.json"):
        event_card(ev, "Harvest", icon=ev.get("resourceIcon") or "")
    for ev in load("study_events.json"):
        ev = dict(ev)
        study = ev.get("study")
        event_card(ev, f"Study — {study}" if study else "Study")

    # ── chain annotations from event-chains.json ─────────────────────────────
    chains_data = load("event-chains.json")
    chains_by_slug = {ch["slug"]: ch for ch in chains_data.get("chains") or []}
    for eid, meta in (chains_data.get("index") or {}).items():
        c = cards.get(eid)
        if not c or not c.get("event"):
            continue
        size = meta.get("size") or 0
        if size > 1:
            c["event"]["chain"] = {"title": meta.get("title") or "", "size": size}
        ch = chains_by_slug.get(meta.get("slug") or "")
        if not ch:
            continue
        node_key = next((n["key"] for n in ch.get("nodes") or [] if eid in (n.get("ids") or [])), None)
        if not node_key:
            continue
        # option text -> follow-up event names, resolved through the cards we
        # just built so [character] templates render the same way everywhere
        follow: dict[str, list[str]] = {}
        for edge in ch.get("edges") or []:
            if edge.get("fr") != node_key:
                continue
            to_ids = next((n.get("ids") or [] for n in ch["nodes"] if n["key"] == edge.get("to")), [])
            target = cards.get(to_ids[0])["name"] if to_ids and to_ids[0] in cards else None
            if not target:
                continue
            for label in edge.get("labels") or []:
                follow.setdefault(clean(label), [])
                if target not in follow[clean(label)]:
                    follow[clean(label)].append(target)
        for opt in c["event"]["options"]:
            if opt["text"] in follow:
                opt["leadsTo"] = follow[opt["text"]][:2]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cards, sort_keys=True, separators=(",", ":")) + "\n")
    n_events = sum(1 for c in cards.values() if c["event"])
    n_chained = sum(1 for c in cards.values() if c["event"] and c["event"]["chain"])
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(cards)} cards "
          f"({len(cards) - n_events} entities, {n_events} events, {n_chained} in chains), "
          f"{OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
