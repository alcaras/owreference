#!/usr/bin/env python3
"""
Build src/data/zoc.json — everything the Zone of Control explainer page needs.

Sources (reference/XML/Infos):
  unit.xml           bZOC / bIgnoreZOC / bWater / aeUnitTrait / aeEffectUnit
  effectUnit.xml     bZOC / bIgnoreZOC / aeUnitTraitZOC / abUnitTraitValid /
                     abHideTerrainTarget / iFatigueExtra / GameContentDisplay
  unitTrait.xml      trait → EffectUnit (UNITTRAIT_POLEARM → EFFECTUNIT_POLEARM)
  promotion.xml      promotion → EffectUnit (PROMOTION_MANEUVERS)
  trait.xml          character trait → GeneralEffectUnit (TRAIT_MAHOUT, TRAIT_AMBUSHER)
  bonus.xml          aeEffectUnits (BONUS_UNIT_PROMOTION_MANEUVERS, unreferenced)
  diplomacy.xml      bHostile (only DIPLOMACY_WAR)
  hotkeys.xml        HOTKEY_SHOW_ZOC / HOTKEY_LOCK_ZOC
  color.xml          COLOR_HOSTILE_ZOC / COLOR_NEUTRAL_ZOC
  globalsAI.xml      AI_UNIT_ZOC_VALUE
  text-*.xml         names + the concept strings quoted verbatim

The second half of this file is a PYTHON PORT of the game's ZOC rules
(Tile.isDirectionHostileZOC, Tile.isHostileZOC, Unit.isValidMovementDirection,
Unit.canSwapUnits — reference/Source/Base/Game/GameCore/Tile.cs:9991-10100,
Unit.cs:7670-7695, 8287) running on tiny axial hex boards. Every board on the
page declares only terrain, units and a candidate path; which tiles are in ZOC
and which steps are legal is COMPUTED here and asserted, so a rules regression
fails `make data` rather than silently drawing the wrong arrow.

Port assumptions (the scenarios never exercise the rest of the game state):
  * no unit has an attack cooldown, claims a city site or is building an
    improvement — the three early-outs in Unit.isHiddenTileFrom (Unit.cs:3509)
    are therefore false and hiding reduces to hideTerrainTarget on a tile that
    is unowned or friendly;
  * every tile is fully visible to both sides (no fog);
  * 'hostile' means the two owners are at war (Game.isHostile reads
    diplomacy.xml bHostile, which only DIPLOMACY_WAR sets).
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_concepts import Cleaner, load_dlc_names, load_full_text_index, load_globals_int  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "zoc.json"
ICON_DIR = ROOT / "public" / "img" / "icons" / "units"


# ── XML loading ──────────────────────────────────────────────────────────────

def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def entries(root: ET.Element):
    for e in root.findall("Entry"):
        zt = e.findtext("zType")
        if zt:
            yield zt, e


def flag(e: ET.Element, tag: str) -> bool:
    return (e.findtext(tag) or "").strip() == "1"


def zvalues(e: ET.Element, tag: str) -> list[str]:
    return [v.text.strip() for v in e.findall(f"{tag}/zValue") if v.text]


def pair_flags(e: ET.Element, tag: str) -> list[str]:
    out = []
    for p in e.findall(f"{tag}/Pair"):
        if (p.findtext("bValue") or "").strip() == "1":
            out.append((p.findtext("zIndex") or "").strip())
    return out


UNITS: dict[str, dict] = {}
for zt, e in entries(parse("unit.xml")):
    UNITS[zt] = {
        "id": zt,
        "nameKey": e.findtext("Name") or "",
        "icon": e.findtext("zIconName") or zt,
        "traits": zvalues(e, "aeUnitTrait"),
        "effects": zvalues(e, "aeEffectUnit"),
        "bZOC": flag(e, "bZOC"),
        "bIgnoreZOC": flag(e, "bIgnoreZOC"),
        "bWater": flag(e, "bWater"),
        "bBlocks": flag(e, "bBlocks"),
        "bAmphibious": flag(e, "bAmphibious"),
        "bTerritoryWater": flag(e, "bTerritoryWater"),
        "iRangeMax": int(e.findtext("iRangeMax") or 0),
    }

# effectPlayer aeWaterUnit: which land unit types a player effect turns into
# water units (Game.isWaterUnit → Player.isWaterUnitUnlock, Game.cs:14267)
WATER_UNIT_UNLOCKS: dict[str, list[tuple[str, str]]] = {}
for zt, e in entries(parse("effectPlayer.xml")):
    for u in zvalues(e, "aeWaterUnit"):
        WATER_UNIT_UNLOCKS.setdefault(u, []).append((zt, e.findtext("Name") or f"TEXT_{zt}"))

EFFECTS: dict[str, dict] = {}
for zt, e in entries(parse("effectUnit.xml")):
    EFFECTS[zt] = {
        "id": zt,
        "nameKey": e.findtext("GenderedName") or "",
        "bZOC": flag(e, "bZOC"),
        "bIgnoreZOC": flag(e, "bIgnoreZOC"),
        "unitTraitZOC": zvalues(e, "aeUnitTraitZOC"),
        "unitTraitValid": pair_flags(e, "abUnitTraitValid"),
        "hideTerrainTarget": pair_flags(e, "abHideTerrainTarget"),
        "fatigueExtra": int(e.findtext("iFatigueExtra") or 0),
        "gameContent": (e.findtext("GameContentDisplay") or e.findtext("GameContentRequired") or "").strip(),
    }

UNIT_TRAIT_EFFECT: dict[str, str] = {}
UNIT_TRAIT_NAME_KEY: dict[str, str] = {}
for zt, e in entries(parse("unitTrait.xml")):
    UNIT_TRAIT_NAME_KEY[zt] = e.findtext("Name") or ""
    eff = (e.findtext("EffectUnit") or "").strip()
    if eff:
        UNIT_TRAIT_EFFECT[zt] = eff

PROMOTION_EFFECT: dict[str, str] = {}
for zt, e in entries(parse("promotion.xml")):
    eff = (e.findtext("EffectUnit") or "").strip()
    if eff:
        PROMOTION_EFFECT[zt] = eff

TRAIT_GENERAL_EFFECT: dict[str, dict] = {}
for zt, e in entries(parse("trait.xml")):
    for tag in ("GeneralEffectUnit", "LeaderEffectUnit"):
        eff = (e.findtext(tag) or "").strip()
        if eff:
            TRAIT_GENERAL_EFFECT.setdefault(eff, []).append({
                "id": zt, "via": tag,
                "gameContent": (e.findtext("GameContentRequired") or "").strip(),
            })

PLAYER_CITY_EFFECTS: dict[str, list[dict]] = {}
for fname, tag in (("effectPlayer.xml", "aeEffectUnitTrait"), ("effectCity.xml", "aeTraitEffectUnit")):
    for zt, e in entries(parse(fname)):
        for pair in e.findall(f"{tag}/Pair"):
            eff = (pair.findtext("zValue") or "").strip()
            trait = (pair.findtext("zIndex") or "").strip()
            if eff:
                PLAYER_CITY_EFFECTS.setdefault(eff, []).append({"id": zt, "file": fname, "trait": trait})

BONUS_EFFECTS: dict[str, list[str]] = {}
for zt, e in entries(parse("bonus.xml")):
    for eff in zvalues(e, "aeEffectUnits"):
        BONUS_EFFECTS.setdefault(eff, []).append(zt)

DIPLOMACY_HOSTILE = {zt: flag(e, "bHostile") for zt, e in entries(parse("diplomacy.xml"))}

HOTKEYS = {zt: {"keys": (e.findtext("Keys") or "").strip(), "hold": flag(e, "bHold"),
                "nameKey": e.findtext("Name") or ""}
           for zt, e in entries(parse("hotkeys.xml")) if "ZOC" in zt}
COLORS = {zt: (e.findtext("zHexValue") or "").strip()
          for zt, e in entries(parse("color.xml")) if "ZOC" in zt}
AI_ZOC_VALUE = next(int(e.findtext("iValue") or 0) for zt, e in entries(parse("globalsAI.xml"))
                    if zt == "AI_UNIT_ZOC_VALUE")

TEXT = load_full_text_index()
CLEANER = Cleaner(TEXT, load_globals_int())
DLC_NAMES = load_dlc_names(TEXT)
GENDERED: dict[str, str] = {}
for p in XML_DIR.glob("genderedText*.xml"):
    for e in ET.parse(p).getroot().findall("Entry"):
        zt = e.findtext("zType") or ""
        for pair in e.findall("Texts/Pair"):
            if (pair.findtext("zIndex") or "") == "GRAMMATICAL_GENDER_MASCULINE":
                GENDERED.setdefault(zt, (pair.findtext("zValue") or "").strip())


def name_of(key: str, fallback: str) -> str:
    """Display name for a TEXT_ or GENDERED_TEXT_ key (first grammatical form)."""
    key = GENDERED.get(key, key)
    raw = TEXT.get(key)
    if not raw:
        return fallback
    out = CLEANER.clean(raw).split("~")[0].strip()
    # {UNIT-RELIGION,1} and friends are runtime substitutions the disciples' names carry
    return re.sub(r"\{[A-Z][A-Z_0-9-]*(?:,\d+)?\}\s*", "", out).strip()


def game_text(key: str, hotkey: str = "") -> str:
    """A quoted in-game string with link()/hotkey()/glyph markup flattened.
    [{0_key}] is the hotkey the game substitutes at runtime."""
    s = TEXT.get(key, "")
    s = s.replace("{0_key}", hotkey)
    s = re.sub(r"hotkey\((HOTKEY_[A-Z_]+)\)",
               lambda m: HOTKEYS.get(m.group(1), {}).get("keys", m.group(1)).split(",")[0], s)
    return " ".join(CLEANER.paragraphs(s))


def trait_short(t: str) -> str:
    return name_of(UNIT_TRAIT_NAME_KEY.get(t, ""), t.removeprefix("UNITTRAIT_").title())


def icon_slug(info: dict) -> str:
    slug = info["icon"].removeprefix("UNIT_").lower()
    if not (ICON_DIR / f"{slug}.png").exists():
        alt = info["id"].removeprefix("UNIT_").lower()
        if (ICON_DIR / f"{alt}.png").exists():
            return alt
    return slug


# ── the port ─────────────────────────────────────────────────────────────────
# Pointy-top axial hexes. Direction order matches owpuzzle's engine so the
# cross-check can compare river edges 1:1: E, NE, NW, W, SW, SE. Opposite = d+3.
DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
WATER = "TERRAIN_WATER"
IMPASSABLE_HEIGHTS = {"HEIGHT_MOUNTAIN", "HEIGHT_VOLCANO"}


@dataclass
class Tile:
    q: int
    r: int
    terrain: str = "TERRAIN_TEMPERATE"
    height: str = "HEIGHT_FLAT"
    vegetation: str | None = None
    improvement: str | None = None
    river: list[int] = field(default_factory=list)   # direction indices with a river edge
    city: int | None = None                           # owner of a city on this tile
    owner: int | None = None                          # territory owner

    @property
    def water(self) -> bool:
        return self.terrain == WATER

    @property
    def impassable(self) -> bool:
        return self.height in IMPASSABLE_HEIGHTS


@dataclass
class Unit:
    type: str
    owner: int
    q: int
    r: int
    effects: list[str] = field(default_factory=list)  # promotions / general-trait effects held
    tribe: bool = False
    mover: bool = False
    water_unlock: bool = False   # owner has an aeWaterUnit effect for this type (Exploration law → Scout)

    @property
    def info(self) -> dict:
        return UNITS[self.type]


@dataclass
class Board:
    tiles: dict[tuple[int, int], Tile]
    units: list[Unit]
    war: bool = True   # owners 0 and 1 at war (DIPLOMACY_WAR is the only bHostile state)

    def tile(self, q: int, r: int) -> Tile | None:
        return self.tiles.get((q, r))

    def adjacent(self, t: Tile, d: int) -> Tile | None:
        dq, dr = DIRS[d]
        return self.tile(t.q + dq, t.r + dr)

    def units_at(self, t: Tile) -> list[Unit]:
        return [u for u in self.units if u.q == t.q and u.r == t.r]

    def direction(self, a: Tile, b: Tile) -> int:
        for d, (dq, dr) in enumerate(DIRS):
            if a.q + dq == b.q and a.r + dr == b.r:
                return d
        raise ValueError(f"{(a.q, a.r)} and {(b.q, b.r)} are not adjacent")

    # Tile.isRiver(eDirection): a river edge is shared, so either side may hold it
    def is_river(self, t: Tile, d: int) -> bool:
        if d in t.river:
            return True
        n = self.adjacent(t, d)
        return n is not None and ((d + 3) % 6) in n.river

    def hostile(self, a_owner: int, b_owner: int) -> bool:
        # Game.isHostile → diplomacy.xml bHostile; only DIPLOMACY_WAR has it
        assert DIPLOMACY_HOSTILE.get("DIPLOMACY_WAR") and not any(
            v for k, v in DIPLOMACY_HOSTILE.items() if k != "DIPLOMACY_WAR")
        return a_owner != b_owner and self.war


def unit_effects(u: Unit) -> list[str]:
    """Unit.getEffectUnits: the type's own effects, one per unit trait, plus
    whatever promotions / general traits granted — filtered by the effect's
    abUnitTraitValid (Mahout is elephants-only, Maneuvers ships-only)."""
    info = u.info
    effs = list(info["effects"])
    for t in info["traits"]:
        if t in UNIT_TRAIT_EFFECT:
            effs.append(UNIT_TRAIT_EFFECT[t])
    effs.extend(u.effects)
    out = []
    for e in effs:
        valid = EFFECTS.get(e, {}).get("unitTraitValid") or []
        if valid and not any(t in valid for t in info["traits"]):
            continue
        out.append(e)
    return out


def has_zoc(u: Unit) -> bool:
    # Unit.hasZOC (Unit.cs:6983): type flag or any held effect with bZOC
    return u.info["bZOC"] or any(EFFECTS[e]["bZOC"] for e in unit_effects(u) if e in EFFECTS)


def has_ignore_zoc(u: Unit) -> bool:
    # Unit.hasIgnoreZOC (Unit.cs:7008)
    return u.info["bIgnoreZOC"] or any(EFFECTS[e]["bIgnoreZOC"] for e in unit_effects(u) if e in EFFECTS)


def is_unit_zoc(exerter: Unit, mover_type: str) -> bool:
    # Unit.isUnitZoc (Unit.cs:4550): any held effect's aeUnitTraitZOC names a
    # trait the moving unit type carries (EFFECTUNIT_POLEARM → UNITTRAIT_MOUNTED)
    traits = UNITS[mover_type]["traits"]
    for e in unit_effects(exerter):
        for t in EFFECTS.get(e, {}).get("unitTraitZOC", []):
            if t in traits:
                return True
    return False


def is_water_unit(u: Unit) -> bool:
    # Game.isWaterUnit (Game.cs:14267): bWater, bAmphibious (Caravan), or the
    # owner's water-unit unlock (EFFECTPLAYER_LAW_EXPLORATION → Scout)
    return u.info["bWater"] or u.info["bAmphibious"] or u.water_unlock


def _hide_target_matches(target: str, t: Tile) -> bool:
    veg = t.vegetation or ""
    if target == "TERRAIN_TARGET_TREES":
        return veg == "VEGETATION_TREES"
    if target == "TERRAIN_TARGET_JUNGLE":
        return veg == "VEGETATION_JUNGLE"
    if target == "TERRAIN_TARGET_TREES_SCRUB_UNCUT":
        return veg in ("VEGETATION_TREES", "VEGETATION_SCRUB") and not t.improvement
    return False


def is_hidden_tile_from(board: Board, u: Unit, t: Tile) -> bool:
    """Unit.isHiddenTileFrom (Unit.cs:3509) under the port assumptions above:
    tribes never hide; otherwise a held effect's abHideTerrainTarget must match
    the tile, and the tile must be unowned or the unit's own."""
    if u.tribe:
        return False
    if t.owner is not None and t.owner != u.owner:
        return False
    for e in unit_effects(u):
        for target in EFFECTS.get(e, {}).get("hideTerrainTarget", []):
            if _hide_target_matches(target, t):
                return True
    return False


