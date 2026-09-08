#!/usr/bin/env python3
"""
Build src/data/borders.json — everything the Border Expansion explainer needs.

Sources (reference/XML/Infos):
  terrain / height / vegetation / resource.xml   iBorderValue, iLandValueAdjacent, bImpassable, bUrban
  improvement.xml     bUrban / bSpreadsBorders / bRemoveBorder / bTerritoryOnly / bTribe /
                      aeAdjacentImprovementSpecialists / GameContentRequired
  yield.xml           iBuyTileBase / iBuyTilePer
  bonus*.xml          iBorderGrowth
  effectPlayer.xml    aeImprovementSpreadBorders / aeBuyTile
  effectCity.xml      aeBuyTile          effectUnit.xml  aeBuyTileYield
  trait.xml / law.xml / familyClass.xml / tech.xml   who grants those effects
  globalsInt / globalsType / color.xml / teamColor.xml   constants
  text-*.xml          names + the concept strings quoted verbatim

The second half is a PYTHON PORT of the game's territory code
(reference/Source/Base/Game/GameCore):
  Tile.isValidGrowth              Tile.cs:12576
  Tile.canGrowBorder              Tile.cs:12605
  Tile.isValidOwnerChangeTerritory Tile.cs:7302
  Tile.isNonAlliedTribeSite       Tile.cs:7289
  Tile.getOwnerChangeTiles        Tile.cs:7323   (resource / urban / flank / fill)
  Tile.doBorderFill (tile)        Tile.cs:11168
  Tile.getExpansionTiles          Tile.cs:12657  (BFS + checkMinorCity)
  Tile.checkMinorCity             Tile.cs:11089
  Tile.getCitySiteSurrounded      Tile.cs:4852 / getCitySiteAndSurroundingTiles 4912
  Tile.getAdjacentUnclaimedUrbanTiles Tile.cs:5030
  Tile.getConnectedCitySiteActive Tile.cs:12788
  Tile.spreadBorders              Tile.cs:7777   (range 1)
  Tile.getCityInitTiles           Tile.cs:12652  (range 2)
  Unit.buyTile / City.canBuyTile / getBuyTileCost   Unit.cs:12707, City.cs:9493, 9445
  City.findGrowBorderTile / growBorders  City.cs:9659, 9812
  Game.doBorderFill / doUrbanSurroundedRural / setTilesOwner  Game.cs:13155, 12895, 13177
  Tile.setOwner (bRemoveBorder)   Tile.cs:7470-7560
  Tile.setMinorCity               Tile.cs:11127

Every board on the page declares only terrain, ownership and a trigger; which
tiles are grabbed, in what order, by which rule, is COMPUTED here and asserted,
so a rules regression fails `make data` instead of drawing the wrong border.

Port assumptions (the scenarios never exercise the rest of the game state):
  * every tile is revealed to everyone (the engine runs with TeamType.NONE,
    for which Tile.isRevealed is always true and 'revealed' owners are the
    real ones);
  * team == player, no team alliances (Game.areTeamsAllied reduces to
    equality); tribe alliances are declared per board;
  * findGrowBorderTile's RandomStruct(cityTile.initSeed()) roll is replaced
    by an explicit per-scenario roll so the page can show the scoring;
  * the trade network is a per-tile flag (City.findGrowBorderTile's
    onTradeNetwork test);
  * city population and culture are equal (Tile.doBorderFill's last
    tie-break) — that branch is unreachable anyway, see do_border_fill_tile.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_concepts import Cleaner, load_dlc_names, load_full_text_index, load_globals_int  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "borders.json"
RES_ICON_DIR = ROOT / "public" / "img" / "icons" / "resources"


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


def ival(e: ET.Element, tag: str) -> int:
    # InfoBase defaults every int field to 0 (InfoBase.cs:3396, 5416, 6631, 7555)
    return int((e.findtext(tag) or "0").strip() or 0)


def zvalues(e: ET.Element, tag: str) -> list[str]:
    return [v.text.strip() for v in e.findall(f"{tag}/zValue") if v.text]


TERRAIN = {zt: {"border": ival(e, "iBorderValue"), "urban": flag(e, "bUrban"), "water": flag(e, "bWater"),
                "nameKey": e.findtext("Name") or ""} for zt, e in entries(parse("terrain.xml"))}
HEIGHT = {zt: {"border": ival(e, "iBorderValue"), "landAdj": ival(e, "iLandValueAdjacent"),
               "impassable": flag(e, "bImpassable"), "water": flag(e, "bWater"),
               "nameKey": e.findtext("Name") or ""} for zt, e in entries(parse("height.xml"))}
VEGETATION = {zt: {"border": ival(e, "iBorderValue"), "nameKey": e.findtext("Name") or ""}
              for zt, e in entries(parse("vegetation.xml"))}
RESOURCE = {zt: {"border": ival(e, "iBorderValue"), "icon": (e.findtext("zIconName") or zt).strip(),
                 "nameKey": e.findtext("Name") or ""} for zt, e in entries(parse("resource.xml"))}
IMPROVEMENT = {zt: {
    "urban": flag(e, "bUrban"), "spreads": flag(e, "bSpreadsBorders"), "removeBorder": flag(e, "bRemoveBorder"),
    "removeBonus": flag(e, "bRemoveBonus"), "territoryOnly": flag(e, "bTerritoryOnly"), "tribe": flag(e, "bTribe"),
    "wonder": flag(e, "bWonder"), "permanent": flag(e, "bPermanent"),
    "adjSpecialists": zvalues(e, "aeAdjacentImprovementSpecialists"),
    "gameContent": (e.findtext("GameContentRequired") or "").strip(),
    "nameKey": e.findtext("Name") or "", "class": (e.findtext("Class") or "").strip(),
} for zt, e in entries(parse("improvement.xml"))}
YIELD = {zt: {"buyBase": ival(e, "iBuyTileBase"), "buyPer": ival(e, "iBuyTilePer"), "nameKey": e.findtext("Name") or ""}
         for zt, e in entries(parse("yield.xml"))}
BONUS_GROWTH: dict[str, tuple[int, str]] = {}
for _f in sorted(XML_DIR.glob("bonus*.xml")):
    for zt, e in entries(ET.parse(_f).getroot()):
        v = ival(e, "iBorderGrowth")
        if e.findtext("iBorderGrowth") is not None and v != 0:
            BONUS_GROWTH[zt] = (v, _f.name)
# a tech card's BonusDiscover fans out to per-city bonuses through aeAllCityBonuses
BONUS_CHILDREN: dict[str, list[str]] = {zt: zvalues(e, "aeAllCityBonuses") + zvalues(e, "aeBonuses")
                                        for zt, e in entries(parse("bonus.xml"))}
EFFECT_PLAYER = {zt: {"spread": zvalues(e, "aeImprovementSpreadBorders"), "buy": zvalues(e, "aeBuyTile"),
                      "addUrban": flag(e, "bAddUrban"), "nameKey": e.findtext("Name") or ""}
                 for zt, e in entries(parse("effectPlayer.xml"))}
EFFECT_CITY = {zt: {"buy": zvalues(e, "aeBuyTile"), "nameKey": e.findtext("Name") or ""}
               for zt, e in entries(parse("effectCity.xml"))}
EFFECT_UNIT_BUY = {zt: zvalues(e, "aeBuyTileYield") for zt, e in entries(parse("effectUnit.xml"))
                   if zvalues(e, "aeBuyTileYield")}
TRAIT_EFFECTS: dict[str, list[dict]] = {}
for zt, e in entries(parse("trait.xml")):
    for tag in ("LeaderEffectPlayer", "GeneralEffectPlayer", "EffectPlayer"):
        eff = (e.findtext(tag) or "").strip()
        if eff:
            TRAIT_EFFECTS.setdefault(eff, []).append({"id": zt, "via": tag,
                                                      "gameContent": (e.findtext("GameContentRequired") or "").strip()})
LAW_EFFECTS = {(e.findtext("EffectPlayer") or "").strip(): zt for zt, e in entries(parse("law.xml"))
               if (e.findtext("EffectPlayer") or "").strip()}
FAMILY_SEAT_EFFECTS = {(e.findtext("SeatEffectCity") or "").strip(): zt for zt, e in entries(parse("familyClass.xml"))
                       if (e.findtext("SeatEffectCity") or "").strip()}
TECHS = {zt: {"nameKey": e.findtext("Name") or "", "bonusDiscover": (e.findtext("BonusDiscover") or "").strip(),
              "prereqs": [p.findtext("zIndex") for p in e.findall("abTechPrereq/Pair") if (p.findtext("bValue") or "") == "1"],
              "gameContent": (e.findtext("GameContentRequired") or "").strip()}
         for zt, e in entries(parse("tech.xml"))}
UNITS = {zt: {"build": flag(e, "bBuild"), "territoryWater": flag(e, "bTerritoryWater"), "found": flag(e, "bFound"),
              "nameKey": e.findtext("Name") or "", "icon": e.findtext("zIconName") or zt}
         for zt, e in entries(parse("unit.xml"))}
GLOBALS_INT = {zt: ival(e, "iValue") for zt, e in entries(parse("globalsInt.xml"))}
GLOBALS_TYPE = {zt: (e.findtext("zValue") or "").strip() for zt, e in entries(parse("globalsType.xml"))}
COLORS = {zt: (e.findtext("zHexValue") or "").strip() for zt, e in entries(parse("color.xml"))}
BORDER_PATTERNS = sorted({p for zt, e in entries(parse("teamColor.xml")) for p in zvalues(e, "aeBorderPatterns")})
EVENT_STORY_NAMES: dict[str, str] = {}
for _f in sorted(XML_DIR.glob("eventStory*.xml")):
    for zt, e in entries(ET.parse(_f).getroot()):
        EVENT_STORY_NAMES[zt] = e.findtext("Name") or ""

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

URBAN_TERRAIN = GLOBALS_TYPE["URBAN_TERRAIN"]
MINOR_CITY_IMPROVEMENT = GLOBALS_TYPE["MINOR_CITY_IMPROVEMENT"]
WATER_TERRAINS = {t for t, i in TERRAIN.items() if i["water"]}
IMPASSABLE_HEIGHTS = {h for h, i in HEIGHT.items() if i["impassable"]}
WATER_HEIGHTS = {h for h, i in HEIGHT.items() if i["water"]}


def name_of(key: str, fallback: str) -> str:
    key = GENDERED.get(key, key)
    raw = TEXT.get(key)
    if not raw:
        return fallback
    out = CLEANER.clean(raw).split("~")[0].strip()
    return re.sub(r"\{[A-Z][A-Z_0-9-]*(?:,\d+)?\}\s*", "", out).strip()


def game_text(key: str) -> str:
    return " ".join(CLEANER.paragraphs(TEXT.get(key, "")))


def nice(token: str, prefix: str) -> str:
    return token.removeprefix(prefix).replace("_", " ").title()


def resource_icon(res: str) -> str:
    slug = RESOURCE[res]["icon"].removeprefix("RESOURCE_").lower()
    if not (RES_ICON_DIR / f"{slug}.png").exists():
        alt = res.removeprefix("RESOURCE_").lower()
        if (RES_ICON_DIR / f"{alt}.png").exists():
            return alt
    return slug


# ── the port ─────────────────────────────────────────────────────────────────
# Pointy-top axial hexes in the GAME's direction order (Enums.cs:1849:
# NW, NE, E, SE, SW, W — clockwise), because Tile.doBorderFill iterates the
# first three directions against their opposites and that order decides which
# city receives a filled tile. wrapDirection(d, ±1) = the two flanking
# directions; directionOpposite = d+3 (Utils.cs:249-260).
DIRS = [(0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0)]
DIR_NAMES = ["NW", "NE", "E", "SE", "SW", "W"]
# HexBoard.astro draws river edges in owpuzzle's order (E, NE, NW, W, SW, SE).
GAME_TO_HEXBOARD_DIR = {0: 2, 1: 1, 2: 0, 3: 5, 4: 4, 5: 3}
NONE = -1
Key = tuple[int, int]


class CityTerritory(NamedTuple):
    """Structs.cs:2787. city_tile / city_site are tile keys; city_id -1 for a
    city that does not exist yet (founding), which Game.setTilesOwner then
    replaces with the new city's id."""
    player: int
    team: int
    tribe: int
    city_id: int
    city_tile: Key | None
    city_site: Key | None


