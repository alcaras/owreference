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
  game strings, the tables and the source citations are computed, not editable here.
  Board titles stay in `scripts/build_borders.py`.

## lede

City Territory is built by one engine in the game's tile code. Every coloured tile and every number below was computed by a port of that engine, not drawn by hand.

## legend.you

your Territory

## legend.enemy

another player's

## legend.badge

tile taken on this board; the number counts the steps from the trigger (0 = inside the trigger's own range)

## legend.resource

resource pull

## legend.urban

urban pull

## legend.water

shielded water

## legend.gap

gap fill

## legend.minor

Minor City

## legend.ring

the tile the board ran the rules from (no ring: the whole end-of-turn pass)

## legend.buy

can be bought, label = cost

## summary.heading

If you only read one paragraph

## summary.body

Your border does not creep outward by itself. Land joins your Territory only within range of something you do: founding a city takes everything within 2 tiles, a specialist or an urban improvement takes its neighbours, a bought tile takes itself, and a border growth card picks tiles for you. Two things join by themselves at the end of each turn: a resource next to your land, and water or a mountain beside your land, unless all other land around it is nobody's or someone else's. Build toward resources and coastlines. A tile boxed in between two of your tiles on opposite sides fills in too. A City Site you completely surround on land becomes your Minor City: nobody can found a city there again, and its land is yours. Tribal settlements count too (see [Losing tiles and gotchas](#losing)). Tiles never leave your Territory unless a city is captured or razed.

## territory.heading

What Territory is

## territory.quote.source

In-game concept text, `{territoryName}`

## territory.headline

A tile joins your Territory only inside a trigger's range, or when one of four rules fires on it from a tile you already own. Every tile taken runs the rules again.

## territory.body

At the end of every turn the game runs the four rules from every owned tile, so a resource or shielded water beside your border joins by itself. Reaching further takes a trigger with a range: founding, a specialist, an urban improvement, a bought tile or a growth bonus.

## rules.heading

The four spread rules

## rules.intro

*Claimable land* is any tile that is not {notClaimable}. For an owned tile T and an unowned neighbour N, tested in this order; the first rule that fires takes N.

## rules.list

1. **Resource pull.** N has a resource and T has none.
2. **Urban pull.** T or N is urban, and N is not connected to another live City Site.
3. **Shielded water.** T is claimable land and N is not: water, a mountain or a volcano. The two tiles that touch both T and N are the *side tiles*; a side tile that is not claimable land itself is ignored. N is taken if a side tile is yours, or if both side tiles are ignored. A side tile that is unowned or someone else's refuses N unless the other side tile is yours. Yours includes an ally's tile and a tile taken earlier in the same pass.
4. **Gap fill.** N is not urban, and the same team owns the tiles on two opposite sides of it.

## board.resource.caption

Only the horses join: the wheat touches only the marble tile and the sheep only the horse tile.

## board.resource.note

A tile pulls a neighbouring resource only when it has no resource of its own, and nothing pulls at range 2.

## board.urban.caption

The two urban tiles take their whole ring; your plain tiles on the other side take nothing.

## board.urban.note

Urban tiles pull every neighbour, resource or not. A city tile is urban, which is why a city's ring is always its own.

## board.hole.caption

The gap between two enemy tiles is filled for the enemy, although it touches your land too.

## board.hole.note

Gap fill looks only at the two tiles either side of the gap, on any of its three axes. Whose land is nearby otherwise does not matter.

## board.hole_which.caption

Both cities are yours; the gap goes to the lower-left city although the upper-right one touches it on two sides.

## board.hole_which.note

The game tries the axes NW–SE, NE–SW, E–W and gives the gap to the city on the second-named side of the first axis that matches. It counts each city's tiles around the gap but compares teams, so that count never decides.

## rules.water.heading

Shielded water, four ways

## board.flank_open.caption

Both side tiles are water, so they are ignored and the water is yours; the two side tiles then join the same way, each with your land and the new water beside it.

## board.flank_open.note

Side tiles that are themselves water are ignored, so nothing speaks against taking it.

## board.flank_unowned.caption

One unowned side tile refuses the water; the other side tile is water and is ignored.

## board.flank_unowned.note

Unowned land counts as not yours. Your own tile plus an unowned side tile is not enough; a side tile itself must be yours.

## board.flank_ours.caption

Own one side tile and the water is yours, whatever the other side tile is.

## board.flank_enemy.caption

An enemy side tile refuses the water exactly like an unowned one.

## rules.water.note

Mountains and volcanoes follow the same rule as water (asserted). An owned water tile spreads to nothing on its own.

## chain.heading

Chains

## chain.intro

Every tile taken is queued and the rules run from it in turn, all in one pass. One specialist reaches {chainGens} steps here and adds {chainGrabs} tiles, {chainWater} of them water.

## board.chain.caption

One specialist on the farm ends up adding seven tiles, three of them water.

## board.chain.note

Badge 0 is the specialist's range; each later number is a rule firing from a tile taken the step before.

## chain.steps

1. Range 1 takes the three unowned neighbours of the farm (0).
2. The northern one has no resource, so it pulls the game and the fish (1).
3. The game tile takes the water east of it: its side tiles are the fish and more water, and water never counts against a grab (2).
4. The last water tile now lies between that water and land you already owned: gap fill (2).
5. Water is not claimable land, so the chain stops there.

## founding.heading

Founding

## founding.intro

Founding takes every tile within 2 of the Settler, then the chain runs: urban tiles at distance 2 pull their ring at distance 3, and the end-of-turn pass follows.

## board.found.caption

Founding takes everything within 2 of the Settler, and the urban tiles at that edge pull one ring further.

## board.found.note

{foundRing} tiles came from urban pull and {foundResources} from resource pull; the end-of-turn pass added nothing here.

## board.minor.caption

The City Site next door is boxed in by the new city's land, so it becomes a Minor City and everything within 2 of it joins the new city.

## board.minor.note

{minorSiteGrabs} urban tiles of the site and everything within 2 of it joined in the same pass. Water and mountains count as closed sides; one unowned passable land tile beside the site would have kept it free (asserted).

## founding.quote.source

In-game help text for the {minorCityName}

## founding.body

**Minor Cities.** A City Site stays live until a city is founded on it. When every passable land tile around a live site's urban cluster is owned, the next pass swallows it: its urban tiles and everything within 2 of it go to the owner with the most tiles around it, ties to the nearest city. The site is marked used and gets the {minorCityName} improvement and a name; nobody can found a city there again, and its land is simply part of the neighbouring city. The improvement is urban and pays {minorCityOutput} and {minorCityVp} victory points for {minorCityUpkeep} upkeep. The help text says sites without a tribal settlement, but the code has no tribe test (board under Losing tiles). If the owning city is razed, its Minor Cities and its own tile become live City Sites again, unless the razing event wipes sites.

## triggers.heading

Triggers

## triggers.note

Range 0 means the rules run from the tile itself.

## triggers.after

An urban improvement spreads before its tile turns urban, so its grab is the plain range-1 ring, not an urban pull. A fourth spread path in the same check (free specialists from adjacent improvements) reads a list that is empty in the current data.

## buying.heading

Buying tiles

## buying.quote.source

In-game concept text, `{buyTileName}`

## buying.body

- **Eligible:** your unit stands on the tile; it touches the buying city's Territory, is not urban, and water must touch land. Costs {buyTileCost} order.
- **Unlocks:** {buyUnlocksPlayer} (every city); {buyUnlocksCity} (that city only). A unit effect exists in the code but no unit carries it.
- **From your own city:** a tile of another of your cities moves over with no unlock if it has no improvement and the move does not split that city's Territory. Both purchase counters still go up.
- **Cost:** (base + per × (tile purchases in that city + tile purchases in any of your cities ÷ 2)) × (distance from the city + 1) ÷ 4, minimum 1, rounding down at each step. Every purchase raises both counts, so the buying city pays 1½ per tile it bought and ½ per tile any other city bought. {moneyName} base {moneyBase} per {moneyPer}; {trainingName} base {trainingBase} per {trainingPer}.
- **The rules run** from a newly bought tile at range 0, so a resource behind it comes free; a tile moved between your cities spreads nothing.

## board.buy.caption

Dashed tiles can be bought, the label is the Money cost; buying the hill pulls the cattle behind it for free.

## board.buy.note

The Worker bought the hill for {buyBoardCost} {moneyName} and the cattle joined by resource pull. Both counters went up, so the next tile from this city costs more.

## buying.grid.heading

Cost by distance and purchases

## buying.grid.note

“Bought” is tile purchases in that city plus half of tile purchases in any of your cities, that city's included, rounded down.

## growth.heading

Growth bonuses

## growth.intro

A growth bonus of *n* picks one tile *n* times: the highest-scoring claimable tile that touches the city's connected Territory, is not on or beside an urban tile and is not on the map edge. The rules then run from it at range 0.

## board.grow.caption

Two picks: each takes the best-scoring claimable tile beside the city's land, then the rules run from it.

## board.grow.note

Scores shown with the roll fixed at {growRoll} for every candidate. The trees at {growWinner} beat the lush river tile at {growRunnerUp}; the water beyond joined as shielded water, then the second pick took the river tile.

## growth.roll

**The roll** comes from a random stream seeded by the city tile and restarted for every pick, so a city always rolls the same numbers in the same candidate order; the board fixes the roll so the rest of the score shows.

## losing.heading

Losing tiles and gotchas

## losing.body

- **Territory never shrinks by itself:** a tile leaves you only by capture, razing, or moving it to another of your cities.
- **Your city is captured** → all its tiles change hands at once; the end-of-turn pass then runs for the new owner.
- **A city is razed** → its tiles become unowned and their improvements are cleared; its Minor Cities and its own tile become live City Sites again.
- **You own every passable land tile around a tribal {tribeSettlements}** → at the end of the turn it becomes your Minor City and the settlement is removed. Its units stay unless the tribe is under truce with you, in which case they are pushed to the nearest tile they may stand on.
- **Your border swallows a site still showing a City Site marker or ruins ({ruins})** → the marker is removed and the Minor City placed.
- **Another live City Site touches your border** → its urban tiles are taken only by the surround above; a tribal site blocks the urban pull even for an ally.
- **A tile is on the map edge** → it never becomes Territory; rules, ranges and growth picks all skip it.
- **A growth bonus never picks** a tile on or beside an urban tile; only a chain reaches those.
- **{territoryOnlyCount} of {improvementCount} improvements** need Territory; {territoryWaterUnits} may end a move on your own water.

## board.tribe_surrounded.caption

Every passable land tile around the Outpost is yours, so at the end of the turn the Outpost becomes your Minor City and everything within 2 of it joins your city.

## board.tribe_surrounded.note

Red badge: the site itself. Gold badges: everything within 2 of it, taken in the same pass.

## appendix.heading

Appendix

## appendix.spreaders.heading

Improvements that spread borders

## appendix.spreaders.note

All {wonderCount} wonders, all Holy Sites and the {harbor} carry the Spreads Borders flag; {urbanCount} improvements spread because they are urban.

## appendix.growth.heading

Every growth value

## appendix.resources.heading

Resource border values

## appendix.resources.note

{resourceValues}. Resources without a value score 0 but are still pulled; a resource with a negative value would not be (none has one).

## appendix.constants.heading

Constants

## appendix.sources.heading

Sources

---

Placeholders: `{buyBoardCost}` `{buyTileCost}` `{buyTileName}` `{buyUnlocksCity}` `{buyUnlocksPlayer}` `{chainGens}` `{chainGrabs}` `{chainWater}` `{foundResources}` `{foundRing}` `{growRoll}` `{growRunnerUp}` `{growWinner}` `{harbor}` `{improvementCount}` `{minorCityName}` `{minorCityOutput}` `{minorCityUpkeep}` `{minorCityVp}` `{minorSiteGrabs}` `{moneyBase}` `{moneyName}` `{moneyPer}` `{notClaimable}` `{resourceValues}` `{ruins}` `{territoryName}` `{territoryOnlyCount}` `{territoryWaterUnits}` `{trainingBase}` `{trainingName}` `{trainingPer}` `{tribeSettlements}` `{urbanCount}` `{wonderCount}`.