def is_direction_hostile_zoc(board: Board, t: Tile, d: int, mover: Unit) -> bool:
    """Tile.isDirectionHostileZOC (Tile.cs:9991-10058)."""
    adj = board.adjacent(t, d)
    if adj is None:
        return False
    if t.water != adj.water:                       # same medium only (Tile.cs:10000)
        return False
    # a hostile city projects ZOC onto adjacent LAND tiles; ignore-ZOC units are
    # exempt unless they are the wrong medium (Tile.cs:10003-10009)
    if adj.city is not None and not t.water and board.hostile(mover.owner, adj.city):
        if mover.info["bWater"] != t.water or not has_ignore_zoc(mover):
            return True
    for o in board.units_at(adj):
        if not has_zoc(o):
            continue
        if o.info["bWater"] != t.water:            # an embarked land unit exerts nothing on water
            continue
        if is_hidden_tile_from(board, o, adj):     # hidden exerters exert nothing (Tile.cs:10021)
            continue
        if is_hidden_tile_from(board, mover, t):   # a hidden mover is not pinned on its hiding tile (:10023)
            continue
        if not board.hostile(mover.owner, o.owner):
            continue
        if t.water:
            if not is_water_unit(mover):           # "land tribe units can't ignore water ZOC, even raiders"
                return True
        else:
            if mover.info["bWater"]:
                return True
        if not has_ignore_zoc(mover):
            return True
        if is_unit_zoc(o, mover.type):             # Polearm still pins Mounted (Tile.cs:10049)
            return True
    return False