class Grab(NamedTuple):
    key: Key
    ct: CityTerritory
    gen: int
    reason: str


@dataclass
class Tile:
    q: int
    r: int
    terrain: str = "TERRAIN_TEMPERATE"
    height: str = "HEIGHT_FLAT"
    vegetation: str | None = None
    resource: str | None = None
    improvement: str | None = None
    city_site: str | None = None       # 'ACTIVE' | 'USED' | None
    tribe: int = NONE                  # tribe holding a settlement improvement here
    specialist: bool = False
    boundary: bool = False
    trade: bool = False                # on the owning team's trade network
    river: list[int] = field(default_factory=list)   # HexBoard direction indices
    owner: int = NONE                  # player
    owner_tribe: int = NONE
    territory: int = NONE              # city id
    city: int = NONE                   # city id of a city ON this tile

    @property
    def key(self) -> Key:
        return (self.q, self.r)

    @property
    def water(self) -> bool:
        return self.terrain in WATER_TERRAINS or self.height in WATER_HEIGHTS

    @property
    def land(self) -> bool:
        return not self.water

    @property
    def impassable(self) -> bool:
        return self.height in IMPASSABLE_HEIGHTS

    @property
    def urban(self) -> bool:
        return TERRAIN[self.terrain]["urban"]

    @property
    def has_territory(self) -> bool:
        return self.territory != NONE

    def is_city_site_active(self) -> bool:
        return self.city_site == "ACTIVE"

    def is_city_site_any(self) -> bool:
        return self.city_site is not None


@dataclass
class City:
    id: int
    key: Key
    player: int
    buy_count: int = 0


@dataclass
class Board:
    tiles: dict[Key, Tile]
    cities: dict[int, City] = field(default_factory=dict)
    tribe_ally: dict[int, int] = field(default_factory=dict)   # tribe → allied player
    player_buy_count: dict[int, int] = field(default_factory=dict)
    next_city_id: int = 0
    log: list[str] = field(default_factory=list)

    def tile(self, q: int, r: int) -> Tile | None:
        return self.tiles.get((q, r))

    def at(self, k: Key) -> Tile:
        return self.tiles[k]

    def adjacent(self, t: Tile, d: int) -> Tile | None:
        dq, dr = DIRS[d]
        return self.tile(t.q + dq, t.r + dr)

    def neighbours(self, t: Tile):
        for d in range(6):
            n = self.adjacent(t, d)
            if n is not None:
                yield d, n

    @staticmethod
    def distance(a: Key, b: Key) -> int:
        dq, dr = a[0] - b[0], a[1] - b[1]
        return max(abs(dq), abs(dr), abs(dq + dr))

    def tiles_at_distance(self, t: Tile, dist: int) -> list[Tile]:
        # Tile.getTilesAtDistance: ring order does not matter for membership;
        # tile-id order (row-major) keeps generation numbering stable
        return sorted((o for o in self.tiles.values() if self.distance(t.key, o.key) == dist), key=lambda o: (o.r, o.q))

    def city_of(self, cid: int) -> City:
        return self.cities[cid]

    def territory_ct(self, t: Tile) -> CityTerritory:
        """new CityTerritory(City) — Structs.cs:2807: site id = the city tile."""
        c = self.city_of(t.territory)
        return CityTerritory(c.player, c.player, NONE, c.id, c.key, c.key)

    # Game.areAllied (Game.cs) with team == player and no team alliances
    def allied(self, team1: int, tribe1: int, team2: int, tribe2: int) -> bool:
        if team2 != NONE:
            if team1 != NONE:
                return team1 == team2
            if tribe1 != NONE:
                return self.tribe_ally.get(tribe1, NONE) == team2
        elif tribe2 != NONE:
            if tribe1 == tribe2:
                return True
            if team1 != NONE:
                return self.tribe_ally.get(tribe2, NONE) == team1
        return False


