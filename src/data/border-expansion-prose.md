# Border expansion: page prose

Every piece of text on `/border-expansion` lives here, and `src/pages/border-expansion.astro`
reads this file at build time. Edit freely and rebuild with `npx astro build`, or edit in place by
running `npm run edit` and opening `http://localhost:4321/owreference/border-expansion/?edit`. The
rules for this file are below.

- Each `## key` heading starts one text slot. Keep the keys, and reorder, reword or delete
  the text under them as you like. Delete the text but not the heading to blank a slot.
- Plain paragraphs, blank-line separated. Lines starting with `- ` become bullets and
  `1. ` lines a numbered list. Inline markup: `**bold**`, `*emphasis*`, `` `code` ``,
  `[text](url)` (`#section` anchors work).
- `{placeholders}` are filled from the game data at build time (counts, names, costs,
  entity links). The available ones are listed at the bottom. Anything else in braces is
  left as typed.
- Board captions are `board.<id>.caption`, one sentence that is always shown, and
  `board.<id>.note`, an optional smaller second line. The boards themselves, the quoted
  game strings and the tables are computed, so you cannot edit them here.
  Board titles stay in `scripts/build_borders.py`.

## lede

Borders in Old World are entirely deterministic, unlike in other games.

## legend.you

your territory

## legend.enemy

another player's

## legend.badge

tile acquisition order

## legend.resource

resource pull

## legend.urban

urban pull

## legend.water

adjacent water

## legend.gap

gap fill

## legend.minor

Minor City

## legend.ring

starting tile

## legend.buy

a buyable tile

## summary.heading

Summary

## summary.body

Tile acquisition is entirely deterministic in Old World, unlike other games. The page below sets out the rules the game uses to expand your borders, whether the expansion comes from a Border Boost card, from urban expansion, or from buying tiles with the Colonies law or in a Landowner Seat.

## territory.heading

Tiles

## territory.quote.source

In-game concept text, `{territoryName}`

## territory.headline

You gain a tile whenever it meets one of the rules below. Then, the rules run again to see if you gain any other tiles because of the new tile you just gained.

## rules.heading

Tile acquisition rules

## rules.intro

*Claimable land* is any tile that is not {notClaimable}. The game goes down this list, considering all your owned tiles.

## rules.list

1. **Resource pull.** Your borders expand to a tile with a resource when it neighbors one of your tiles that has no resource.
2. **Urban pull.** Your borders expand to an urban tile when you own a tile next to it.
3. **Adjacent water.** Your borders expand to a water tile when you own two claimable land tiles that sit next to each other and both touch that water tile. Mountain and volcano tiles work the same way. When the water tile has only one possible adjacent land tile and you own it, your borders expand as well.
4. **Gap fill.** You gain a tile when you already own the tiles on both sides of it.

## board.resource.caption

Your borders expand to the horses only, because one resource tile cannot pull another resource tile.

## board.urban.caption

You gain everything next to the urban tiles, because an urban tile pulls the borders around it.

## board.hole.caption

Red owns a tile on both sides of the empty tile, so red gains it.

## board.hole_which.caption

You own both sides of this tile, and it goes to the lower left city, because the game assigns tiles in the priority order SE, SW, W. The lower left city owns the tile to the SW of this one, so it gets the tile.

## rules.water.heading

Adjacent water

## board.flank_open.caption

Taking the highlighted land tile first also gives you the central water tile, because the only claimable tile next to it is a land tile you own. The other two tiles then chain off that one.

## board.flank_unowned.caption

Taking the highlighted land tile gives you one tile only, because you have no other tile along the coast. You get that tile because you own land on two sides of it.

## board.flank_ours.caption

You get the water tile because you own one of the two land tiles beside it, and it does not matter that the other one is unowned.

## board.flank_enemy.caption

You do not get the water tile when one side is an enemy tile, because you do not own it. An enemy tile acts the same as an unowned tile.

## rules.water.note

Mountains and volcanoes follow the same rules as water.

## chain.heading

Chains

## chain.intro

You can 'chain' border expansion.

## board.chain.caption

Adding a specialist on the farm ends up adding 7 tiles.