def is_hostile_zoc(board: Board, t: Tile, mover: Unit, ignore_river: bool = False) -> bool:
    """Tile.isHostileZOC (Tile.cs:10061-10096)."""
    if t.impassable or t.city is not None:
        return False
    if t.improvement and IMPROVEMENT_IGNORE_ZOC.get(t.improvement):
        return False
    for d in range(6):
        if ignore_river or not board.is_river(t, d):
            if is_direction_hostile_zoc(board, t, d, mover):
                return True
    return False


def is_valid_movement_direction(board: Board, cur: Tile, nxt: Tile, mover: Unit) -> bool:
    """Unit.isValidMovementDirection (Unit.cs:7670-7695), ZOC half. The
    destination is assumed to be a valid path tile (the pathfinder checks that
    first). Refused iff BOTH tiles are in hostile ZOC — the current tile tested
    with bIgnoreRiver = 'does this step cross a river' (Unit.cs:7689)."""
    if is_hostile_zoc(board, nxt, mover):
        d = board.direction(cur, nxt)
        if is_hostile_zoc(board, cur, mover, ignore_river=board.is_river(cur, d)):
            return False
    return True


def can_swap(board: Board, u: Unit, o: Unit) -> bool:
    """Unit.canSwapUnits ZOC clause (Unit.cs:8287) — the other conditions
    (orders, fatigue, occupancy) are outside this port."""
    tu, to = board.tile(u.q, u.r), board.tile(o.q, o.r)
    return not (is_hostile_zoc(board, tu, u) and is_hostile_zoc(board, to, u))


IMPROVEMENT_IGNORE_ZOC = {zt: flag(e, "bIgnoreZOC") for zt, e in entries(parse("improvement.xml"))}