class Engine:
    """The territory code, one method per game function."""

    def __init__(self, board: Board):
        self.b = board
        self._surrounded: set[Key] | None = None

    # ── predicates ───────────────────────────────────────────────────────
    def is_valid_growth(self, t: Tile) -> bool:
        """Tile.isValidGrowth (Tile.cs:12576): terrain, height, vegetation and
        resource all have iBorderValue >= 0."""
        if TERRAIN[t.terrain]["border"] < 0:
            return False
        if HEIGHT[t.height]["border"] < 0:
            return False
        if t.vegetation and VEGETATION[t.vegetation]["border"] < 0:
            return False
        if t.resource and RESOURCE[t.resource]["border"] < 0:
            return False
        return True

    def is_non_allied_tribe_site(self, t: Tile, player: int) -> bool:
        """Tile.isNonAlliedTribeSite (Tile.cs:7289): a bTribe improvement whose
        tribe is not allied to the expanding player."""
        if not (t.improvement and IMPROVEMENT[t.improvement]["tribe"]) or t.tribe == NONE:
            return False
        return self.b.tribe_ally.get(t.tribe, NONE) != player

    def connected_city_site_active(self, t: Tile) -> Key | None:
        """Tile.getConnectedCitySiteActive (Tile.cs:12788): flood over urban
        tiles from an urban tile; the first ACTIVE city site found."""
        if not t.urban:
            return None
        seen = {t.key}
        queue = deque([t])
        while queue:
            cur = queue.popleft()
            if cur.is_city_site_active():
                return cur.key
            for _, n in self.b.neighbours(cur):
                if n.key not in seen:
                    seen.add(n.key)
                    if n.urban:
                        queue.append(n)
        return None

    def is_valid_owner_change_territory(self, t: Tile, ct: CityTerritory, pending: dict[Key, CityTerritory]) -> bool:
        """Tile.isValidOwnerChangeTerritory (Tile.cs:7302)."""
        site = self.connected_city_site_active(t)
        if site is not None and site != ct.city_site:
            return False
        if t.key in pending:
            return False
        if t.has_territory:
            return False
        return True

    def adjacent_unclaimed_urban(self, t: Tile, out: set[Key]) -> None:
        """Tile.getAdjacentUnclaimedUrbanTiles (Tile.cs:5030): the tile plus
        every connected urban tile with no territory."""
        out.add(t.key)
        for _, n in self.b.neighbours(t):
            if n.urban and not n.has_territory and n.key not in out:
                self.adjacent_unclaimed_urban(n, out)

    # ── Game.doUrbanSurroundedRural (Game.cs:12895) ──────────────────────
    def urban_surrounded_rural(self) -> set[Key]:
        if self._surrounded is not None:
            return self._surrounded
        b = self.b

        def rural_passable(t: Tile | None) -> bool:
            if t is None or t.water:
                return False
            if t.impassable:
                return True
            if t.urban or t.boundary or t.has_territory:
                return False
            return True

        # land sections: connected land components
        section: dict[Key, int] = {}
        for t in b.tiles.values():
            if t.land and t.key not in section:
                sid = len(section)
                queue = deque([t])
                section[t.key] = sid
                while queue:
                    cur = queue.popleft()
                    for _, n in b.neighbours(cur):
                        if n.land and n.key not in section:
                            section[n.key] = sid
                            queue.append(n)
        urban_site: dict[Key, Key] = {}
        section_sites: dict[int, int] = {}
        for start in sorted(b.tiles.values(), key=lambda t: (t.r, t.q)):
            if not start.is_city_site_any():
                continue
            section_sites[section.get(start.key, -1)] = section_sites.get(section.get(start.key, -1), 0) + 1
            queue = deque([start])
            urban_site[start.key] = start.key
            while queue:
                cur = queue.popleft()
                for _, n in b.neighbours(cur):
                    if n.urban and n.territory == start.territory and n.key not in urban_site:
                        urban_site[n.key] = start.key
                        queue.append(n)
        surrounded: set[Key] = set()
        checked: set[Key] = set()
        for start in sorted(b.tiles.values(), key=lambda t: (t.r, t.q)):
            if start.key in checked:
                continue
            checked.add(start.key)
            if not (rural_passable(start) and section_sites.get(section.get(start.key, -1), 0) > 1):
                continue
            region = {start.key}
            sites: set[Key] = set()
            queue = deque([start])
            while queue:
                cur = queue.popleft()
                for _, n in b.neighbours(cur):
                    if rural_passable(n):
                        if n.key not in checked:
                            checked.add(n.key)
                            queue.append(n)
                            region.add(n.key)
                    elif n.key in urban_site:
                        sites.add(urban_site[n.key])
                    elif n.has_territory:
                        sites.add(b.city_of(n.territory).key)
            if len(sites) == 1:
                surrounded |= region
        self._surrounded = surrounded
        return surrounded

    # ── minor cities ─────────────────────────────────────────────────────
    def city_site_and_surrounding(self, t: Tile, out: set[Key], pending: dict[Key, CityTerritory]) -> Key | None:
        """Tile.getCitySiteAndSurroundingTiles (Tile.cs:4912): the urban cluster
        plus its ring; None unless every unowned passable land tile around the
        cluster is inside an urban-surrounded rural pocket."""
        out.clear()
        site: Key | None = None
        queue = deque([t])
        out.add(t.key)
        while queue:
            cur = queue.popleft()
            if cur.has_territory or cur.key in pending:
                continue
            if cur.urban:
                if cur.is_city_site_active():
                    site = cur.key
                for _, n in self.b.neighbours(cur):
                    if n.key not in out:
                        out.add(n.key)
                        queue.append(n)
            elif cur.land and not cur.impassable and cur.key not in self.urban_surrounded_rural():
                return None
        return site

    def city_site_surrounded(self, t: Tile, pending: dict[Key, CityTerritory]) -> CityTerritory | None:
        """Tile.getCitySiteSurrounded (Tile.cs:4852): who takes a surrounded
        site — most adjacent owned tiles (land counts the cluster size, water
        1 as a tie-break), then nearest city, then lowest city tile id."""
        b = self.b

        def owned(k: Key) -> CityTerritory | None:
            tt = b.at(k)
            if tt.has_territory:
                return b.territory_ct(tt)
            return pending.get(k)

        site_tiles: set[Key] = set()
        site = self.city_site_and_surrounding(t, site_tiles, pending)
        if site is None:
            return None
        values: dict[CityTerritory, int] = {}
        for k in sorted(site_tiles, key=lambda k: (k[1], k[0])):
            ct = owned(k)
            if ct is not None and ct.city_site != site:
                values[ct] = values.get(ct, 0) + (len(site_tiles) if b.at(k).land else 1)
        best: CityTerritory | None = None
        best_value, best_dist = 0, 10 ** 9
        for ct, value in values.items():
            dist = b.distance(site, ct.city_tile)
            if (best is None or value > best_value or
                    (value == best_value and (dist < best_dist or
                                              (dist == best_dist and (ct.city_tile[1], ct.city_tile[0]) < (best.city_tile[1], best.city_tile[0]))))):
                best, best_value, best_dist = ct, value, dist
        return best

    def check_minor_city(self, t: Tile, pending: dict[Key, CityTerritory], out: list[Grab],
                         source_site: Key | None, gen: int) -> CityTerritory | None:
        """Tile.checkMinorCity (Tile.cs:11089)."""
        minor_site = self.connected_city_site_active(t)
        if minor_site is None or minor_site == source_site:
            return None
        surround = self.city_site_surrounded(t, pending)
        if surround is None or surround.player == NONE:
            return None
        urban: set[Key] = set()
        self.adjacent_unclaimed_urban(self.b.at(minor_site), urban)
        for k in sorted(urban, key=lambda k: (k[1], k[0])):
            if not self.b.at(k).boundary and k not in pending:
                pending[k] = surround
                out.append(Grab(k, surround, gen, "minor"))
        # getCityInitTiles from the site: range 2 in the surrounding city's name
        self.expansion_tiles(self.b.at(minor_site), 2, surround, pending, out, gen)
        return surround

    # ── the spread rules ─────────────────────────────────────────────────
    def owner_change_tiles(self, t: Tile, ct: CityTerritory, pending: dict[Key, CityTerritory]) -> list[tuple[Key, CityTerritory, str]]:
        """Tile.getOwnerChangeTiles (Tile.cs:7323-7470). Returns (tile, territory,
        reason) for the tile itself and each neighbour it grabs."""
        b = self.b

        def is_our_team(o: Tile) -> bool:
            p = pending.get(o.key)
            if p is not None and b.allied(p.team, p.tribe, ct.team, ct.tribe):
                return True
            owner_team = o.owner if o.owner != NONE else NONE
            return b.allied(owner_team, o.owner_tribe, ct.team, ct.tribe)

        def has_border_value_resource(o: Tile) -> bool:
            return o.resource is not None and RESOURCE[o.resource]["border"] >= 0

        def valid_expansion_direction(d: int) -> str | None:
            n = b.adjacent(t, d)
            if n is None or n.has_territory or n.key in pending:
                return None
            if self.is_non_allied_tribe_site(n, ct.player):
                return None
            if has_border_value_resource(n) and not has_border_value_resource(t):
                return "resource"
            if t.urban or n.urban:
                site = self.connected_city_site_active(n)
                if site is None or site == ct.city_site:
                    return "urban"
            if self.is_valid_growth(t) and not self.is_valid_growth(n):
                ours, theirs = 1, 0
                for flank in (b.adjacent(t, (d + 1) % 6), b.adjacent(t, (d - 1) % 6)):
                    if flank is not None and self.is_valid_growth(flank):
                        if is_our_team(flank):
                            ours += 1
                        else:
                            theirs += 1
                if ours > min(0 if (ours + theirs) == 1 else 1, theirs):
                    return "flank"
            return None

        out: list[tuple[Key, CityTerritory, str]] = []
        if self.is_valid_owner_change_territory(t, ct, pending):
            out.append((t.key, ct, "seed"))
        for d in range(6):
            n = b.adjacent(t, d)
            if n is None or n.has_territory or n.key in pending:
                continue
            reason = valid_expansion_direction(d)
            if reason:
                out.append((n.key, ct, reason))
            else:
                fill = self.do_border_fill_tile(n, pending)
                if fill is not None:
                    out.append((n.key, fill, "fill"))
        return out

    def do_border_fill_tile(self, t: Tile, pending: dict[Key, CityTerritory]) -> CityTerritory | None:
        """Tile.doBorderFill (Tile.cs:11168): an unowned, non-urban tile with
        same-team owners on two opposite sides is filled. The code then counts
        the tile's owned neighbours per side to pick the city, but it compares
        TEAMS, and both sides are the same team by construction, so every
        same-team neighbour lands in the 'opposite' bucket and the opposite
        side's city always wins; the distance and population tie-breaks below
        it are unreachable. The port keeps the whole ladder for fidelity."""
        b = self.b

        def territory(o: Tile | None) -> CityTerritory | None:
            if o is None:
                return None
            if o.has_territory:
                return b.territory_ct(o)
            return pending.get(o.key)

        if t.urban or territory(t) is not None:
            return None
        for d in range(3):
            adj = territory(b.adjacent(t, d))
            if adj is None:
                continue
            opp = territory(b.adjacent(t, d + 3))
            if opp is None or (opp.team, opp.tribe) != (adj.team, adj.tribe):
                continue
            n_adj = n_opp = 0
            for dd in range(6):
                inner = territory(b.adjacent(t, dd))
                if inner is None:
                    continue
                if (inner.team, inner.tribe) == (opp.team, opp.tribe):
                    n_opp += 1
                elif (inner.team, inner.tribe) == (adj.team, adj.tribe):
                    n_adj += 1
            if n_adj > n_opp:
                return adj
            if n_opp > n_adj:
                return opp
            d_adj, d_opp = b.distance(t.key, adj.city_tile), b.distance(t.key, opp.city_tile)
            if d_adj < d_opp:
                return adj
            if d_opp < d_adj:
                return opp
            if adj.city_id != NONE and opp.city_id == NONE:
                return opp
            return adj
        return None

    # ── the engine ───────────────────────────────────────────────────────
    def expansion_tiles(self, t: Tile, rng: int, ct: CityTerritory, pending: dict[Key, CityTerritory],
                        out: list[Grab], gen0: int = 0) -> None:
        """Tile.getExpansionTiles (Tile.cs:12657). `out` receives every grab in
        the order the game adds it; gen = BFS generation (gen0 = seeds)."""
        b = self.b
        queue: deque[tuple[Key, CityTerritory, int]] = deque()
        source_site = self.connected_city_site_active(t)
        if t.key in pending:
            queue.append((t.key, pending[t.key], gen0))
        elif t.has_territory:
            queue.append((t.key, b.territory_ct(t), gen0))
        elif self.is_valid_owner_change_territory(t, ct, pending):
            queue.append((t.key, ct, gen0))
            out.append(Grab(t.key, ct, gen0, "seed"))
            pending[t.key] = ct
        for dist in range(1, rng + 1):
            for o in b.tiles_at_distance(t, dist):
                if self.is_valid_owner_change_territory(o, ct, pending):
                    queue.append((o.key, ct, gen0))
                    out.append(Grab(o.key, ct, gen0, "seed"))
                    pending[o.key] = ct
        while queue:
            k, kct, gen = queue.popleft()
            cur = b.at(k)
            for nk, nct, reason in self.owner_change_tiles(cur, kct, pending):
                assert nk not in pending, "error in Tile.getOwnerChangeTiles"
                queue.append((nk, nct, gen + 1))
                out.append(Grab(nk, nct, gen + 1, reason))
                pending[nk] = nct
            for _, n in b.neighbours(cur):
                if n.urban and not n.has_territory and n.key not in pending:
                    minor: list[Grab] = []
                    if self.check_minor_city(n, pending, minor, source_site, gen + 1) is not None:
                        for g in minor:
                            queue.append((g.key, g.ct, g.gen))
                            out.append(g)

    # ── committing (Game.setTilesOwner, Tile.setOwner, Tile.setMinorCity) ─
    def set_tiles_owner(self, grabs: list[Grab], default_city: int) -> None:
        b = self.b
        for g in grabs:
            t = b.at(g.key)
            cid = g.ct.city_id if g.ct.city_id != NONE else default_city
            if cid == NONE:
                continue
            changed = (t.owner, t.owner_tribe, t.territory) != (g.ct.player, g.ct.tribe, cid)
            t.owner, t.owner_tribe, t.territory = g.ct.player, g.ct.tribe, cid
            if changed and t.owner != NONE and t.improvement and IMPROVEMENT[t.improvement]["removeBorder"]:
                # Tile.setOwner (Tile.cs:7540): a bRemoveBorder improvement is
                # cleared the moment a border covers it (the tile stays owned)
                b.log.append(f"{g.key}: {t.improvement} removed by the border")
                t.improvement = None
            if t.is_city_site_active():
                # Tile.setMinorCity (Tile.cs:11127)
                t.city_site = "USED"
                t.improvement = MINOR_CITY_IMPROVEMENT
                b.log.append(f"{g.key}: city site became a minor city of city {cid}")
        self._surrounded = None

    # ── triggers ─────────────────────────────────────────────────────────
    def spread_borders(self, t: Tile, gen0: int = 0) -> list[Grab]:
        """Tile.spreadBorders (Tile.cs:7777): range 1 from an owned tile."""
        out: list[Grab] = []
        if t.has_territory and t.owner != NONE:
            self.expansion_tiles(t, 1, self.b.territory_ct(t), {}, out, gen0)
            self.set_tiles_owner(out, t.territory)
        return out

    def found_city(self, t: Tile, player: int) -> tuple[int, list[Grab], list[Grab]]:
        """Game.createCityNext (Game.cs:11004) → getCityInitTiles (range 2) →
        City.start → Game.doBorderFill. Returns the new city id, the founding
        grabs and the trailing global-fill grabs."""
        b = self.b
        ct = CityTerritory(player, player, NONE, NONE, t.key, self.connected_city_site_active(t))
        out: list[Grab] = []
        self.expansion_tiles(t, 2, ct, {}, out)
        cid = b.next_city_id
        b.next_city_id += 1
        b.cities[cid] = City(cid, t.key, player)
        t.city = cid
        t.city_site = "USED"
        self.set_tiles_owner(out, cid)
        fill = self.global_fill(gen0=max((g.gen for g in out), default=0) + 1)
        return cid, out, fill

    def global_fill(self, gen0: int = 0) -> list[Grab]:
        """Game.doBorderFill (Game.cs:13155): range 0 from EVERY owned tile,
        in tile-id order, one shared pending dictionary."""
        self._surrounded = None
        pending: dict[Key, CityTerritory] = {}
        out: list[Grab] = []
        for t in sorted(self.b.tiles.values(), key=lambda t: (t.r, t.q)):
            if t.has_territory:
                self.expansion_tiles(t, 0, self.b.territory_ct(t), pending, out, gen0)
        self.set_tiles_owner(out, NONE)
        return out

    # buying
    def buy_tile_cost(self, city: City, t: Tile, yld: str) -> int:
        """City.getBuyTileCost (City.cs:9445)."""
        count = city.buy_count + self.b.player_buy_count.get(city.player, 0) // 2
        cost = YIELD[yld]["buyBase"] + YIELD[yld]["buyPer"] * count
        cost *= self.b.distance(city.key, t.key) + 1
        cost //= 3 + 1
        return max(cost, 1)

    def can_buy_tile(self, city: City, t: Tile, unlocked: bool = True) -> bool:
        """City.canBuyTile (City.cs:9493) minus the stockpile test; `unlocked`
        stands for canBuyTileUnlocked / a unit with aeBuyTileYield."""
        b = self.b
        if t.has_territory:
            if t.owner != city.player or t.improvement or t.territory == city.id:
                return False
            other = b.city_of(t.territory)
            rest = {k for k, o in b.tiles.items() if o.territory == other.id and k != t.key}
            seen = {other.key}
            queue = deque([other.key])
            while queue:
                cur = queue.popleft()
                for _, n in b.neighbours(b.at(cur)):
                    if n.key in rest and n.key not in seen:
                        seen.add(n.key)
                        queue.append(n.key)
            if len(seen) < len(rest) + 1:
                return False
        else:
            if t.water and not any(n.land for _, n in b.neighbours(t)):
                return False
            if not unlocked:
                return False
        if t.urban:
            return False
        if not any(n.territory == city.id for _, n in b.neighbours(t)):
            return False
        return True

    def buy_tile(self, city: City, t: Tile, yld: str) -> tuple[int, list[Grab]]:
        """Unit.buyTile (Unit.cs:12707): range 0 from the tile, or a plain
        reassignment when it already belongs to another of your cities."""
        assert self.can_buy_tile(city, t, True)
        cost = self.buy_tile_cost(city, t, yld)
        out: list[Grab] = []
        ct = CityTerritory(city.player, city.player, NONE, city.id, city.key, city.key)
        if not t.has_territory:
            self.expansion_tiles(t, 0, ct, {}, out)
        else:
            out.append(Grab(t.key, ct, 0, "reassign"))
        self.set_tiles_owner(out, city.id)
        city.buy_count += 1
        self.b.player_buy_count[city.player] = self.b.player_buy_count.get(city.player, 0) + 1
        return cost, out

    # growth bonuses
    def border_adjacent(self, city: City, pending: dict[Key, CityTerritory]) -> list[Key]:
        """Tile.getBorderAdjacent (Tile.cs:~12510): flood the city's contiguous
        territory from the city tile; collect adjacent valid-growth unowned tiles."""
        b = self.b

        def is_territory(o: Tile) -> bool:
            return o.territory == city.id or pending.get(o.key, CityTerritory(0, 0, 0, NONE, None, None)).city_id == city.id

        exclude = {city.key}
        out: list[Key] = []

        def walk(t: Tile) -> None:
            for _, n in b.neighbours(t):
                if n.key in exclude:
                    continue
                exclude.add(n.key)
                if is_territory(n):
                    walk(n)
                elif self.is_valid_growth(n) and n.key not in pending and not n.has_territory:
                    out.append(n.key)

        walk(b.at(city.key))
        return out

    def can_grow_border(self, t: Tile, pending: dict[Key, CityTerritory], city: City) -> bool:
        """Tile.canGrowBorder (Tile.cs:12605)."""
        b = self.b
        if t.boundary or not self.is_valid_growth(t):
            return False
        if t.urban or any(n.urban for _, n in b.neighbours(t)):
            return False
        if t.key in pending or t.has_territory:
            return False
        return any(n.territory == city.id or pending.get(n.key, CityTerritory(0, 0, 0, NONE, None, None)).city_id == city.id
                   for _, n in b.neighbours(t))

    def score_grow_tile(self, city: City, t: Tile, roll: int, pending: dict[Key, CityTerritory]) -> tuple[int, dict]:
        """City.findGrowBorderTile scoring (City.cs:9713-9787)."""
        b = self.b
        parts: dict[str, int] = {"roll": roll}
        v = roll
        parts["terrain"] = TERRAIN[t.terrain]["border"]
        parts["height"] = HEIGHT[t.height]["border"]
        parts["vegetation"] = VEGETATION[t.vegetation]["border"] if t.vegetation else 0
        parts["river"] = 100 if t.river else 0
        parts["passable"] = 0 if t.impassable else 200
        parts["trade"] = 100 if t.trade else 0
        parts["resource"] = RESOURCE[t.resource]["border"] if t.resource else 0
        adj = 0
        for _, n in b.neighbours(t):
            if t.land:
                adj += HEIGHT[n.height]["landAdj"]
            if n.territory == city.id or pending.get(n.key, CityTerritory(0, 0, 0, NONE, None, None)).city_id == city.id:
                adj += 10
            if n.key in pending or (n.owner != NONE and n.owner == city.player):
                if n.improvement:
                    adj += 20
            elif n.resource:
                adj += RESOURCE[n.resource]["border"] // 5
        parts["adjacent"] = adj
        v += sum(parts[k] for k in parts if k != "roll")
        dist = b.distance(city.key, t.key)
        parts["distance"] = dist
        total = (v * 3) // (dist + 2)
        parts["total"] = total
        return total, parts

    def find_grow_border_tile(self, city: City, pending: dict[Key, CityTerritory], rolls) -> tuple[Tile | None, list[dict]]:
        best: Tile | None = None
        best_value = 0
        table: list[dict] = []
        i = 0
        for k in self.border_adjacent(city, pending):
            t = self.b.at(k)
            if not self.can_grow_border(t, pending, city):
                continue
            roll = rolls[i] if isinstance(rolls, list) else rolls
            i += 1
            value, parts = self.score_grow_tile(city, t, roll, pending)
            table.append({"q": t.q, "r": t.r, **parts})
            if value > best_value:
                best, best_value = t, value
        return best, table

    def grow_borders(self, city: City, n: int, rolls=50) -> tuple[list[Grab], list[dict]]:
        """City.growBorders (City.cs:9812) → getBorderGrowth → n × (findGrowBorderTile
        + getExpansionTiles range 0), one shared pending dictionary."""
        ct = CityTerritory(city.player, city.player, NONE, city.id, city.key, city.key)
        pending: dict[Key, CityTerritory] = {}
        out: list[Grab] = []
        picks: list[dict] = []
        gen0 = 0
        for _ in range(n):
            pick, table = self.find_grow_border_tile(city, pending, rolls)
            if pick is None:
                break
            before = len(out)
            self.expansion_tiles(pick, 0, ct, pending, out, gen0)
            picks.append({"q": pick.q, "r": pick.r, "candidates": table})
            gen0 = max((g.gen for g in out[before:]), default=gen0) + 1
        self.set_tiles_owner(out, city.id)
        return out, picks


