#!/usr/bin/env python3
"""
Build src/data/pillage.json — what every improvement pays when pillaged, what
pillaging does to the tile, and the few things that change the payout.

The whole mechanic is small and lives in three places:

  Unit.pillage (Unit.cs:11272)
      for each yield: getPillageYield(improvement, yield)
        = Utils.modify(improvement.aiYieldPillage[yield], pillageModifier())
      pillageModifier() = Σ effectUnit.iPillageYieldModifier over the unit's
        effect units (Unit.getEffectUnits: the unit's own, its traits', its
        promotions', and the player's effectPlayer-granted ones — that last
        hop is how EFFECTPLAYER_NATION_ASSYRIA reaches every Assyrian unit)
      the yield lands via Player.processYieldWholeTile: a bGlobal yield goes
        to the stockpile; a non-global one (Culture) goes to the pillager's
        closest city, and is simply lost if they have none
      then Tile.pillageImprovement, the PILLAGED cooldown, UNIT_PILLAGE_COST
        Orders, +5 war score against the tile's team, and (bHealPillage)
        an active-heal's worth of HP
  Tile.pillageImprovement (Tile.cs:2777)
      unfinished improvement, or bRemovePillage  → cleared outright
      otherwise → pillaged, countdown = iPillageTurns (only if > 0)
  Tile.doTurn (Tile.cs:10979)
      countdown −1 per turn; at 0 the improvement is destroyed

The XML values in aiYieldPillage are DISPLAY units (processYieldWholeTile takes
whole yields), so no ÷10 — the game's own tile text prints the same numbers.

Game.canPillageTile (Game.cs:14812) is the only eligibility test: hostile city
territory (or no territory), an improvement present, not already pillaged, and
iPillageTurns ≠ 0. Wonders, tribe settlements, holy sites, the Pillar of Edicts
and ruins have no iPillageTurns, so they can never be pillaged. A −1 means
"pillageable, but never destroyed" (shrines, Estates, Slums).

Repair (Unit.repair, Unit.cs:11500) is instant, costs UNIT_REPAIR_COST Orders,
and charges Player.getRepairCost = the full build cost through
InfoHelpers.getBuildCost(bExisting: true) (city cost modifiers included) times
any effectPlayer iRepairModifier. Burn (Unit.burn, Unit.cs:11383) is the same
tile change with no payout, no cooldown, and a flat yield.xml iBurnCost.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dlc import dlc_by_content  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
SRC = ROOT / "reference" / "Source" / "Base" / "Game" / "GameCore"
OUT = ROOT / "src" / "data" / "pillage.json"
IMG_DIR = ROOT / "public" / "img" / "icons" / "improvements"

# Rows that are identical across a family are collapsed into one row per
# (class, payout, countdown). Anything else stays one row per improvement.
AGGREGATE_CLASSES = {
    "IMPROVEMENTCLASS_SHRINE",
    "IMPROVEMENTCLASS_TEMPLE",
    "IMPROVEMENTCLASS_MONASTERY",
    "IMPROVEMENTCLASS_CATHEDRAL",
    "IMPROVEMENTCLASS_HOLY_SITE",
    "IMPROVEMENTCLASS_CULT",
}
AGGREGATE_LABEL = {
    "IMPROVEMENTCLASS_SHRINE": "Shrines",
    "IMPROVEMENTCLASS_TEMPLE": "Temples",
    "IMPROVEMENTCLASS_MONASTERY": "Monasteries",
    "IMPROVEMENTCLASS_CATHEDRAL": "Cathedrals",
    "IMPROVEMENTCLASS_HOLY_SITE": "Holy Sites",
    "IMPROVEMENTCLASS_CULT": "Cults",
}
# Where an aggregate row links when it has no entity of its own.
AGGREGATE_HREF = {
    "IMPROVEMENTCLASS_SHRINE": "shrines",
}
AGGREGATE_ENTITY = {
    "IMPROVEMENTCLASS_TEMPLE": "IMPROVEMENT_TEMPLE",
    "IMPROVEMENTCLASS_MONASTERY": "IMPROVEMENT_MONASTERY",
    "IMPROVEMENTCLASS_CATHEDRAL": "IMPROVEMENT_CATHEDRAL",
    "IMPROVEMENTCLASS_HOLY_SITE": "IMPROVEMENT_HOLY_SITE",
}
AGGREGATE_ICON = {
    "IMPROVEMENTCLASS_TEMPLE": "temple.png",
    "IMPROVEMENTCLASS_CATHEDRAL": "cathedral.png",
}


# ---------------------------------------------------------------- helpers ---
def parse(name: str) -> ET.Element | None:
    p = XML_DIR / name
    return ET.parse(p).getroot() if p.exists() else None


def load_text() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(XML_DIR.glob("text-*.xml")):
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            if k and k not in out:
                out[k] = e.findtext("en-US") or ""
    return out


_ICON_RE = re.compile(r"icon\([A-Z_]+\)")
_LINK_RE = re.compile(r"link\(([A-Z_]+)(?:,\d+)?\)")


def clean_name(s: str) -> str:
    """First gender form, minus icon(...) markers."""
    s = (s or "").split("~")[0]
    return _ICON_RE.sub("", s).strip()


def pairs(e: ET.Element, tag: str) -> "OrderedDict[str, int]":
    out: "OrderedDict[str, int]" = OrderedDict()
    for p in e.findall(f"{tag}/Pair"):
        k = p.findtext("zIndex") or ""
        v = int(p.findtext("iValue") or 0)
        if k and v:
            out[k] = v
    return out


def int_of(e: ET.Element, tag: str, default: int = 0) -> int:
    t = e.findtext(tag)
    return int(t) if t not in (None, "") else default


def flag(e: ET.Element, tag: str) -> bool:
    return e.findtext(tag) == "1"


def find_line(path: Path, needle: str) -> int:
    for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if needle in line:
            return i
    raise SystemExit(f"{path.name}: `{needle}` not found — re-check the citation")


def cite(file: str, needle: str) -> str:
    return f"{file}:{find_line(SRC / file, needle)}"


# ------------------------------------------------------------------ main ---
def main() -> None:
    text = load_text()
    dlc_label = dlc_by_content()

    def name_of(e: ET.Element, strip: str = "IMPROVEMENT_") -> str:
        """Name, else GenderedName (GENDERED_TEXT_X → TEXT_X), else the id."""
        key = e.findtext("Name") or ""
        if not key:
            key = (e.findtext("GenderedName") or "").replace("GENDERED_", "", 1)
        return clean_name(text.get(key, "")) or (e.findtext("zType") or "").replace(strip, "", 1).replace("_", " ").title()

    yields_xml = parse("yield.xml")
    assert yields_xml is not None
    yield_info: dict[str, dict] = {}
    for e in yields_xml.findall("Entry"):
        t = e.findtext("zType")
        if not t:
            continue
        yield_info[t] = {
            "id": t,
            "name": clean_name(text.get(e.findtext("Name") or "", "")) or t.replace("YIELD_", "").title(),
            "global": flag(e, "bGlobal"),
            "burnCost": int_of(e, "iBurnCost"),
        }

    # Existing per-page datasets: the slug each improvement is rendered under,
    # and the icon those pages already resolved (never re-derive either).
    slug_by_id: dict[str, str] = {}
    icon_by_id: dict[str, str] = {}
    for fn in ("rural_improvements.json", "urban_improvements.json"):
        for row in json.loads((ROOT / "src" / "data" / fn).read_text()):
            slug_by_id[row["id"]] = row["slug"]
            if row.get("icon"):
                icon_by_id[row["id"]] = row["icon"]
    ents = json.loads((ROOT / "src" / "data" / "entities.json").read_text())["entities"]
    ent_by_id = {e["id"]: e for e in ents}
    ent_by_slug = {e["slug"]: e["id"] for e in ents if e["type"] == "improvement"}

    # The three Stele tiers render as one row on /nations/aksum (entity
    # IMPROVEMENT_STELE); nothing else needs a hand mapping.
    ENTITY_ALIAS = {f"IMPROVEMENT_AKSUM_STELE_{i}": "IMPROVEMENT_STELE" for i in (1, 2, 3)}

    def entity_for(imp_id: str) -> str:
        if imp_id in ent_by_id:
            return imp_id
        if ENTITY_ALIAS.get(imp_id) in ent_by_id:
            return ENTITY_ALIAS[imp_id]
        slug = slug_by_id.get(imp_id)
        return ent_by_slug.get(slug, "") if slug else ""

    def icon_for(imp_id: str, cls: str) -> str:
        if imp_id in icon_by_id:
            return icon_by_id[imp_id]
        # world-religion buildings: <religion>_<kind>.png or <adjective>_<kind>.png
        m = re.match(r"IMPROVEMENT_(TEMPLE|MONASTERY|CATHEDRAL|HOLY_SITE)_([A-Z]+)$", imp_id)
        if m:
            kind, rel = m.group(1).lower(), m.group(2).lower()
            adj = {"hinduism": "hindu", "buddhism": "buddhist"}.get(rel, rel)
            for cand in (f"{rel}_{kind}.png", f"{adj}_{kind}.png", f"{kind}_{rel}.png"):
                if (IMG_DIR / cand).exists():
                    return f"img/icons/improvements/{cand}"
        stem = imp_id.replace("IMPROVEMENT_", "").lower()
        if (IMG_DIR / f"{stem}.png").exists():
            return f"img/icons/improvements/{stem}.png"
        return ""

    class_names: dict[str, str] = {}
    ic = parse("improvementClass.xml")
    if ic is not None:
        for e in ic.findall("Entry"):
            t = e.findtext("zType")
            if t:
                class_names[t] = clean_name(text.get(e.findtext("Name") or "", "")) or t.replace("IMPROVEMENTCLASS_", "").replace("_", " ").title()

    # ---- every improvement, every file -------------------------------------
    raw_rows: list[dict] = []
    unpillageable: list[dict] = []
    # improvement.xml plus the DLC/event copies (improvement-event-*.xml);
    # NOT improvementClass.xml, which the same glob would catch.
    files = [p for p in sorted(XML_DIR.glob("improvement*.xml")) if p.name == "improvement.xml" or p.name.startswith("improvement-")]
    for p in files:
        for e in ET.parse(p).getroot().findall("Entry"):
            imp_id = e.findtext("zType")
            if not imp_id:
                continue
            turns_raw = e.findtext("iPillageTurns")
            turns = int(turns_raw) if turns_raw not in (None, "") else 0
            remove = flag(e, "bRemovePillage")
            payout = pairs(e, "aiYieldPillage")
            cls = e.findtext("Class") or ""
            content = e.findtext("GameContentRequired") or ""
            row = {
                "id": imp_id,
                "name": name_of(e),
                "class": cls,
                "className": class_names.get(cls, AGGREGATE_LABEL.get(cls, "")),
                "file": p.name,
                "event": p.name != "improvement.xml",
                "dlc": dlc_label.get(content, "") if content else "",
                "wonder": flag(e, "bWonder"),
                "urban": flag(e, "bUrban"),
                "tribe": flag(e, "bTribe"),
                "turns": turns,
                "removeOnPillage": remove,
                "payout": payout,
                "buildCost": pairs(e, "aiYieldCost"),
                "entityId": entity_for(imp_id),
                "icon": icon_for(imp_id, cls),
            }
            # Game.canPillageTile: iPillageTurns == 0 → never. bRemovePillage
            # alone (Shrine of Victory) still needs a non-zero countdown to be
            # a target, and the game gives it none.
            if turns == 0:
                unpillageable.append(row)
            else:
                raw_rows.append(row)

    # ---- collapse identical families ---------------------------------------
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    rows: list[dict] = []
    for r in raw_rows:
        if r["class"] in AGGREGATE_CLASSES:
            key = (r["class"], tuple(r["payout"].items()), r["turns"], r["removeOnPillage"], tuple(r["buildCost"].items()), r["event"])
            g = groups.get(key)
            if g is None:
                g = dict(r)
                g["id"] = f"GROUP_{r['class']}_{len(groups)}"
                g["name"] = AGGREGATE_LABEL.get(r["class"], r["className"])
                g["members"] = []
                g["entityId"] = AGGREGATE_ENTITY.get(r["class"], "")
                g["href"] = AGGREGATE_HREF.get(r["class"], "")
                icon = AGGREGATE_ICON.get(r["class"])
                g["icon"] = f"img/icons/improvements/{icon}" if icon and (IMG_DIR / icon).exists() else (r["icon"] if r["class"] != "IMPROVEMENTCLASS_SHRINE" else "")
                groups[key] = g
                rows.append(g)
            g["members"].append({"id": r["id"], "name": r["name"], "dlc": r["dlc"]})
        else:
            r["members"] = []
            r["href"] = ""
            rows.append(r)
    for g in rows:
        if g["members"]:
            dlcs = sorted({m["dlc"] for m in g["members"] if m["dlc"]})
            g["dlc"] = ", ".join(dlcs) if len(dlcs) == 1 else ""
            g["count"] = len(g["members"])
            if g["count"] == 1:
                g["name"] = g["members"][0]["name"]
        else:
            g["count"] = 1

    def bucket(r: dict) -> str:
        if r["event"]:
            return "event"
        if r["class"] in ("IMPROVEMENTCLASS_SHRINE",):
            return "shrine"
        if r["class"] in ("IMPROVEMENTCLASS_TEMPLE", "IMPROVEMENTCLASS_MONASTERY", "IMPROVEMENTCLASS_CATHEDRAL", "IMPROVEMENTCLASS_HOLY_SITE"):
            return "religion"
        if r["class"] in ("IMPROVEMENTCLASS_AKSUM_STELE", "IMPROVEMENTCLASS_KUSHITE_PYRAMIDS", "IMPROVEMENTCLASS_ALTAR_ATEN"):
            return "unique"
        return "urban" if r["urban"] else "rural"

    for r in rows:
        r["bucket"] = bucket(r)
    order = {"rural": 0, "urban": 1, "religion": 2, "shrine": 3, "unique": 4, "event": 5}
    rows.sort(key=lambda r: (order[r["bucket"]], 0 if r["bucket"] != "rural" else 0))

    # ---- who changes the payout / heals / repairs cheaper -------------------
    eu = parse("effectUnit.xml")
    ep = parse("effectPlayer.xml")
    assert eu is not None and ep is not None
    nation_xml = parse("nation.xml")
    trait_xml = parse("trait.xml")
    dynasty_xml = parse("dynasty.xml")
    assert nation_xml is not None and trait_xml is not None

    def carriers_of_effect_player(ep_id: str) -> list[dict]:
        out: list[dict] = []
        for n in nation_xml.findall("Entry"):
            if n.findtext("EffectPlayer") == ep_id:
                nid = n.findtext("zType") or ""
                out.append({"kind": "nation", "id": nid, "name": name_of(n, "NATION_")})
        # A trait reaches units through a role: LeaderEffectPlayer applies to
        # every unit while that character rules; GeneralEffectUnit /
        # LeaderEffectUnit only to the unit the character commands.
        for t in trait_xml.findall("Entry"):
            for tag, note in (("EffectPlayer", ""), ("LeaderEffectPlayer", "as leader")):
                if t.findtext(tag) == ep_id:
                    tid = t.findtext("zType") or ""
                    out.append({"kind": "archetype" if tid in ent_by_id and ent_by_id[tid]["type"] == "archetype" else "trait",
                                "id": tid, "name": ent_by_id[tid]["name"] if tid in ent_by_id else name_of(t, "TRAIT_"), "note": note})
        return out

    effect_unit_carriers: dict[str, list[dict]] = {}
    for e in ep.findall("Entry"):
        ep_id = e.findtext("zType") or ""
        for eu_ref in e.findall("EffectUnit"):
            if eu_ref.text:
                effect_unit_carriers.setdefault(eu_ref.text, []).extend(carriers_of_effect_player(ep_id))
    # Promotions, unit traits and character traits (as general / as leader)
    # can also carry an effectUnit; none set the pillage fields today, but the
    # walk has to cover every path Unit.getEffectUnits reads.
    for fn, kind, tag, note in (
        ("promotion.xml", "promotion", "EffectUnit", ""),
        ("unitTrait.xml", "unitTrait", "EffectUnit", ""),
        ("trait.xml", "trait", "GeneralEffectUnit", "as general"),
        ("trait.xml", "trait", "LeaderEffectUnit", "as leader"),
    ):
        x = parse(fn)
        if x is None:
            continue
        for e in x.findall("Entry"):
            ref = e.findtext(tag)
            if ref:
                tid = e.findtext("zType") or ""
                effect_unit_carriers.setdefault(ref, []).append({
                    "kind": "archetype" if tid in ent_by_id and ent_by_id[tid]["type"] == "archetype" else kind,
                    "id": tid, "name": ent_by_id[tid]["name"] if tid in ent_by_id else name_of(e, ""), "note": note})

    payout_modifiers: list[dict] = []
    heal_on_pillage: list[dict] = []
    for e in eu.findall("Entry"):
        eu_id = e.findtext("zType") or ""
        mod = int_of(e, "iPillageYieldModifier")
        if mod:
            payout_modifiers.append({"id": eu_id, "value": mod, "carriers": effect_unit_carriers.get(eu_id, [])})
        if flag(e, "bHealPillage"):
            heal_on_pillage.append({"id": eu_id, "carriers": effect_unit_carriers.get(eu_id, [])})

    repair_modifiers: list[dict] = []
    for e in ep.findall("Entry"):
        v = int_of(e, "iRepairModifier")
        if v:
            ep_id = e.findtext("zType") or ""
            carriers = carriers_of_effect_player(ep_id)
            if dynasty_xml is not None:
                for d in dynasty_xml.findall("Entry"):
                    if d.findtext("EffectPlayer") == ep_id:
                        nat = d.findtext("Nation") or ""
                        nat_e = next((n for n in nation_xml.findall("Entry") if n.findtext("zType") == nat), None)
                        carriers.append({
                            "kind": "dynasty", "id": d.findtext("zType") or "", "name": name_of(d, "DYNASTY_"),
                            "nationId": nat, "nationName": name_of(nat_e, "NATION_") if nat_e is not None else nat,
                            "dlc": dlc_label.get(d.findtext("GameContentRequired") or "", ""),
                        })
            repair_modifiers.append({"id": ep_id, "value": v, "carriers": carriers})

    # ---- who can pillage ---------------------------------------------------
    unit_xml = parse("unit.xml")
    assert unit_xml is not None
    cannot: list[dict] = []
    can_count = 0
    for e in unit_xml.findall("Entry"):
        uid = e.findtext("zType")
        if not uid:
            continue
        traits = [x.text for x in e.findall("aeUnitTrait/zValue") if x.text]
        if flag(e, "bPillage"):
            can_count += 1
        elif "UNITTRAIT_SIEGE" in traits:
            # Every land unit with bPillage can pillage; the only combat units
            # without it are the siege line (the rest are civilians).
            cannot.append({"id": uid, "name": name_of(e, "UNIT_")})

    # ---- other ways a tile gets pillaged -----------------------------------
    occ_slugs: dict[str, str] = {}
    occ_json = ROOT / "src" / "data" / "occurrences.json"
    if occ_json.exists():
        for fam in json.loads(occ_json.read_text()).get("calamityFamilies", []):
            for k in ("full", "mitigated"):
                o = fam.get(k)
                if o:
                    occ_slugs[o["id"]] = o["slug"]
    occurrences: list[dict] = []
    occ = parse("occurrence.xml")
    if occ is not None:
        for e in occ.findall("Entry"):
            oid = e.findtext("zType") or ""
            always = flag(e, "bTilePillage")
            chance = int_of(e, "iTilePillageChance")
            if always or chance:
                occurrences.append({
                    "id": oid,
                    "name": name_of(e, "OCCURRENCE_"),
                    "slug": occ_slugs.get(oid, ""),
                    "chance": 100 if always else chance,
                })

    events: list[dict] = []
    ev_index = {x["i"]: x for x in json.loads((ROOT / "src" / "data" / "event-search.json").read_text())}
    trigger_label = {
        "EVENTTRIGGER_IMPROVEMENT_PILLAGED_US": "you pillaged someone",
        "EVENTTRIGGER_IMPROVEMENT_PILLAGED_ENEMY": "a nation pillaged you",
        "EVENTTRIGGER_IMPROVEMENT_PILLAGED_TRIBE": "a tribe pillaged you",
    }
    for p in sorted(XML_DIR.glob("eventStory*.xml")):
        for e in ET.parse(p).getroot().findall("Entry"):
            tr = e.findtext("Trigger") or ""
            if tr not in trigger_label:
                continue
            eid = e.findtext("zType") or ""
            hit = ev_index.get(eid)
            events.append({
                "id": eid,
                "name": (hit or {}).get("n") or clean_name(text.get(e.findtext("Name") or "", "")) or eid,
                "trigger": tr,
                "when": trigger_label[tr],
                "href": (hit or {}).get("h", ""),
                "dlc": dlc_label.get(e.findtext("GameContentRequired") or "", ""),
            })
    events.sort(key=lambda x: (list(trigger_label).index(x["trigger"]), x["name"]))

    bonus_pillage = 0
    for p in sorted(XML_DIR.glob("bonus*.xml")):
        for e in ET.parse(p).getroot().findall("Entry"):
            if flag(e, "bPillageImprovement") or flag(e, "bPillageAdjacent"):
                bonus_pillage += 1

    fam_class = parse("familyClass.xml")
    family_opinion: list[dict] = []
    if fam_class is not None:
        for e in fam_class.findall("Entry"):
            v = int_of(e, "iPillagedOpinion")
            if v:
                fid = e.findtext("zType") or ""
                family_opinion.append({"id": fid, "name": name_of(e, "FAMILYCLASS_"), "value": v})

    tribes: list[dict] = []
    tx = parse("tribe.xml")
    if tx is not None:
        for e in tx.findall("Entry"):
            v = int_of(e, "iPillagePriority")
            if v:
                tid = e.findtext("zType") or ""
                tribes.append({"id": tid, "name": name_of(e, "TRIBE_"), "priority": v})

    goals: list[dict] = []
    gx = parse("goal.xml")
    if gx is not None:
        for e in gx.findall("Entry"):
            gid = e.findtext("zType") or ""
            if "PILLAGED" in gid:
                goals.append({"id": gid, "name": _LINK_RE.sub(lambda m: clean_name(text.get("TEXT_" + m.group(1), m.group(1).split("_")[-1].title())), text.get(e.findtext("Name") or "", "")).strip()})

    cognomens: list[dict] = []
    cx = parse("cognomen.xml")
    if cx is not None:
        for e in cx.findall("Entry"):
            for pr in e.findall("aiStatValue/Pair"):
                if pr.findtext("zIndex") == "STAT_IMPROVEMENT_PILLAGED":
                    cid = e.findtext("zType") or ""
                    cognomens.append({"id": cid, "name": name_of(e, "COGNOMEN_"), "value": int(pr.findtext("iValue") or 0)})

    gi = parse("globalsInt.xml")
    assert gi is not None
    gint = {e.findtext("zType"): int(e.findtext("iValue") or 0) for e in gi.findall("Entry") if e.findtext("zType")}

    data = {
        "patchNote": "aiYieldPillage values are whole yields (no ÷10): Player.processYieldWholeTile.",
        "globals": {
            "pillageOrders": gint.get("UNIT_PILLAGE_COST", 1),
            "repairOrders": gint.get("UNIT_REPAIR_COST", 1),
            "warScore": 5,
            "warScoreContext": {"killUnit": 10, "captureUnit": 50, "captureCity": 100},
            "burnCost": {y["id"]: y["burnCost"] for y in yield_info.values() if y["burnCost"]},
        },
        "yields": {k: {"name": v["name"], "global": v["global"]} for k, v in yield_info.items()},
        "payoutModifiers": payout_modifiers,
        "healOnPillage": heal_on_pillage,
        "repairModifiers": repair_modifiers,
        "rows": rows,
        "unpillageable": unpillageable,
        "units": {"canPillage": can_count, "cannot": cannot},
        "occurrences": occurrences,
        "events": events,
        "bonusPillageCount": bonus_pillage,
        "familyOpinion": family_opinion,
        "tribes": tribes,
        "goals": goals,
        "cognomens": cognomens,
        "code": {
            "pillage": cite("Unit.cs", "public virtual void pillage(Player pActingPlayer)"),
            "getPillageYield": cite("Unit.cs", "public virtual int getPillageYield("),
            "pillageModifier": cite("Unit.cs", "public virtual int pillageModifier()"),
            "canPillageTile": cite("Game.cs", "public virtual bool canPillageTile("),
            "pillageImprovement": cite("Tile.cs", "public virtual void pillageImprovement("),
            "doTurn": cite("Tile.cs", "public virtual void doTurn()"),
            "loadPillaged": cite("Tile.cs", "public virtual void loadPillaged("),
            "repair": cite("Unit.cs", "public virtual void repair(Player pActingPlayer"),
            "getRepairCost": cite("Player.cs", "public virtual int getRepairCost("),
            "burn": cite("Unit.cs", "public virtual void burn(Player pActingPlayer)"),
            "canBurn": cite("Unit.cs", "public virtual bool canBurn("),
            "processYieldWholeTile": cite("Player.cs", "public virtual bool processYieldWholeTile("),
            "modify": cite("Utils.cs", "public virtual int modify(int iValue, int iModifier"),
            "razeCity": cite("Game.cs", "public virtual void razeCity("),
            "familyOpinion": cite("PlayerOpinion.cs", "calculateFamilyOpinionPillaged("),
            "aiSkipsNoPayout": cite("PlayerAI.cs", "maiYieldPillage.Count == 0"),
            "aiRepairPriority": cite("UnitRoleManager.cs", "2 * pTile.getImprovementPillageTurns() < pTile.improvement().miPillageTurns"),
            "occurrencePillage": cite("Game.cs", "occurrence.mbTilePillage || occurrence.miTilePillageChance > 0"),
        },
    }
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} rows ({len(raw_rows)} improvements), "
          f"{len(unpillageable)} unpillageable, {len(payout_modifiers)} payout modifier(s), "
          f"{len(events)} events, {len(occurrences)} occurrences")


if __name__ == "__main__":
    main()