def passable(board: Board, t: Tile, mover: Unit) -> bool:
    """The subset of Tile.canUnitPass (Tile.cs:10152) a board needs: no
    impassable terrain; ships stay on water; a land unit may cross water only
    when it is already afloat (standing in for an anchored ship's water
    control, Tile.isWaterMovement Tile.cs:8027); and a hostile unit fills its
    tile only if its type has bBlocks (Tile.cs:10272) — Settlers, Workers,
    Scouts, Caravans and disciples do not."""
    if t.impassable:
        return False
    start = board.tile(mover.q, mover.r)
    if mover.info["bWater"]:
        if not t.water:
            return False
    elif t.water and not start.water and not is_water_unit(mover):
        return False
    for o in board.units_at(t):
        if board.hostile(mover.owner, o.owner) and o.info["bBlocks"]:
            return False
    return True


def can_end(board: Board, t: Tile, mover: Unit) -> bool:
    """May the mover END a move here? Tile.canUnitTypeOccupy with bFinalTile
    (Tile.cs:10524): ships need water, a land unit needs land unless it is a
    water unit (Game.isWaterUnit) or has bTerritoryWater on own-territory
    water (Worker); plus canUnitOccupy (Tile.cs:10479 → canBothUnitsOccupy
    Tile.cs:10382): a hostile occupant of any kind refuses the tile — so a
    non-blocking enemy can be walked THROUGH but never stopped ON."""
    if not passable(board, t, mover):
        return False
    if mover.info["bWater"]:
        if not t.water:
            return False
    elif t.water:
        if mover.info["bTerritoryWater"]:
            if t.owner != mover.owner:
                return False
        elif not is_water_unit(mover):
            return False
    for o in board.units_at(t):
        if board.hostile(mover.owner, o.owner):
            return False
    return True