# ── board builders ───────────────────────────────────────────────────────────

def hexagon(radius: int, **defaults) -> dict[Key, Tile]:
    tiles = {}
    for q in range(-radius, radius + 1):
        for r in range(max(-radius, -q - radius), min(radius, -q + radius) + 1):
            tiles[(q, r)] = Tile(q, r, **defaults)
    return tiles


def make_board(tiles: dict, edits: dict | None = None, cities: list[tuple[int, Key, int]] = (),
               tribe_ally: dict | None = None) -> Board:
    """cities: (id, key, player). Every tile within `own` distance of a city is
    given to it when the edit says so via the `owned` helper below."""
    for k, attrs in (edits or {}).items():
        t = tiles[k]
        for a, v in attrs.items():
            setattr(t, a, v)
    b = Board(tiles, tribe_ally=dict(tribe_ally or {}))
    for cid, k, player in cities:
        b.cities[cid] = City(cid, k, player)
        t = tiles[k]
        t.city, t.owner, t.territory, t.city_site, t.terrain = cid, player, cid, "USED", URBAN_TERRAIN
        b.next_city_id = max(b.next_city_id, cid + 1)
    return b


def own(b: Board, cid: int, keys) -> None:
    c = b.city_of(cid)
    for k in keys:
        t = b.at(k)
        t.owner, t.territory = c.player, cid