## chain.steps

1. First you take every tile next to the specialist, which are the three tiles labeled 0.
2. The game tile has a resource and sits next to a tile you now own that has none, so resource pull takes it. The fish works the same way.
3. The game takes the water tile to its east, because that is the only land boundary of that water, marked tile 2.
4. The last water tile now lies between that tile and land you already owned, so gap fill takes it.

## founding.heading

Founding

## founding.intro

Founding works the same way, because it takes everything within 2 tiles of the Settler and then runs all the same rules.

## board.found.caption

You pick up the ore and the wheat, because they border tiles you own that have no resource.

## board.minor.caption

You would make a minor city here, because you own every land tile bordering a city site.

## founding.quote.source

In-game help text for the {minorCityName}

## founding.body

**Minor Cities.** If you surround all land tiles of a city site, you make a minor city. Minor cities are worth {minorCityVp} VP, give {minorCityOutput} and cost {minorCityUpkeep} upkeep.

## triggers.heading

What can expand borders

## triggers.after

Building an urban improvement takes the tiles next to it, in the same way a specialist does, and it can chain in the same way as any other border expansion.

## buying.heading

Buying tiles

## buying.quote.source

In-game concept text, `{buyTileName}`

## buying.body

You can buy tiles with the Colonies law or in a Landowners seat, under the conditions below.

- You need a unit on the tile. It can be a military or civilian unit.
- The tile cannot be urban.
- If the tile is water, it must touch land. Being Coastal is not enough, it must touch land.
- The tile needs to be adjacent to a tile you already own.
- The same border expansion rules run on tile buying.
- **Cost:** (base + per × (tile purchases for that city + tile purchases for any of your cities ÷ 2)) × (distance from the city + 1) ÷ 4, with a minimum of 1, rounding down at each step. Every purchase raises the count of tile purchases for that city and the count for any of your cities.

## buying.swap.heading

Swapping tiles

## buying.swap.body

- You can also swap tiles between your own cities without Colonies or a Landowners seat. The tile cannot have an improvement on it, and moving it cannot split the other city's territory. Swapping costs the same as buying.
- Swapping tiles between cities of the same family costs Money only.
- Swapping tiles between cities of different families gives {swapGain} opinion to the family gaining the tile for {swapGainTurns} turns, and {swapLoss} to the family losing it for {swapLossTurns} turns.

## board.buy.caption

You can buy any of the dashed tiles for the price listed. Buying the hill will also grab the cattle because of border expansion rules.

## buying.grid.heading

Cost by distance and purchases

## growth.heading

Border Boost and similar events

## growth.intro

Border Boost is the clearest example, and it takes {borderBoostTiles} tiles. The game scores every possible tile, takes the highest scoring one, and chains from it, then repeats until it has taken all {borderBoostTiles} tiles. You can end up with far more than {borderBoostTiles} tiles, because you always get {borderBoostTiles} tiles plus everything they chain to.

## board.grow.caption

The event below takes +2 tiles.

## board.grow.note

Each tile is labeled with its score.

## growth.roll

The roll is random, but is seeded by the city tile and restarted each pick, so the tiles grabbed are always grabbed in the same order.

## growth.resources

**Resource border values.** {resourceValues}. Resources without a value score 0 but are still pulled.

## losing.heading

Losing tiles and gotchas

## losing.body

- Tiles are never removed from a city. You can lose a city, but the tiles go with the city.
- If City Razing is on, and a City is Razed, then the Tiles become unowned because the City no longer exists.
- You can take a Tribal Site as a minor city *even with units still on it*, which turns the camp into a minor city immediately.

## board.tribe_surrounded.caption

Every land tile around the city site is yours, so you take the site as a minor city and then take the tiles around it as if you had founded a city there, which reaches 2 tiles out.

---

Placeholders: `{borderBoostTiles}` `{buyTileName}` `{minorCityName}` `{minorCityOutput}` `{minorCityUpkeep}` `{minorCityVp}` `{notClaimable}` `{resourceValues}` `{swapGainTurns}` `{swapGain}` `{swapLossTurns}` `{swapLoss}` `{territoryName}`.