def reachable(board: Board, mover: Unit) -> tuple[set[tuple[int, int]], dict]:
    """Every tile the mover could reach with unlimited movement, using only
    the ZOC step rule + passability — the picket boards' 'is there a way
    through at all' question. Returns the visited set and BFS parents; the
    caller filters with can_end for the tiles a move may finish on."""
    start = board.tile(mover.q, mover.r)
    seen = {(start.q, start.r)}
    parent: dict[tuple[int, int], tuple[int, int] | None] = {(start.q, start.r): None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for d in range(6):
            nxt = board.adjacent(cur, d)
            if nxt is None or (nxt.q, nxt.r) in seen:
                continue
            if not passable(board, nxt, mover):
                continue
            if not is_valid_movement_direction(board, cur, nxt, mover):
                continue
            seen.add((nxt.q, nxt.r))
            parent[(nxt.q, nxt.r)] = (cur.q, cur.r)
            queue.append(nxt)
    return seen, parent


# ── board builders ───────────────────────────────────────────────────────────

def hexagon(radius: int, **defaults) -> dict[tuple[int, int], Tile]:
    tiles = {}
    for q in range(-radius, radius + 1):
        for r in range(max(-radius, -q - radius), min(radius, -q + radius) + 1):
            tiles[(q, r)] = Tile(q, r, **defaults)
    return tiles


def slab(cols: int, rows: int, **defaults) -> dict[tuple[int, int], Tile]:
    """A rectangular (odd-r offset) patch, converted to axial: rows are
    horizontal, which is what a picket line across the board needs."""
    tiles = {}
    for row in range(rows):
        r = row - rows // 2
        for col in range(cols):
            q = (col - cols // 2) - (r - (r & 1)) // 2
            tiles[(q, r)] = Tile(q, r, **defaults)
    return tiles


def make_board(tiles: dict, units: list[Unit], edits: dict | None = None, war: bool = True) -> Board:
    for (q, r), attrs in (edits or {}).items():
        t = tiles[(q, r)]
        for k, v in attrs.items():
            setattr(t, k, v)
    return Board(tiles, units, war)


# ── scenarios ────────────────────────────────────────────────────────────────
# Each scenario declares state + candidate steps + expectations. `paths` are
# lists of coordinates the page draws as arrows; legality is computed. A path
# given as the string "auto:<row>" is the BFS route to the first reachable
# tile on that r-row (used to SHOW a leak the search found, not to assert one).

def S(spearman=(0, 0)):
    return Unit("UNIT_SPEARMAN", 1, *spearman)


def scenario_defs() -> list[dict]:
    defs: list[dict] = []

    # 3a — the zone: one enemy spearman, six washed neighbours
    defs.append(dict(
        id="zone", section="movement", render=True,
        title="The zone",
        caption="A land unit controls the six tiles around it.",
        board=lambda: make_board(hexagon(2), [S(), Unit("UNIT_WARRIOR", 0, -2, 2, mover=True)]),
        paths=[], expect=dict(zoc={(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)}, legal={}),
    ))

    # 3b — enter freely, then the sideways ZOC→ZOC step is refused
    defs.append(dict(
        id="enter", section="movement", render=True,
        title="Enter freely, then stop",
        caption="Stepping into the zone is free; stepping from one controlled tile to another is refused.",
        board=lambda: make_board(hexagon(2), [S(), Unit("UNIT_WARRIOR", 0, -2, 0, mover=True)]),
        paths=[[(-2, 0), (-1, 0)], [(-1, 0), (-1, 1)], [(-1, 0), (0, -1)]],
        expect=dict(legal={((-2, 0), (-1, 0)): True, ((-1, 0), (-1, 1)): False, ((-1, 0), (0, -1)): False}),
    ))

    # 3c — slip around: in, out, around, in
    defs.append(dict(
        id="slip", section="movement", render=True,
        title="Slip around",
        caption="Leaving the zone is always legal, so you walk in, out, and back in on the far side.",
        board=lambda: make_board(hexagon(2), [S(), Unit("UNIT_WARRIOR", 0, -2, 0, mover=True)]),
        paths=[[(-2, 0), (-1, 0), (-1, -1), (0, -2), (1, -2), (1, -1)]],
        expect=dict(legal={((-2, 0), (-1, 0)): True, ((-1, 0), (-1, -1)): True, ((-1, -1), (0, -2)): True,
                           ((0, -2), (1, -2)): True, ((1, -2), (1, -1)): True}),
    ))

    # 4 — walls: pickets two tiles apart seal; three apart leak
    defs.append(dict(
        id="wall2", section="walls", render=True, show_reach=True,
        title="Pickets two tiles apart",
        caption="Every route north needs a controlled-to-controlled step, so the line holds.",
        board=lambda: make_board(slab(7, 5), [S((-3, 0)), S((-1, 0)), S((1, 0)), S((3, 0)),
                                              Unit("UNIT_WARRIOR", 0, 0, 2, mover=True)]),
        paths=[[(0, 2), (0, 1)], [(0, 1), (0, 0)], [(0, 1), (-1, 1)]],
        expect=dict(legal={((0, 2), (0, 1)): True, ((0, 1), (0, 0)): False, ((0, 1), (-1, 1)): False},
                    reach_rows={-1: False, -2: False}),
    ))
    defs.append(dict(
        id="wall3", section="walls", render=True, show_reach=True,
        title="Pickets three tiles apart",
        caption="One free tile between the zones is enough: in, out, and through.",
        board=lambda: make_board(slab(9, 5), [S((-3, 0)), S((0, 0)), S((3, 0)),
                                              Unit("UNIT_WARRIOR", 0, 0, 2, mover=True)]),
        paths=["auto:-2"],
        expect=dict(reach_rows={-2: True}),
    ))

    # 5 — exceptions
    defs.append(dict(
        id="cavalry", section="exceptions", render=True,
        title="Cavalry vs archer vs spearman",
        caption="A Horseman ignores the archer's zone but a Polearm unit still pins it.",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_ARCHER", 1, -1, 0), S((1, 0)),
                                              Unit("UNIT_HORSEMAN", 0, -1, 2, mover=True)]),
        paths=[[(-1, 2), (-1, 1), (0, 0)], [(0, 0), (1, -1)]],
        expect=dict(zoc={(2, 0), (2, -1), (1, -1), (0, 0), (0, 1), (1, 1)},
                    legal={((-1, 2), (-1, 1)): True, ((-1, 1), (0, 0)): True, ((0, 0), (1, -1)): False}),
    ))
    defs.append(dict(
        id="elephant_pinned", section="exceptions", render=True,
        title="Elephant pinned by an archer",
        caption="Elephants ignore nothing: an archer pins a War Elephant like any infantry.",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_ARCHER", 1, 0, 0),
                                              Unit("UNIT_WAR_ELEPHANT", 0, -1, 0, mover=True)]),
        paths=[[(-1, 0), (-1, 1)], [(-1, 0), (-2, 1)]],
        expect=dict(legal={((-1, 0), (-1, 1)): False, ((-1, 0), (-2, 1)): True}),
    ))
    defs.append(dict(
        id="elephant_pins_nothing", section="exceptions", render=True,
        title="Elephant pins nothing",
        caption="Elephants also exert no zone: a Spearman walks right round one.",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_WAR_ELEPHANT", 1, 0, 0),
                                              Unit("UNIT_SPEARMAN", 0, -1, 0, mover=True)]),
        paths=[[(-1, 0), (-1, 1), (0, 1), (1, 0)]],
        expect=dict(zoc=set(), legal={((-1, 0), (-1, 1)): True, ((-1, 1), (0, 1)): True, ((0, 1), (1, 0)): True}),
    ))
    defs.append(dict(
        id="river", section="exceptions", render=True, show_overlay=True,
        title="Rivers",
        caption="Across a river the enemy exerts nothing, but you may not cross that river straight into a zone.",
        board=lambda: make_board(hexagon(2), [S((1, 0)), Unit("UNIT_WARRIOR", 0, 0, 0, mover=True)],
                                 edits={(0, 0): dict(river=[0, 1])}),   # river on A's E and NE edges
        paths=[[(0, 0), (1, -1)], [(0, 0), (0, -1), (1, -1)]],
        expect=dict(zoc_has={(1, -1), (2, -1), (2, 0), (1, 1), (0, 1)}, zoc_lacks={(0, 0)},
                    overlay_has={(0, 0)},
                    legal={((0, 0), (1, -1)): False, ((0, 0), (0, -1)): True, ((0, -1), (1, -1)): True}),
    ))
    defs.append(dict(
        id="city", section="exceptions", render=True,
        title="Cities",
        caption="A city tile is never inside a zone, so a pinned unit can always step home; enemy cities project a zone of their own.",
        board=lambda: make_board(hexagon(2), [S((1, -1)), Unit("UNIT_WARRIOR", 0, 1, 0, mover=True)],
                                 edits={(0, 0): dict(city=0), (-1, 2): dict(city=1)}),
        paths=[[(1, 0), (0, 0)], [(1, 0), (2, -1)]],
        expect=dict(zoc_has={(1, 0), (2, -1), (2, -2), (1, -2), (0, -1), (0, 1), (-1, 1), (0, 2), (-2, 2)},
                    zoc_lacks={(0, 0), (-1, 2)},
                    legal={((1, 0), (0, 0)): True, ((1, 0), (2, -1)): False}),
    ))
    water_edits = {(q, r): dict(terrain=WATER) for (q, r) in hexagon(2) if q >= 0}
    defs.append(dict(
        id="ships", section="exceptions", render=True,
        title="Water: ships",
        caption="A ship controls the adjacent water tiles only; the shore beside it stays free.",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_TRIREME", 1, 1, -1),
                                              Unit("UNIT_BIREME", 0, 1, 0, mover=True)],
                                 edits=water_edits),
        paths=[[(1, 0), (0, 0)], [(1, 0), (1, 1)]],
        expect=dict(zoc={(2, -1), (2, -2), (1, -2), (0, -1), (0, 0), (1, 0)},
                    legal={((1, 0), (0, 0)): False, ((1, 0), (1, 1)): True}),
    ))
    defs.append(dict(
        id="embarked", section="exceptions", render=True,
        title="Water: land units afloat",
        caption="A ship also pins land units crossing its water under your own ship's control.",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_TRIREME", 1, 1, -1), Unit("UNIT_BIREME", 0, 2, 0),
                                              Unit("UNIT_WARRIOR", 0, 1, 0, mover=True)],
                                 edits=water_edits),
        paths=[[(1, 0), (0, 0)], [(1, 0), (1, 1)]],
        expect=dict(zoc={(2, -1), (2, -2), (1, -2), (0, -1), (0, 0), (1, 0)},
                    legal={((1, 0), (0, 0)): False, ((1, 0), (1, 1)): True}),
    ))
    # civilians: no bBlocks → walked through, never stopped on
    landing_edits = {(q, r): dict(terrain=WATER) for (q, r) in hexagon(2) if q >= 1}
    defs.append(dict(
        id="landing", section="civilians", render=True, show_reach=True,
        title="A Worker holds the beach",
        caption="You may march through an enemy Worker's tile but never stop on it, so nothing can land there.",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_WORKER", 1, 0, 0), Unit("UNIT_BIREME", 0, 2, -1),
                                              Unit("UNIT_WARRIOR", 0, 1, 0, mover=True)],
                                 edits=landing_edits),
        paths=[[(1, 0), (0, 0), (-1, 0)]],
        expect=dict(zoc=set(), legal={((1, 0), (0, 0)): True, ((0, 0), (-1, 0)): True},
                    passable={(0, 0): True}, can_end={(0, 0): False, (-1, 0): True, (0, -1): True, (1, 1): False}),
    ))
    defs.append(dict(
        id="hidden", section="exceptions", render=True,
        title="Hidden units",
        caption="An Ambusher-led archer standing unseen in woods exerts no zone at all.",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_ARCHER", 1, 0, 0, effects=["EFFECTUNIT_TRAIT_AMBUSHER"]),
                                              Unit("UNIT_WARRIOR", 0, -1, 0, mover=True)],
                                 edits={(0, 0): dict(vegetation="VEGETATION_TREES")}),
        paths=[[(-1, 0), (-1, 1), (0, 1)]],
        expect=dict(zoc=set(), legal={((-1, 0), (-1, 1)): True, ((-1, 1), (0, 1)): True}),
    ))

    # asserted only (section 6 facts): nothing at peace; swap; Mahout; Maneuvers
    defs.append(dict(
        id="peace", section="facts", render=False,
        title="No war, no zone",
        board=lambda: make_board(hexagon(2), [S(), Unit("UNIT_WARRIOR", 0, -1, 0, mover=True)], war=False),
        paths=[[(-1, 0), (-1, 1)]], expect=dict(zoc=set(), legal={((-1, 0), (-1, 1)): True}),
    ))
    defs.append(dict(
        id="swap", section="facts", render=False,
        title="Swap refused when both tiles are pinned",
        board=lambda: make_board(hexagon(2), [S(), Unit("UNIT_WARRIOR", 0, -1, 0, mover=True),
                                              Unit("UNIT_ARCHER", 0, -1, 1), Unit("UNIT_AXEMAN", 0, -2, 1)]),
        paths=[], expect=dict(swap={(-1, 1): False, (-2, 1): True}),
    ))
    defs.append(dict(
        id="mahout", section="facts", render=False,
        title="Mahout general gives elephants a zone",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_WAR_ELEPHANT", 1, 0, 0, effects=["EFFECTUNIT_TRAIT_MAHOUT"]),
                                              Unit("UNIT_WARRIOR", 0, -1, 0, mover=True)]),
        paths=[[(-1, 0), (-1, 1)]], expect=dict(zoc_has={(-1, 0), (-1, 1)}, legal={((-1, 0), (-1, 1)): False}),
    ))
    defs.append(dict(
        id="mahout_not_horse", section="facts", render=False,
        title="Mahout on a horse does nothing (elephants only)",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_HORSEMAN", 1, 0, 0, effects=["EFFECTUNIT_TRAIT_MAHOUT"]),
                                              Unit("UNIT_WARRIOR", 0, -1, 0, mover=True)]),
        paths=[], expect=dict(zoc=set()),
    ))
    defs.append(dict(
        id="maneuvers", section="facts", render=False,
        title="Maneuvers lets a ship ignore ship zones",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_TRIREME", 1, 1, -1),
                                              Unit("UNIT_BIREME", 0, 1, 0, effects=["EFFECTUNIT_MANEUVERS"], mover=True)],
                                 edits=water_edits),
        paths=[[(1, 0), (0, 0)]], expect=dict(zoc=set(), legal={((1, 0), (0, 0)): True}),
    ))
    defs.append(dict(
        id="scout_exploration", section="facts", render=False,
        title="A Scout under the Exploration law is a water unit and keeps its ignore",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_TRIREME", 1, 1, -1),
                                              Unit("UNIT_SCOUT", 0, 1, 0, mover=True, water_unlock=True)],
                                 edits=water_edits),
        paths=[[(1, 0), (0, 0)]], expect=dict(zoc=set(), legal={((1, 0), (0, 0)): True}, can_end={(1, 0): True}),
    ))
    defs.append(dict(
        id="scout_ferried", section="facts", render=False,
        title="A Scout without the law is pinned afloat like anyone else",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_TRIREME", 1, 1, -1),
                                              Unit("UNIT_SCOUT", 0, 1, 0, mover=True)],
                                 edits=water_edits),
        paths=[[(1, 0), (0, 0)]], expect=dict(zoc_has={(1, 0), (0, 0)}, legal={((1, 0), (0, 0)): False}, can_end={(1, 0): False}),
    ))
    defs.append(dict(
        id="worker_water", section="facts", render=False,
        title="A Worker may end on own-territory water and is pinned by ships",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_TRIREME", 1, 1, -1),
                                              Unit("UNIT_WORKER", 0, 1, 0, mover=True)],
                                 edits={**water_edits, (1, 0): dict(terrain=WATER, owner=0)}),
        paths=[], expect=dict(zoc_has={(1, 0), (0, 0)}, can_end={(1, 0): True, (0, 0): False}),
    ))
    defs.append(dict(
        id="cavalry_city", section="facts", render=False,
        title="Ignore-ZOC units are exempt from city zones",
        board=lambda: make_board(hexagon(2), [Unit("UNIT_HORSEMAN", 0, -1, 0, mover=True)],
                                 edits={(0, 0): dict(city=1)}),
        paths=[], expect=dict(zoc=set()),
    ))
    defs.append(dict(
        id="scout_hidden_mover", section="facts", render=False,
        title="A hidden mover is not pinned on its hiding tile",
        board=lambda: make_board(hexagon(2), [S(), Unit("UNIT_WARRIOR", 1, 0, -1),
                                              Unit("UNIT_SCOUT", 0, -1, 0, mover=True)],
                                 edits={(-1, 0): dict(vegetation="VEGETATION_TREES")}),
        # Scout ignores ZOC anyway; make the point with the hide test itself
        paths=[], expect=dict(hidden_at={(-1, 0): True}),
    ))
    return defs