def disc(center: Key, radius: int, tiles: dict) -> list[Key]:
    return [k for k in tiles if Board.distance(center, k) <= radius]


def W(**kw):
    return dict(terrain="TERRAIN_WATER", height="HEIGHT_COAST", **kw)


def MTN(**kw):
    return dict(height="HEIGHT_MOUNTAIN", **kw)


def U(**kw):
    return dict(terrain=URBAN_TERRAIN, **kw)


# ── scenarios ────────────────────────────────────────────────────────────────

def scenario_defs() -> list[dict]:
    defs: list[dict] = []

    # 2a — resource pull
    def resource_board():
        b = make_board(hexagon(2), edits={(1, -1): dict(resource="RESOURCE_HORSE"), (2, -1): dict(resource="RESOURCE_SHEEP"),
                                          (1, 1): dict(resource="RESOURCE_WHEAT"), (0, 0): dict(resource="RESOURCE_MARBLE")},
                       cities=[(0, (-1, 0), 0)])
        own(b, 0, [(0, 0), (-1, 1), (0, -1), (-2, 1), (-2, 2)])
        return b
    defs.append(dict(
        id="resource", section="rules", title="Resource pull",
        caption="An owned tile without a resource grabs any adjacent resource tile.",
        board=resource_board, trigger=("fill", (0, -1)),
        expect=dict(grabbed={(1, -1)}, not_grabbed={(1, 0), (2, -1), (1, 1)}),
    ))
    # the same board from the Marble tile: a resource tile pulls nothing
    defs.append(dict(
        id="resource_from_resource", section="rules", render=False, title="A resource tile pulls no resource",
        board=resource_board, trigger=("fill", (0, 0)),
        expect=dict(grabbed=set(), not_grabbed={(1, 0), (1, -1)}),
    ))

    # 2b — urban pull
    def urban_board():
        b = make_board(hexagon(2), edits={(0, -1): U(), (1, -1): U()}, cities=[(0, (0, 0), 0)])
        own(b, 0, [(0, -1), (1, -1), (-1, 0), (-1, 1), (0, 1), (1, 0)])
        return b
    defs.append(dict(
        id="urban", section="rules", title="Urban pull",
        caption="An urban tile grabs every tile around it, whatever it is.",
        board=urban_board, trigger=("fill", (1, -1)),
        expect=dict(grabbed={(2, -2), (1, -2), (2, -1)}, not_grabbed={(0, 2), (-2, 2)}),
    ))

    # 2c — flank rule, four boards from one shape: T owned at (0,0), N = water at (1,-1)
    def flank_board(clockwise, counter):
        # T=(0,0); N=(1,-1) is direction NE (index 1); flankers are E (1,0) and NW (0,-1)
        edits = {(1, -1): W(), (2, -2): W(), (2, -1): W(), (1, -2): W()}
        edits[(1, 0)] = clockwise
        edits[(0, -1)] = counter
        b = make_board(hexagon(2), edits=edits, cities=[(0, (-1, 1), 0)])
        own(b, 0, [(0, 0), (-1, 0), (0, 1), (-2, 1), (-1, 2), (-2, 2)])
        return b
    defs.append(dict(
        id="flank_open", section="rules", title="Water with no land flankers",
        caption="Both tiles flanking the water are water too: taken.",
        board=lambda: flank_board(W(), W()), trigger=("fill", (0, 0)),
        expect=dict(grabbed_has={(1, -1)}, reason={(1, -1): "flank"}),
    ))
    defs.append(dict(
        id="flank_unowned", section="rules", title="One unowned land flanker",
        caption="A flanker that is passable land but not yours blocks the grab.",
        board=lambda: flank_board(dict(), W()), trigger=("fill", (0, 0)),
        expect=dict(not_grabbed={(1, -1)}),
    ))

    def flank_ours_board():
        b = flank_board(dict(), dict())
        own(b, 0, [(1, 0)])
        return b
    defs.append(dict(
        id="flank_ours", section="rules", title="One flanker yours, one unowned",
        caption="Once one flanker is yours the water is taken even if the other is not.",
        board=flank_ours_board, trigger=("fill", (0, 0)),
        expect=dict(grabbed={(1, -1)}),
    ))

    def flank_enemy_board():
        b = make_board(hexagon(2), edits={(1, -1): W(), (2, -2): W(), (2, -1): W(), (1, -2): W(), (0, -1): W()},
                       cities=[(0, (-1, 1), 0), (1, (2, 0), 1)])
        own(b, 0, [(0, 0), (-1, 0), (0, 1), (-2, 1), (-1, 2), (-2, 2)])
        own(b, 1, [(1, 0)])
        return b
    defs.append(dict(
        id="flank_enemy", section="rules", title="One flanker the enemy's",
        caption="An enemy flanker counts like an unowned one: no grab without a flanker of your own.",
        board=flank_enemy_board, trigger=("fill", (0, 0)),
        expect=dict(not_grabbed={(1, -1)}),
    ))

    # mountains obey the same rule
    def flank_mountain_board():
        b = make_board(hexagon(2), edits={(1, -1): MTN(), (1, 0): MTN(), (0, -1): MTN()}, cities=[(0, (-1, 1), 0)])
        own(b, 0, [(0, 0), (-1, 0), (0, 1)])
        return b
    defs.append(dict(
        id="flank_mountain", section="rules", render=False, title="Mountains follow the flank rule",
        board=flank_mountain_board, trigger=("fill", (0, 0)),
        expect=dict(grabbed={(1, -1), (1, 0), (0, -1)}),
    ))

    # 2d — hole fill
    def hole_board():
        b = make_board(hexagon(2), cities=[(0, (-2, 1), 0), (1, (2, -1), 1)])
        own(b, 0, [(-1, 0), (-1, 1), (-2, 2), (-1, 2)])
        own(b, 1, [(0, -1), (0, 1), (1, -1), (1, 0), (1, -2), (2, -2), (2, 0), (1, 1)])
        return b
    defs.append(dict(
        id="hole", section="rules", title="Hole fill",
        caption="An unowned tile with the same team on two opposite sides is filled; here the enemy fills it, not you.",
        board=hole_board, trigger=("fill", (1, 0)),
        expect=dict(grabbed={(0, 0)}, owner={(0, 0): 1}, reason={(0, 0): "fill"}),
    ))

    def hole_two_cities_board():
        b = make_board(hexagon(2), cities=[(0, (-2, 2), 0), (1, (1, -1), 0)])
        own(b, 0, [(-1, 1), (-2, 1), (-1, 2), (0, 1)])
        own(b, 1, [(2, -2), (1, -2), (2, -1), (0, -1)])
        return b
    defs.append(dict(
        id="hole_which", section="rules", title="Which city gets a filled tile",
        caption="Two of your cities either side of a hole: the far side of the first matching axis wins, here the distant city over the adjacent one.",
        board=hole_two_cities_board, trigger=("fill", (0, 1)),
        expect=dict(grabbed_has={(0, 0)}, territory={(0, 0): 0}),
    ))

    # 3 — chain: specialist → ring → resource → water (flank) → hole fill
    def chain_board():
        edits = {
            (1, -2): dict(resource="RESOURCE_FISH", improvement=None, terrain="TERRAIN_WATER", height="HEIGHT_COAST"),
            (2, -3): W(), (2, -2): W(), (3, -3): W(), (3, -2): W(),
            (1, -3): dict(resource="RESOURCE_GAME", vegetation="VEGETATION_TREES"),
            (0, -3): dict(vegetation="VEGETATION_TREES"),
            (-1, -1): dict(specialist=True, improvement="IMPROVEMENT_FARM"),
        }
        b = make_board(hexagon(3), edits=edits, cities=[(0, (-1, 1), 0)])
        own(b, 0, disc((-1, 1), 1, b.tiles) + [(-1, -1), (0, -1), (-2, 0), (1, -1), (0, 0), (2, -1)])
        return b
    defs.append(dict(
        id="chain", section="chain", title="A specialist starts a chain",
        caption="0 is the specialist's range; every later number is a rule firing from a tile grabbed the step before.",
        board=chain_board, trigger=("specialist", (-1, -1)),
        expect=dict(grabbed={(-1, -2), (0, -2), (-2, -1), (1, -2), (1, -3), (2, -3), (2, -2)},
                    gen={(-1, -2): 0, (1, -2): 1, (1, -3): 1, (2, -3): 2, (2, -2): 2},
                    reason={(1, -3): "resource", (1, -2): "resource", (2, -3): "flank", (2, -2): "fill"}),
    ))

    # 4 — founding: radius 2 + urban rings, then a resource at distance 3
    def found_board():
        edits = {(0, 0): U(city_site="ACTIVE"), (1, 0): U(), (1, 1): U(), (2, 0): U(),
                 (3, -2): dict(resource="RESOURCE_ORE", height="HEIGHT_HILL"),
                 (-3, 1): dict(resource="RESOURCE_WHEAT")}
        return make_board(hexagon(3), edits=edits)
    defs.append(dict(
        id="found", section="founding", title="Founding a city",
        caption="Radius 2 is seeded at once (0); the urban tiles then pull their own ring, and the ring pulls resources (1).",
        board=found_board, trigger=("found", (0, 0), 0),
        expect=dict(grabbed_has={(3, 0), (3, -1), (2, 1), (1, 2), (3, -2), (-3, 1)}, not_grabbed={(3, -3), (0, 3), (-3, 0)},
                    gen={(2, 0): 0, (3, 0): 1, (3, -2): 1, (-3, 1): 1},
                    reason={(3, 0): "urban", (3, -2): "resource"}, post_fill_empty=True),
    ))

    # 4b — a neighbouring city site swallowed at founding
    def minor_board():
        edits = {(0, 0): U(city_site="ACTIVE"), (0, -1): U(),
                 (3, -1): U(city_site="ACTIVE"), (3, -2): U(),
                 (4, -2): W(), (4, -3): W(), (3, -3): W(), (4, -1): W(), (3, 0): W(), (2, -3): W(),
                 (2, -4): W(), (1, -4): W(), (3, -4): W(), (4, -4): W(),
                 (2, 0): dict(resource="RESOURCE_HORSE")}
        return make_board(hexagon(4), edits=edits)
    defs.append(dict(
        id="minor", section="founding", title="A site next door becomes a minor city",
        caption="Every passable land tile around the second site is owned after the radius-2 seed, so the whole site and its own radius 2 join the new city.",
        board=minor_board, trigger=("found", (0, 0), 0),
        expect=dict(grabbed_has={(3, -1), (3, -2), (4, -2), (2, -3)}, minor={(3, -1)}, reason={(3, -1): "minor"}),
    ))
    # the same site with one unowned passable land tile next to it stays independent
    def minor_open_board():
        b = minor_board()
        b.at((3, 0)).terrain, b.at((3, 0)).height = "TERRAIN_TEMPERATE", "HEIGHT_FLAT"
        return b
    defs.append(dict(
        id="minor_open", section="founding", render=False, title="One unowned land tile keeps a site independent",
        board=minor_open_board, trigger=("found", (0, 0), 0),
        expect=dict(not_grabbed={(3, -1), (3, -2), (4, -2)}),
    ))

    # 6 — buying
    def buy_board():
        edits = {(3, -2): dict(resource="RESOURCE_CATTLE"), (2, -1): dict(height="HEIGHT_HILL"),
                 (-2, 2): W(), (-3, 3): W(), (-2, 3): W()}
        b = make_board(hexagon(3), edits=edits, cities=[(0, (0, 0), 0)])
        own(b, 0, disc((0, 0), 1, b.tiles))
        return b
    defs.append(dict(
        id="buy", section="buying", title="Buying a tile",
        caption="Dashed tiles can be bought (label = Money cost from this city); buying the hill pulls the cattle behind it for free.",
        board=buy_board, trigger=("buy", (2, -1), 0, "YIELD_MONEY"),
        expect=dict(grabbed={(2, -1), (3, -2)}, cost=15, reason={(3, -2): "resource"}),
    ))

    # 7 — growth bonus: two picks
    def grow_board():
        edits = {(2, -1): dict(vegetation="VEGETATION_TREES"), (-2, 1): dict(terrain="TERRAIN_ARID"),
                 (0, -2): dict(height="HEIGHT_HILL"), (2, -2): W(), (3, -2): W(), (3, -3): W(),
                 (1, 1): dict(terrain="TERRAIN_LUSH", river=[0]), (-1, 2): dict(terrain="TERRAIN_LUSH"),
                 (0, 2): dict(resource="RESOURCE_WHEAT"), (2, 0): dict(resource="RESOURCE_HORSE"),
                 (-1, -1): dict(vegetation="VEGETATION_TREES"), (-2, 2): dict(terrain="TERRAIN_TUNDRA")}
        b = make_board(hexagon(3), edits=edits, cities=[(0, (0, 0), 0)])
        own(b, 0, disc((0, 0), 1, b.tiles) + [(2, 0), (0, 2)])
        return b
    defs.append(dict(
        id="grow", section="growth", title="A growth bonus picks by score",
        caption="Two tiles: each pick is the highest-scoring candidate adjacent to the territory, then the chain runs from it.",
        board=grow_board, trigger=("grow", 0, 2, 50),
        expect=dict(grab_count_min=2),
    ))

    # 8 — losing tiles
    # other active city site: blocked
    def site_blocked_board():
        b = make_board(hexagon(2), edits={(1, -1): U(city_site="ACTIVE"), (1, 0): U(), (2, -1): U()}, cities=[(0, (-1, 0), 0)])
        own(b, 0, [(0, 0), (0, -1), (-1, 1)])
        return b
    defs.append(dict(
        id="site_blocked", section="losing", render=False, title="Another active site's urban tiles are never grabbed",
        board=site_blocked_board, trigger=("fill", (0, 0)),
        expect=dict(not_grabbed={(1, -1), (1, 0)}),
    ))

    # a tribe settlement whose every passable land neighbour is yours: the code
    # path has no tribe test, so the site is swallowed as a minor city
    def tribe_surrounded_board():
        edits = {(0, 0): U(improvement="IMPROVEMENT_SETTLEMENT_2", tribe=3, city_site="ACTIVE"),
                 (1, -1): W(), (1, 0): W()}
        b = make_board(hexagon(2), edits=edits, cities=[(0, (-2, 2), 0)])
        own(b, 0, [k for k in b.tiles if k not in ((0, 0), (1, -1), (1, 0), (2, -2), (2, -1), (2, 0))])
        return b
    defs.append(dict(
        id="tribe_surrounded", section="losing", title="A surrounded tribe site becomes your minor city",
        caption="Every passable land tile around the Outpost is yours, so the end-of-turn fill swallows the site: the Outpost becomes a Minor City and everything within 2 of it joins your city, the water and the land beyond included.",
        board=tribe_surrounded_board, trigger=("fill", (-1, 0)),
        expect=dict(grabbed={(0, 0), (1, -1), (1, 0), (2, -2), (2, -1), (2, 0)}, minor={(0, 0)},
                    reason={(0, 0): "minor", (2, -1): "seed"}, improvement_removed={(0, 0)}),
    ))

    # map boundary excluded from growth picks
    def boundary_board():
        b = make_board(hexagon(2), edits={k: dict(boundary=True) for k in hexagon(2) if Board.distance((0, 0), k) == 2 and k != (2, -2)},
                       cities=[(0, (0, 0), 0)])
        own(b, 0, disc((0, 0), 1, b.tiles))
        return b
    defs.append(dict(
        id="boundary_grow", section="losing", render=False, title="Boundary tiles are never a growth pick",
        board=boundary_board, trigger=("grow", 0, 1, 50),
        expect=dict(grabbed={(2, -2)}),
    ))
    return defs


