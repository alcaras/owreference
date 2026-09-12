# Border Expansion — page prose

Every piece of text on `/border-expansion` lives here; `src/pages/border-expansion.astro`
reads this file at build time. Edit freely and rebuild (`npx astro build`), or edit in place:
`npm run edit`, then open `http://localhost:4321/owreference/border-expansion/?edit`. Rules:

- Each `## key` heading starts one text slot. Keep the keys; reorder, reword or delete
  the text under them as you like. Delete the text (not the heading) to blank a slot.
- Plain paragraphs, blank-line separated. Lines starting with `- ` become bullets and
  `1. ` lines a numbered list. Inline markup: `**bold**`, `*emphasis*`, `` `code` ``,
  `[text](url)` (`#section` anchors work).
- `{placeholders}` are filled from the game data at build time (counts, names, costs,
  entity links). The available ones are listed at the bottom. Anything else in braces is
  left as typed.
- Board captions are `board.<id>.caption` (one sentence, always shown) and
  `board.<id>.note` (smaller second line, optional). The boards themselves, the quoted
  game strings and the tables are computed, not editable here.
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

TL;DR

## summary.body

Tile acquisition is entirely deterministic in Old World, unlike other games. This page outlines the simple rules that the game uses to expand your borders -- whether through a Border Boost card, urban expansion, or buying tiles via the Colonies law or in a Landowner Seat.

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

1. **Resource pull.** Your borders will expand to a tile neighboring one of your tiles that has a resource when your tile doesn't have a resource.
2. **Urban pull.** Your borders will expand to an urban tile if you own an adjacent tile.
3. **Adjacent water.** If you own two tiles next to each other, both adjacent to a water tile, and both are claimable land, your borders will expand to that water tile. This also works for mountain or volcano tiles. If there's only one possible adjacent land tile and you own it, your borders will expand.
4. **Gap fill.** If your owned tiles 'flank' a tile (i.e. you have a tile on both sides of the neighboring tile), you'll gain that tile.

## board.resource.caption

Your borders only expand to the horses, since you can't 'chain' resources from another resource tile.

## board.urban.caption

Your gain everything next to the urban tiles, since urban tiles 'push' borders around them.

## board.hole.caption

Since red owns a tile on both sides of the tile, they get the tile.

## board.hole_which.caption

You own both sides of this tile. It'll go to the lower left city, because the game assigns tiles in priority order -- SE, SW, W. The lower left city owns the tile SW of this one, so it gets the tile.

## rules.water.heading

Adjacent water

## board.flank_open.caption

Getting the highlighted land tile first gets you the central water tile, since the only adjacent claimable tile to it is a land tile you own. Then the other two tiles chain off that.

## board.flank_unowned.caption

Getting the highlighted land tile only gets one tile since you don't have another tile along the coast. You get the tile you get since you have land on two sides of it.

## board.flank_ours.caption

You get the water tile because you own one of the two land tiles beside it. The other one being unowned doesn't matter.

## board.flank_enemy.caption

If there's an enemy tile, you don't get the water tile -- since you don't own the enemy tile. (It acts just like an unowned tile).

## rules.water.note

Mountains and volcanoes follow the same rules as water.

## chain.heading

Chains

## chain.intro

You can 'chain' border expansion.

## board.chain.caption

Adding a specialist on the farm ends up adding 7 tiles.

## chain.steps

1. First we grab all tiles adjacent to the specialist (the three tiles labeled 0).
2. Because the game has a resource and is adjacent to a tile we now own that doesn't have a resource, we grab it (resource pull). Same deal with the fish.
3. The game grabs the water tile east of itself, since that's the only land boundary of that water (tile 2).
4. The last water tile now lies between that tile and land you already owned: gap fill.

## founding.heading

Founding

## founding.intro

Founding works the same way -- it gets everything within 2 tiles of the Settler, then runs all the same rules.

## board.found.caption

We pick up the ore and wheat since they border tiles we own that don't have resources.

## board.minor.caption

We'd make a minor city here because we own all land tiles bordering a city site.

## founding.quote.source

In-game help text for the {minorCityName}

## founding.body

**Minor Cities.** If you surround all land tiles of a city site, you make a minor city. Minor cities are worth {minorCityVp} VP, give {minorCityOutput} and cost {minorCityUpkeep} upkeep.

## triggers.heading

What can expand borders

## triggers.after

Building an urban improvement grabs the tiles next to it, just like a specialist. And it can chain, just like another border expansion.

## buying.heading

Buying tiles

## buying.quote.source

In-game concept text, `{buyTileName}`

## buying.body

You can buy tiles with the Colonies law or in a Landowners seat.

- You need a unit on the tile. It can be a military or civilian unit.
- The tile cannot be urban.
- If the tile is water, it must touch land. Being Coastal is not enough, it must touch land.
- The tile needs to be adjacent to a tile you already own.
- The same border expansion rules run on tile buying.
- **Cost:** (base + per × (tile purchases for that city + tile purchases for any of your cities ÷ 2)) × (distance from the city + 1) ÷ 4, minimum 1, rounding down at each step. Every purchase raises both the 'tile purchases for that city' and the 'tile purchases for any of your cities' counts.

## buying.swap.heading

Swapping tiles

## buying.swap.body

- You can also swap tiles between your own cities without Colonies or a Landowners seat. The tile can't have an improvement on it, and moving it can't split the other city's territory. Swapping costs the same as buying.
- Swapping tiles between cities of the same family just has the Money cost.
- Swapping tiles between cities of different families gives {swapGain} opinion to the family gaining the tile (for {swapGainTurns} turns) and {swapLoss} to the family losing it (for {swapLossTurns} turns).

## board.buy.caption

You can buy any of the dashed tiles for the price listed. Buying the hill will also grab the cattle because of border expansion rules.

## buying.grid.heading

Cost by distance and purchases

## growth.heading

Border Boost and similar events

## growth.intro

Let's use Border Boost as an example. Border Boost grabs {borderBoostTiles} tiles. It goes through all potential tiles, scores them, and picks the highest scoring one, then grabs it, and chains from that. Then it does that again until it's grabbed all {borderBoostTiles} tiles. Note this can result in grabbing way more than {borderBoostTiles} tiles since you always get {borderBoostTiles} tiles and whatever they chain to.

## board.grow.caption

Here's an event that grabs +2 tiles.

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
- You can minor city a Tribal Site *even with units still on it* -- this will instantly turn the camp into a minor city.

## board.tribe_surrounded.caption

All land tiles surrounding the city site are yours, so you minor the city and then grab tiles around it, as if you had founded a city (grabbing tiles within 2).

---

Placeholders: `{borderBoostTiles}` `{buyTileName}` `{minorCityName}` `{minorCityOutput}` `{minorCityUpkeep}` `{minorCityVp}` `{notClaimable}` `{resourceValues}` `{swapGainTurns}` `{swapGain}` `{swapLossTurns}` `{swapLoss}` `{territoryName}`.