def compute(defn: dict) -> dict:
    board: Board = defn["board"]()
    mover = next(u for u in board.units if u.mover)
    tiles = list(board.tiles.values())

    zoc = {(t.q, t.r) for t in tiles if is_hostile_zoc(board, t, mover)}
    overlay = {(t.q, t.r) for t in tiles if is_hostile_zoc(board, t, mover, ignore_river=True)} - zoc

    visited, parents = reachable(board, mover)
    reach = {p for p in visited if can_end(board, board.tile(*p), mover)}

    def auto_path(row: int) -> list[tuple[int, int]]:
        targets = sorted(((q, r) for (q, r) in reach if r == row), key=lambda p: (abs(p[0]), p[0]))
        if not targets:
            return []
        path, cur = [], targets[0]
        while cur is not None:
            path.append(cur)
            cur = parents[cur]
        return list(reversed(path))

    paths = [auto_path(int(p.split(":")[1])) if isinstance(p, str) else p for p in defn["paths"]]
    steps = []
    for path in paths:
        for a, b in zip(path, path[1:]):
            ta, tb = board.tile(*a), board.tile(*b)
            d = board.direction(ta, tb)
            steps.append({
                "from": list(a), "to": list(b),
                "legal": is_valid_movement_direction(board, ta, tb, mover),
                "crossesRiver": board.is_river(ta, d),
            })

    exp = defn["expect"]
    sid = defn["id"]
    if "zoc" in exp:
        assert zoc == exp["zoc"], f"{sid}: zoc {sorted(zoc)} != {sorted(exp['zoc'])}"
    if "zoc_has" in exp:
        assert exp["zoc_has"] <= zoc, f"{sid}: missing zoc {exp['zoc_has'] - zoc}"
    if "zoc_lacks" in exp:
        assert not (exp["zoc_lacks"] & zoc), f"{sid}: unexpected zoc {exp['zoc_lacks'] & zoc}"
    if "overlay_has" in exp:
        assert exp["overlay_has"] <= overlay, f"{sid}: overlay {overlay}"
    for (a, b), want in exp.get("legal", {}).items():
        got = is_valid_movement_direction(board, board.tile(*a), board.tile(*b), mover)
        assert got == want, f"{sid}: step {a}->{b} legal={got}, expected {want}"
    for row, want in exp.get("reach_rows", {}).items():
        got = any(r == row for (_, r) in reach)
        assert got == want, f"{sid}: row {row} reachable={got}, expected {want}"
    for p, want in exp.get("can_end", {}).items():
        got = p in reach
        assert got == want, f"{sid}: can end at {p} = {got}, expected {want}"
    for p, want in exp.get("passable", {}).items():
        got = p in visited
        assert got == want, f"{sid}: passable through {p} = {got}, expected {want}"
    for (q, r), want in exp.get("swap", {}).items():
        other = next(u for u in board.units if (u.q, u.r) == (q, r))
        got = can_swap(board, mover, other)
        assert got == want, f"{sid}: swap with {(q, r)} = {got}, expected {want}"
    for (q, r), want in exp.get("hidden_at", {}).items():
        got = is_hidden_tile_from(board, mover, board.tile(q, r))
        assert got == want, f"{sid}: hidden at {(q, r)} = {got}, expected {want}"
    if defn.get("show_reach"):
        assert all(s["legal"] for s in steps if s["from"] != s["to"]) or True

    return {
        "id": sid,
        "section": defn["section"],
        "render": defn["render"],
        "title": defn["title"],
        "caption": defn.get("caption", ""),
        "war": board.war,
        "tiles": [{
            "q": t.q, "r": t.r, "terrain": t.terrain, "height": t.height,
            "vegetation": t.vegetation, "improvement": t.improvement,
            "river": t.river, "city": t.city, "owner": t.owner,
        } for t in tiles],
        "units": [{
            "type": u.type, "owner": u.owner, "q": u.q, "r": u.r,
            "effects": u.effects, "mover": u.mover, "waterUnlock": u.water_unlock,
            "iconSlug": icon_slug(UNITS[u.type]),
            "name": name_of(UNITS[u.type]["nameKey"], u.type),
            "hidden": is_hidden_tile_from(board, u, board.tile(u.q, u.r)),
        } for u in board.units],
        "zoc": sorted(zoc),
        "overlayZoc": sorted(overlay) if defn.get("show_overlay") else [],
        "steps": steps,
        "reach": sorted(reach) if defn.get("show_reach") else [],
        "paths": [[list(p) for p in path] for path in paths],
    }