def snapshot(b: Board) -> dict[Key, tuple[int, int, str | None, str | None]]:
    return {k: (t.owner, t.territory, t.improvement, t.city_site) for k, t in b.tiles.items()}


def compute(defn: dict) -> dict:
    b: Board = defn["board"]()
    for cid, keys in defn.get("pre_own", {}).items():
        own(b, cid, keys)
    eng = Engine(b)
    before = snapshot(b)
    trig = defn["trigger"]
    grabs: list[Grab] = []
    extra: dict = {}
    if trig[0] == "fill":
        t = b.at(trig[1])
        out: list[Grab] = []
        eng.expansion_tiles(t, 0, b.territory_ct(t), {}, out)
        eng.set_tiles_owner(out, t.territory)
        grabs = out
        extra["from"] = list(trig[1])
    elif trig[0] == "specialist":
        grabs = eng.spread_borders(b.at(trig[1]))
        extra["from"] = list(trig[1])
    elif trig[0] == "found":
        cid, grabs, fill = eng.found_city(b.at(trig[1]), trig[2])
        extra["from"] = list(trig[1])
        extra["postFill"] = [{"q": g.key[0], "r": g.key[1], "gen": g.gen, "reason": g.reason} for g in fill]
        grabs = grabs + fill
    elif trig[0] == "buy":
        city = b.city_of(trig[2])
        t = b.at(trig[1])
        buyable = []
        for o in sorted(b.tiles.values(), key=lambda o: (o.r, o.q)):
            if not o.has_territory and eng.can_buy_tile(city, o, True):
                buyable.append({"q": o.q, "r": o.r, "cost": eng.buy_tile_cost(city, o, trig[3])})
        extra["buyable"] = buyable
        cost, grabs = eng.buy_tile(city, t, trig[3])
        extra["from"] = list(trig[1])
        extra["cost"] = cost
        extra["unit"] = {"q": t.q, "r": t.r, "type": "UNIT_WORKER", "owner": city.player}
    elif trig[0] == "grow":
        city = b.city_of(trig[1])
        grabs, picks = eng.grow_borders(city, trig[2], trig[3])
        extra["picks"] = picks
        extra["roll"] = trig[3]

    exp = defn["expect"]
    sid = defn["id"]
    grabbed = {g.key for g in grabs}
    gen_of = {g.key: g.gen for g in grabs}
    if "grabbed" in exp:
        assert grabbed == exp["grabbed"], f"{sid}: grabbed {sorted(grabbed)} != {sorted(exp['grabbed'])}"
    if "grabbed_has" in exp:
        assert exp["grabbed_has"] <= grabbed, f"{sid}: missing {exp['grabbed_has'] - grabbed}; got {sorted(grabbed)}"
    if "not_grabbed" in exp:
        assert not (exp["not_grabbed"] & grabbed), f"{sid}: unexpected {exp['not_grabbed'] & grabbed}"
    for k, g in exp.get("gen", {}).items():
        assert gen_of.get(k) == g, f"{sid}: gen of {k} = {gen_of.get(k)}, expected {g}"
    reason_of = {g.key: g.reason for g in grabs}
    for k, why in exp.get("reason", {}).items():
        assert reason_of.get(k) == why, f"{sid}: reason of {k} = {reason_of.get(k)}, expected {why}"
    if exp.get("post_fill_empty"):
        assert not extra.get("postFill"), f"{sid}: the trailing fill added {extra['postFill']}"
    for k in exp.get("improvement_removed", set()):
        assert before[k][2] and b.at(k).improvement != before[k][2], f"{sid}: improvement at {k} was not removed"
    for k, o in exp.get("owner", {}).items():
        assert b.at(k).owner == o, f"{sid}: owner of {k} = {b.at(k).owner}, expected {o}"
    for k, c in exp.get("territory", {}).items():
        assert b.at(k).territory == c, f"{sid}: territory of {k} = {b.at(k).territory}, expected {c}"
    for k, imp in exp.get("improvement", {}).items():
        assert b.at(k).improvement == imp, f"{sid}: improvement at {k} = {b.at(k).improvement}, expected {imp}"
    for k in exp.get("minor", set()):
        assert b.at(k).improvement == MINOR_CITY_IMPROVEMENT and b.at(k).city_site == "USED", f"{sid}: {k} is not a minor city"
    if "cost" in exp:
        assert extra["cost"] == exp["cost"], f"{sid}: cost {extra['cost']} != {exp['cost']}"
    if "grab_count_min" in exp:
        assert len(grabs) >= exp["grab_count_min"], f"{sid}: only {len(grabs)} grabs"

    tiles_out = []
    for t in sorted(b.tiles.values(), key=lambda t: (t.r, t.q)):
        o0, c0, i0, s0 = before[t.key]
        tiles_out.append({
            "q": t.q, "r": t.r, "terrain": t.terrain, "height": t.height, "vegetation": t.vegetation,
            "resource": t.resource, "resourceIcon": resource_icon(t.resource) if t.resource else None,
            "improvement": t.improvement, "improvementBefore": i0,
            "improvementName": improvement_name(t.improvement) if t.improvement else (improvement_name(i0) if i0 else None),
            "river": t.river, "boundary": t.boundary,
            "city": b.city_of(t.city).player if t.city != NONE else None,
            "cityId": t.city if t.city != NONE else None,
            "owner": t.owner if t.owner != NONE else None,
            "territory": t.territory if t.territory != NONE else None,
            "ownerBefore": o0 if o0 != NONE else None,
            "citySite": t.city_site, "citySiteBefore": s0,
            "specialist": t.specialist, "tribe": t.tribe if t.tribe != NONE else None,
            "minorCity": t.improvement == MINOR_CITY_IMPROVEMENT,
            "improvementRemoved": bool(i0) and t.improvement != i0 and t.improvement != MINOR_CITY_IMPROVEMENT,
        })
    units = []
    if "unit" in extra:
        u = extra["unit"]
        units.append({**u, "iconSlug": UNITS[u["type"]]["icon"].removeprefix("UNIT_").lower(),
                      "name": name_of(UNITS[u["type"]]["nameKey"], "Worker"), "mover": False, "hidden": False})
    return {
        "id": sid, "section": defn["section"], "render": defn.get("render", True),
        "title": defn["title"], "caption": defn.get("caption", ""),
        "trigger": {"kind": trig[0], **{k: v for k, v in extra.items() if k not in ("picks", "buyable", "postFill", "unit")}},
        "tiles": tiles_out,
        "units": units,
        "grabs": [{"q": g.key[0], "r": g.key[1], "gen": g.gen, "reason": g.reason,
                   "player": g.ct.player, "city": (g.ct.city_id if g.ct.city_id != NONE else None)} for g in grabs],
        "buyable": extra.get("buyable", []),
        "picks": extra.get("picks", []),
        "postFill": extra.get("postFill", []),
        "log": list(b.log),
        # HexBoard compatibility (ZOC fields, unused here)
        "zoc": [], "overlayZoc": [], "steps": [], "reach": [],
    }