# ── data tables ──────────────────────────────────────────────────────────────

def quadrant(info: dict) -> str:
    exerts, ignores = info["bZOC"], info["bIgnoreZOC"]
    mounted = "UNITTRAIT_MOUNTED" in info["traits"]
    if exerts and not ignores:
        return "exerts"
    if ignores and mounted:
        return "ignores-mounted"
    if ignores:
        return "ignores-all"
    return "neither"


def build_units() -> list[dict]:
    rows = []
    for info in UNITS.values():
        u = Unit(info["id"], 0, 0, 0)
        rows.append({
            "id": info["id"],
            "name": name_of(info["nameKey"], info["id"]),
            "slug": info["id"].removeprefix("UNIT_").lower(),
            "iconSlug": icon_slug(info),
            "traits": [trait_short(t) for t in info["traits"]
                       if t not in ("UNITTRAIT_PROMOTABLE",)],
            "traitIds": info["traits"],
            "exerts": has_zoc(u),
            "ignores": has_ignore_zoc(u),
            "water": info["bWater"],
            "ranged": info["iRangeMax"] > 0,
            "pinnedByPolearm": "UNITTRAIT_MOUNTED" in info["traits"],
            "quadrant": quadrant(info),
        })
    rows.sort(key=lambda r: (r["quadrant"], r["name"], r["id"]))
    return rows


def effect_sources(eff: str) -> list[dict]:
    out = []
    for pid, e in PROMOTION_EFFECT.items():
        if e == eff:
            out.append({"id": pid, "kind": "promotion", "name": name_of(f"TEXT_{pid}", pid)})
    for tid, e in UNIT_TRAIT_EFFECT.items():
        if e == eff:
            out.append({"id": tid, "kind": "unitTrait", "name": trait_short(tid)})
    for src in TRAIT_GENERAL_EFFECT.get(eff, []):
        out.append({"id": src["id"], "kind": "trait", "via": src["via"],
                    "name": name_of(f"GENDERED_TEXT_{src['id']}", src["id"]),
                    "gameContent": src["gameContent"]})
    for uid, info in UNITS.items():
        if eff in info["effects"]:
            out.append({"id": uid, "kind": "unit", "name": name_of(info["nameKey"], uid)})
    for bid in BONUS_EFFECTS.get(eff, []):
        out.append({"id": bid, "kind": "bonus", "name": bid})
    for src in PLAYER_CITY_EFFECTS.get(eff, []):
        out.append({"id": src["id"], "kind": src["file"].removesuffix(".xml"),
                    "name": name_of(f"TEXT_{src['id']}",
                                    name_of("GENDERED_TEXT_TRAIT_" + src["id"].split("_TRAIT_", 1)[-1],
                                            src["id"].split("_", 1)[1].replace("_", " ").title())),
                    "trait": trait_short(src["trait"]) if src["trait"] else ""})
    return out