# ── data tables ──────────────────────────────────────────────────────────────

def improvement_name(iid: str) -> str:
    return name_of(IMPROVEMENT[iid]["nameKey"] or f"TEXT_{iid}", nice(iid, "IMPROVEMENT_"))


def build_spreaders() -> list[dict]:
    """Every improvement Tile.isImprovementBorderSpread says spreads borders,
    and why (Tile.cs:6111)."""
    unlock_by_improvement: dict[str, list[str]] = {}
    for eid, e in EFFECT_PLAYER.items():
        for imp in e["spread"]:
            unlock_by_improvement.setdefault(imp, []).append(eid)
    out = []
    for iid, info in IMPROVEMENT.items():
        reasons = []
        if info["urban"]:
            reasons.append("urban")
        if info["spreads"]:
            reasons.append("bSpreadsBorders")
        if iid in unlock_by_improvement:
            reasons.append("unlock")
        if not reasons:
            continue
        gc = info["gameContent"]
        out.append({
            "id": iid, "name": improvement_name(iid), "slug": iid.removeprefix("IMPROVEMENT_").lower(),
            "reasons": reasons, "wonder": info["wonder"], "class": info["class"],
            "gameContent": gc, "dlc": DLC_NAMES.get(gc, "") if gc else "",
            "unlockedBy": [{"id": e, "name": effect_source_name(e)} for e in unlock_by_improvement.get(iid, [])],
        })
    out.sort(key=lambda r: (0 if "bSpreadsBorders" in r["reasons"] else 1, 0 if r["wonder"] else 1, r["name"]))
    return out


def effect_source_name(eid: str) -> str:
    for src in TRAIT_EFFECTS.get(eid, []):
        return name_of(f"GENDERED_TEXT_{src['id']}", nice(src["id"], "TRAIT_")) + " (trait)"
    if eid in LAW_EFFECTS:
        return name_of(f"TEXT_{LAW_EFFECTS[eid]}", nice(LAW_EFFECTS[eid], "LAW_")) + " (law)"
    if eid in FAMILY_SEAT_EFFECTS:
        return name_of(f"TEXT_{FAMILY_SEAT_EFFECTS[eid]}", nice(FAMILY_SEAT_EFFECTS[eid], "FAMILYCLASS_")) + " seat"
    return nice(eid, "EFFECTPLAYER_")


def effect_sources(eid: str, kind: str) -> list[dict]:
    out = []
    for src in TRAIT_EFFECTS.get(eid, []):
        gc = src["gameContent"]
        out.append({"id": src["id"], "kind": "trait", "via": src["via"],
                    "name": name_of(f"GENDERED_TEXT_{src['id']}", nice(src["id"], "TRAIT_")),
                    "dlc": DLC_NAMES.get(gc, "") if gc else ""})
    if eid in LAW_EFFECTS:
        out.append({"id": LAW_EFFECTS[eid], "kind": "law", "name": name_of(f"TEXT_{LAW_EFFECTS[eid]}", nice(LAW_EFFECTS[eid], "LAW_")), "dlc": ""})
    if eid in FAMILY_SEAT_EFFECTS:
        out.append({"id": FAMILY_SEAT_EFFECTS[eid], "kind": "familySeat",
                    "name": name_of(f"TEXT_{FAMILY_SEAT_EFFECTS[eid]}", nice(FAMILY_SEAT_EFFECTS[eid], "FAMILYCLASS_")), "dlc": ""})
    return out


def build_buy_tile(eng: Engine) -> dict:
    unlocks = []
    for eid, e in EFFECT_PLAYER.items():
        for y in e["buy"]:
            unlocks.append({"effect": eid, "scope": "player", "yield": y, "yieldName": name_of(YIELD[y]["nameKey"], nice(y, "YIELD_")),
                            "sources": effect_sources(eid, "player")})
    for eid, e in EFFECT_CITY.items():
        for y in e["buy"]:
            unlocks.append({"effect": eid, "scope": "city", "yield": y, "yieldName": name_of(YIELD[y]["nameKey"], nice(y, "YIELD_")),
                            "sources": effect_sources(eid, "city")})
    for eid, ys in EFFECT_UNIT_BUY.items():
        for y in ys:
            unlocks.append({"effect": eid, "scope": "unit", "yield": y, "yieldName": name_of(YIELD[y]["nameKey"], nice(y, "YIELD_")), "sources": []})
    unlocks.sort(key=lambda u: (u["scope"], u["effect"]))
    yields = {y: {"base": i["buyBase"], "per": i["buyPer"], "name": name_of(i["nameKey"], nice(y, "YIELD_"))}
              for y, i in YIELD.items() if i["buyBase"] or i["buyPer"]}
    grid = {}
    for y, yi in yields.items():
        rows = []
        for dist in range(1, 6):
            row = []
            for count in range(0, 7):
                cost = max((yi["base"] + yi["per"] * count) * (dist + 1) // 4, 1)
                row.append(cost)
            rows.append({"distance": dist, "costs": row})
        grid[y] = rows
    # cross-check the grid against the port
    b = make_board(hexagon(3), cities=[(0, (0, 0), 0)])
    e = Engine(b)
    assert e.buy_tile_cost(b.city_of(0), b.at((1, 0)), "YIELD_MONEY") == grid["YIELD_MONEY"][0]["costs"][0]
    assert e.buy_tile_cost(b.city_of(0), b.at((3, 0)), "YIELD_TRAINING") == grid["YIELD_TRAINING"][2]["costs"][0]
    return {
        "unlocks": unlocks, "yields": yields, "grid": grid, "counts": list(range(0, 7)),
        "orderCost": GLOBALS_INT.get("UNIT_BUY_TILE_COST", 0),
        "unitEffectExists": bool(EFFECT_UNIT_BUY),
    }


def bonus_label(bid: str) -> dict:
    """A readable label for a bonus id: the tech card, the event it belongs to,
    or the bonus family name."""
    if bid.startswith("BONUS_EVENTOPTION_"):
        stem = bid.removeprefix("BONUS_EVENTOPTION_").split("_OPTION_")[0]
        for cand in (f"EVENTSTORY_{stem}",):
            if cand in EVENT_STORY_NAMES:
                return {"kind": "event", "name": name_of(EVENT_STORY_NAMES[cand], nice(stem, "")), "event": cand}
        return {"kind": "event", "name": nice(stem, ""), "event": ""}
    if bid.startswith("BONUS_TECH_"):
        for tid, t in TECHS.items():
            if t["bonusDiscover"] == bid or bid in BONUS_CHILDREN.get(t["bonusDiscover"], []):
                prereq = t["prereqs"][0] if t["prereqs"] else ""
                return {"kind": "tech", "name": name_of(t["nameKey"], nice(tid, "TECH_")), "tech": tid, "prereqId": prereq,
                        "prereq": name_of(TECHS[prereq]["nameKey"], nice(prereq, "TECH_")) if prereq else ""}
    return {"kind": "bonus", "name": nice(bid, "BONUS_")}


def build_growth() -> dict:
    values = []
    for bid, (v, fname) in sorted(BONUS_GROWTH.items()):
        values.append({"id": bid, "value": v, "file": fname, **bonus_label(bid)})
    parents = {child: parent for parent, kids in BONUS_CHILDREN.items() for child in kids}
    for row in values:
        if row["id"] in parents:
            row["parent"] = parents[row["id"]]
    weights = {
        "terrain": {t: i["border"] for t, i in TERRAIN.items() if i["border"] > 0},
        "height": {h: i["border"] for h, i in HEIGHT.items() if i["border"] > 0},
        "vegetation": {v: i["border"] for v, i in VEGETATION.items() if i["border"] > 0},
        "resource": {r: i["border"] for r, i in RESOURCE.items() if i["border"] > 0},
        "landAdjacent": {h: i["landAdj"] for h, i in HEIGHT.items() if i["landAdj"] > 0},
        "negative": sorted([k for k, i in TERRAIN.items() if i["border"] < 0] + [k for k, i in HEIGHT.items() if i["border"] < 0]
                           + [k for k, i in VEGETATION.items() if i["border"] < 0] + [k for k, i in RESOURCE.items() if i["border"] < 0]),
        "river": 100, "passable": 200, "tradeNetwork": 100, "ownCityAdjacent": 10, "alliedImprovedAdjacent": 20,
        "adjacentResourceDivisor": 5, "distanceNumerator": 3, "distanceOffset": 2, "rollMax": 100,
    }
    names = {k: name_of(TERRAIN[k]["nameKey"], nice(k, "TERRAIN_")) for k in TERRAIN}
    names.update({k: name_of(HEIGHT[k]["nameKey"], nice(k, "HEIGHT_")) for k in HEIGHT})
    names.update({k: name_of(VEGETATION[k]["nameKey"], nice(k, "VEGETATION_")) for k in VEGETATION})
    names.update({k: name_of(RESOURCE[k]["nameKey"], nice(k, "RESOURCE_")) for k in RESOURCE})
    return {"values": values, "weights": weights, "names": names}


def main() -> int:
    scenarios = [compute(d) for d in scenario_defs()]
    # cross-scenario sanity: the two flank counter-examples to the wiki's wording
    by_id = {s["id"]: s for s in scenarios}
    assert (1, -1) in {(g["q"], g["r"]) for g in by_id["flank_open"]["grabs"]}
    assert (1, -1) not in {(g["q"], g["r"]) for g in by_id["flank_unowned"]["grabs"]}
    eng = Engine(make_board(hexagon(1)))

    spreaders = build_spreaders()
    remove_border = sorted(iid for iid, i in IMPROVEMENT.items() if i["removeBorder"])
    territory_only = sorted(iid for iid, i in IMPROVEMENT.items() if i["territoryOnly"])
    adj_specialists = {iid: i["adjSpecialists"] for iid, i in IMPROVEMENT.items() if i["adjSpecialists"]}
    add_urban = [{"id": eid, "sources": effect_sources(eid, "player")} for eid, e in EFFECT_PLAYER.items() if e["addUrban"]]
    builders = sorted(name_of(u["nameKey"], nice(uid, "UNIT_")) for uid, u in UNITS.items() if u["build"])

    payload = {
        "_meta": {
            "source": "terrain/height/vegetation/resource/improvement/yield/bonus/effect*/trait/law/familyClass/tech/globals XML + Tile.cs/City.cs/Game.cs/Unit.cs port",
            "scenarioCount": len(scenarios),
            "spreaderCount": len(spreaders),
        },
        "spreaders": spreaders,
        "spreadersSummary": {
            "flagged": sorted(iid for iid, i in IMPROVEMENT.items() if i["spreads"]),
            "flaggedWonders": sum(1 for iid, i in IMPROVEMENT.items() if i["spreads"] and i["wonder"]),
            "flaggedNonWonders": [iid for iid, i in IMPROVEMENT.items() if i["spreads"] and not i["wonder"]],
            "urbanCount": sum(1 for i in IMPROVEMENT.values() if i["urban"]),
            "wondersNotFlagged": sorted(iid for iid, i in IMPROVEMENT.items() if i["wonder"] and not i["spreads"]),
            "adjacentSpecialists": adj_specialists,
        },
        "buyTile": build_buy_tile(eng),
        "growth": build_growth(),
        "constants": {
            "borderVisibility": GLOBALS_INT["BORDER_VISIBILITY"],
            "extraVisibility": GLOBALS_INT.get("EXTRA_VISIBILITY", 0),
            "consumptionBordersModifier": GLOBALS_INT["CONSUMPTION_BORDERS_MODIFIER"],
            "familyTerritoryModifier": GLOBALS_INT["FAMILY_TERRITORY_MODIFIER"],
            "unitBuyTileCost": GLOBALS_INT["UNIT_BUY_TILE_COST"],
            "foundBorderPreviewColor": COLORS.get("COLOR_MULTIPLIER_FOUND_BORDER_PREVIEW", ""),
            "borderPatterns": BORDER_PATTERNS,
            "minorCityImprovement": MINOR_CITY_IMPROVEMENT,
            "minorCityName": improvement_name(MINOR_CITY_IMPROVEMENT),
            "urbanTerrain": URBAN_TERRAIN,
            "removeBorder": [{"id": i, "name": improvement_name(i), "tribe": IMPROVEMENT[i]["tribe"]} for i in remove_border],
            "territoryOnlyCount": len(territory_only),
            "improvementCount": len(IMPROVEMENT),
            "territoryWaterUnits": sorted(name_of(u["nameKey"], nice(uid, "UNIT_")) for uid, u in UNITS.items() if u["territoryWater"]),
            "builders": builders,
            "addUrban": add_urban,
            "negativeBorderValues": build_growth()["weights"]["negative"],
        },
        "texts": {
            "territoryName": name_of("GENDERED_TEXT_CONCEPT_TERRITORY", "Territory"),
            "territory": game_text("TEXT_HELPTEXT_LINK_HELP_TERRITORY"),
            "buyTileName": name_of("GENDERED_TEXT_CONCEPT_BUY_TILE", "Buy Tiles"),
            "buyTile": game_text("TEXT_HELPTEXT_LINK_HELP_BUY_TILE"),
            "citySiteName": name_of("GENDERED_TEXT_CONCEPT_CITY_SITE", "City Site"),
            "citySite": game_text("TEXT_HELPTEXT_LINK_HELP_CITY_SITE"),
            "spreadsBorders": game_text("TEXT_HELPTEXT_LINK_HELP_URBAN_SPREADS_BORDERS"),
            "borderGrowthLog": TEXT.get("TEXT_GAME_DO_BONUS_BORDER_GROWTH", ""),
        },
        "scenarios": scenarios,
    }

    # data-driven statements the page makes in prose
    assert payload["spreadersSummary"]["wondersNotFlagged"] == [], "a wonder no longer spreads borders — update the page"
    assert set(payload["spreadersSummary"]["flaggedNonWonders"]) == {"IMPROVEMENT_HARBOR"} | {
        i for i, info in IMPROVEMENT.items() if info["class"] == "IMPROVEMENTCLASS_HOLY_SITE"}, "non-wonder spreaders changed"
    assert not adj_specialists, "aeAdjacentImprovementSpecialists is now populated — the free-specialist spread path is live"
    assert not EFFECT_UNIT_BUY, "effectUnit aeBuyTileYield is now populated — a unit can unlock tile buying"
    assert payload["growth"]["weights"]["negative"] == ["HEIGHT_MOUNTAIN", "HEIGHT_VOLCANO", "TERRAIN_WATER"]
    assert {u["effect"] for u in payload["buyTile"]["unlocks"]} == {
        "EFFECTPLAYER_LAW_COLONIES", "EFFECTPLAYER_BUY_TILES_WITH_TRAINING", "EFFECTPLAYER_TRAIT_HANNO_II_LEADER",
        "EFFECTCITY_FAMILYCLASS_LANDOWNERS_SEAT"}, "buy-tile unlock sources changed"
    assert [r for r in payload["constants"]["removeBorder"]] and all(
        r["id"].startswith(("IMPROVEMENT_CITY_SITE", "IMPROVEMENT_RUINS", "IMPROVEMENT_SETTLEMENT")) for r in payload["constants"]["removeBorder"])

    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    rendered = sum(1 for s in scenarios if s["render"])
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(spreaders)} spreaders, {len(BONUS_GROWTH)} growth bonuses, "
          f"{len(scenarios)} scenarios ({rendered} rendered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