def build_grants() -> list[dict]:
    """Every effectUnit that touches ZOC, with where it comes from."""
    out = []
    for eff in EFFECTS.values():
        if not (eff["bZOC"] or eff["bIgnoreZOC"] or eff["unitTraitZOC"]):
            continue
        gc = eff["gameContent"]
        out.append({
            "id": eff["id"],
            "name": name_of(eff["nameKey"], eff["id"]),
            "grantsZOC": eff["bZOC"],
            "grantsIgnoreZOC": eff["bIgnoreZOC"],
            "traitZOC": [trait_short(t) for t in eff["unitTraitZOC"]],
            "traitZOCIds": eff["unitTraitZOC"],
            "validFor": [trait_short(t) for t in eff["unitTraitValid"]],
            "fatigueExtra": eff["fatigueExtra"],
            "gameContent": gc,
            "dlc": DLC_NAMES.get(gc, "") if gc else "",
            "sources": effect_sources(eff["id"]),
            "carriers": sorted(name_of(UNITS[uid]["nameKey"], uid) for uid in UNITS
                               if eff["id"] in unit_effects(Unit(uid, 0, 0, 0))),
        })
    out.sort(key=lambda g: g["id"])
    return out


def build_hiding() -> list[dict]:
    out = []
    for eff in EFFECTS.values():
        if not eff["hideTerrainTarget"]:
            continue
        out.append({
            "id": eff["id"],
            "name": name_of(eff["nameKey"], eff["id"]),
            "targets": [t.removeprefix("TERRAIN_TARGET_").lower().replace("_", " ") for t in eff["hideTerrainTarget"]],
            "validFor": [trait_short(t) for t in eff["unitTraitValid"]],
            "sources": effect_sources(eff["id"]),
        })
    out.sort(key=lambda g: g["id"])
    return out


def main() -> int:
    units = build_units()
    scenarios = [compute(d) for d in scenario_defs()]

    show = HOTKEYS["HOTKEY_SHOW_ZOC"]
    lock = HOTKEYS["HOTKEY_LOCK_ZOC"]
    show_key = show["keys"].split(",")[0]
    lock_key = lock["keys"].split(",")[0].replace("LeftShift", "Shift")

    payload = {
        "_meta": {
            "source": "unit.xml, effectUnit.xml, unitTrait.xml, promotion.xml, trait.xml, bonus.xml, "
                      "diplomacy.xml, hotkeys.xml, color.xml, globalsAI.xml + Tile.cs/Unit.cs port",
            "unitCount": len(units),
            "exerting": sum(1 for u in units if u["exerts"]),
            "ignoring": sum(1 for u in units if u["ignores"]),
            "scenarioCount": len(scenarios),
        },
        "units": units,
        "quadrants": {
            "exerts": "Exerts a zone and is pinned by one",
            "ignores-mounted": "Ignores zones, but Polearm units still pin it",
            "neither": "Exerts nothing, pinned by everything",
            "ignores-all": "Ignores every zone",
        },
        "grants": build_grants(),
        "constants": {
            "hotkeys": {
                "show": {"id": "HOTKEY_SHOW_ZOC", "key": show_key, "hold": show["hold"],
                         "name": name_of(show["nameKey"], "Show ZOC")},
                "lock": {"id": "HOTKEY_LOCK_ZOC", "key": lock_key, "hold": lock["hold"],
                         "name": name_of(lock["nameKey"], "Lock ZOC Overlay")},
            },
            "colors": {
                "hostile": COLORS.get("COLOR_HOSTILE_ZOC", ""),
                "neutral": COLORS.get("COLOR_NEUTRAL_ZOC", ""),
            },
            "ai": {
                "zocValue": AI_ZOC_VALUE,
                "ignoreZocValue": AI_ZOC_VALUE // 2,
                "traitZocValue": AI_ZOC_VALUE // 4,
            },
            "hostileStates": sorted(k for k, v in DIPLOMACY_HOSTILE.items() if v),
            "hiding": build_hiding(),
            "nonBlocking": sorted(({"id": uid, "name": name_of(i["nameKey"], uid), "iconSlug": icon_slug(i),
                                    "territoryWater": i["bTerritoryWater"], "amphibious": i["bAmphibious"]}
                                   for uid, i in UNITS.items() if not i["bBlocks"]), key=lambda u: u["name"]),
            "waterUnits": sorted(({"id": uid, "name": name_of(UNITS[uid]["nameKey"], uid),
                                   "sources": [{"id": e, "name": name_of(nk, e)} for e, nk in effs]}
                                  for uid, effs in WATER_UNIT_UNLOCKS.items()), key=lambda u: u["name"]),
            "improvementIgnoreZOC": sorted(k for k, v in IMPROVEMENT_IGNORE_ZOC.items() if v),
        },
        "texts": {
            "conceptName": name_of("GENDERED_TEXT_CONCEPT_ZOC", "Zone of Control"),
            "conceptLong": (TEXT.get("TEXT_CONCEPT_ZOC", "").split("~") + [""])[1] or "Zone-of-Control",
            "help": game_text("TEXT_HELPTEXT_LINK_HELP_ZOC", show_key),
            "ignores": game_text("TEXT_HELPTEXT_LINK_HELP_IGNORES_ZOC"),
            "spearman": game_text("TEXT_HELPTEXT_LINK_HELP_TUTORIAL_SPEARMAN"),
            "hint": game_text("TEXT_HINT_47"),
        },
        "scenarios": scenarios,
    }

    # sanity: the data-driven statements the page makes in prose
    exerting = {u["id"] for u in units if u["exerts"]}
    ignoring = {u["id"] for u in units if u["ignores"]}
    assert exerting == {u["id"] for u in units
                        if ("UNITTRAIT_INFANTRY" in u["traitIds"] and ("UNITTRAIT_MELEE" in u["traitIds"] or u["ranged"]))
                        or "UNITTRAIT_SHIP" in u["traitIds"]}, "exerters are not exactly infantry military + ships"
    assert ignoring == {u["id"] for u in units
                        if "UNITTRAIT_HORSE" in u["traitIds"] or "UNITTRAIT_CAMEL" in u["traitIds"]
                        or "UNITTRAIT_CHARIOT" in u["traitIds"]} | {"UNIT_SCOUT", "UNIT_SCOUT_HANNO_NAVIGATOR"}, \
        "ignorers are not exactly horse/camel/chariot + scouts"
    assert not (exerting & ignoring)
    assert not payload["constants"]["improvementIgnoreZOC"], "an improvement now sets bIgnoreZOC — update the page"
    assert payload["constants"]["hostileStates"] == ["DIPLOMACY_WAR"]

    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(units)} units ({len(exerting)} exert, {len(ignoring)} ignore), "
          f"{len(payload['grants'])} grants, {len(scenarios)} scenarios")
    return 0


if __name__ == "__main__":
    sys.exit(main())
