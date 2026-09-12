# Zone of control: page prose

Every piece of text on `/zone-of-control` lives here, and `src/pages/zone-of-control.astro`
reads this file at build time. Edit freely and rebuild with `python3 scripts/build_zoc.py &&
npx astro build`. The rules for this file are below.

- Each `## key` heading starts one text slot. Keep the keys, and reorder, reword or delete
  the text under them as you like. Delete the text but not the heading to blank a slot.
- Plain paragraphs, blank-line separated. Lines starting with `- ` become bullets.
  Inline markup: `**bold**`, `*emphasis*`, `` `code` ``, `[text](url)`.
- `{placeholders}` are filled from the game data at build time (lists of units, hotkeys,
  DLC names). The available ones are listed at the bottom. Anything else in braces is left
  as typed.
- Board captions are `board.<id>.caption`, one sentence that is always shown, and
  `board.<id>.note`, an optional smaller second line. The boards themselves, the quoted
  game strings, the appendix tables and the source citations are computed, so you cannot
  edit them here.

## lede

Zone of control, often shortened to ZOC, is one movement rule in the game's pathfinder. Every zone and arrow below is computed by a port of that code rather than drawn by hand.

## legend.you

your unit, with a white ring on the one moving

## legend.enemy

enemy unit

## legend.zoc

enemy zone for that unit

## legend.legal

legal step

## legend.refused

refused step

## legend.reach

reachable with unlimited moves

## legend.advance

Rout advance after a kill, which skips the zone test

## rule.heading

The rule

## rule.headline

A step is refused only when the tile you leave *and* the tile you enter are both inside an enemy zone.

## rule.body

Entering a zone costs nothing and does not stop you. Leaving a zone for a free tile is always allowed.

## rule.quote.source

In-game concept text, `{conceptLong}`

## who.heading

Who pins whom

## who.hint.exerts

Every infantry unit, whether melee or ranged and tribal or unique, and the three ships.

## who.hint.ignores-mounted

Horse, camel and chariot units, which only Polearm infantry holds.

## who.hint.neither

Elephants, siege engines, Settlers, Workers, Caravans and disciples. Civilians also never block, as described below.

## who.hint.ignores-all

Scouts carry the ignore flag without the Mounted trait, so nothing pins them.

## who.note

The Spearman tutorial says "{spearmanQuote}." That is the whole Polearm exception, because {polearmCarriers} pin Mounted units that ignore everyone else.

## movement.heading

Moving through a zone

## board.zone.caption

A land unit controls the six tiles around it.

## board.enter.caption

Stepping into the zone is free, and stepping from one controlled tile to another is refused.

## board.slip.caption

Leaving the zone is always legal, so you walk in, out and back in on the far side.

## walls.heading

Walls

## walls.intro

Dots mark every tile the search could reach with unlimited movement.

## board.wall2.caption

Every route north needs a step from one controlled tile to another, so the line holds.

## board.wall2.note

Every northward step is zone to zone.

## board.wall3.caption

One free tile between the zones is enough, because you step in, out and through.

## board.wall3.note

The drawn route is the one the search found.

## exceptions.heading

Exceptions

## board.cavalry.caption

A Horseman ignores the archer's zone but a Polearm unit still pins it.

## board.cavalry.note

Only the spearman's tiles are washed for the Horseman.

## board.elephant_pinned.caption

Elephants ignore nothing, so an archer pins a War Elephant as it would any infantry.

## board.elephant_pinned.note

Elephants and siege carry neither flag, so everyone pins them and they pin no one.

## board.elephant_pins_nothing.caption

Elephants also exert no zone, so a Spearman walks right round one.

## board.elephant_pins_nothing.note

A {mahoutDlc} general with the {mahoutName} trait is the one thing that gives an elephant a zone.

## board.river.caption

Across a river the enemy exerts nothing, but you may not cross that river straight into a zone.

## board.river.note

The dashed tile is what the in-game overlay paints anyway (see Reading the overlay).

## board.city.caption

A city tile is never inside a zone, so a pinned unit can always step home, and an enemy city projects a zone of its own.

## board.city.note

Blue is your city, and red is an enemy city with its zone.

## board.ships.caption

A ship controls the adjacent water tiles only, and the shore beside it stays free.

## board.ships.note

Land and water never share a zone.

## board.embarked.caption

A ship also pins land units crossing its water under your own ship's control.

## board.embarked.note

Land units cross water only inside an anchored ship's control and cannot end a turn on it. While afloat they are pinned by ships even with the ignore flag, and they exert nothing.

## board.hidden.caption

An archer under a Tactician leader, unseen in woods, exerts no zone at all.

## board.hidden.note

The hiding effects are a Tactician leader's ranged units in trees or jungle, Scout Stealth, and an Ambusher general's units in uncut trees or scrub.

## civilians.heading

Civilians, scouts and blocking

## civilians.body

- **They never block a path.** {nonBlocking} lack the blocking flag, so a hostile unit walks straight through their tile.
- **But nothing can stop on them.** A move may not end on a tile holding any hostile unit, blocking or not. A Worker or Scout parked on a beach lets enemies pass over it yet denies them the landing.
- **They exert no zone,** and only the two scouts ignore one.
- **On water,** {waterUnits} count as water units and may end a turn afloat. A Worker may stop on water inside its own territory, and the Caravan is amphibious. Every other land unit crosses water only through an anchored ship's control and must keep moving.
- **Afloat, only true water units keep their ignore.** A Scout under Exploration passes a ship's zone, while a Scout being ferried is pinned like a Warrior.

## board.landing.caption

You may march through an enemy Worker's tile but never stop on it, so nothing can land there.

## board.landing.note

Dots mark the tiles the move may end on. The beach tile under the Worker has no dot, and the tiles beyond it do.

## special.heading

Rout and Push

## special.body

The zone test lives in the pathfinder. Two combat abilities move units without running it, and they are how cavalry gets into and through a spear wall.

- **Rout advance.** After a kill, a unit with Rout ({routUnits}) advances into the emptied tile when another enemy can be attacked from there, and it may attack again. The advance asks only whether the tile can be occupied, and never asks about the zone. Each rout also costs the attacker 1 HP.
- **The wall still holds against spears.** Polearm units ({routImmune}) are immune to Rout, so killing one gives no advance, and every advance needs a further kill to continue.
- **Push.** Panic ({pushUnits}) shoves a surviving defender to one of the three tiles away from the attacker, chosen only by occupancy, even into another zone. The Fireship does the same on water.

## board.rout_gap.caption

Kill the unit in the gap and a Rout unit advances into it, which is a step the pathfinder would refuse. Kill again to advance again.

## board.rout_gap.note

Every tile beside the pickets is washed, so ordinary movement into the gap is refused. Two kills carry the Horseman to the far side, where a normal step out of the zone is legal. The board assumes each attack kills.

## asked.heading

Where the zone is asked, and where it is not

## asked.body

The game consults the zone in two places, which are a movement step and a swap of two friendly units. A swap is refused when both tiles are pinned. Everything else ignores the zone, as listed below.

- **No extra cost.** Entering or leaving a zone costs normal movement.
- **No stop.** Entering a zone does not end the move, and only the step from zone to zone is refused.
- **No effect on attacks,** or on the moves they cause, such as the Rout advance and the Panic push above.
- **Nothing at peace or truce.** Only war is hostile, and tribes at war count.
- **No terrain exemption.** An improvement flag exists for it, but no improvement sets it.

## overlay.heading

Reading the overlay

## overlay.body

Hold `{showKey}` to paint every tile in a hostile zone for the selected unit, and press `{lockKey}` to lock the overlay on. The game also tints the zones around each visible enemy while a unit is selected.

## overlay.callout

**The overlay overstates rivers.** The hold-{showKey} overlay tells the ZOC test to ignore river edges, and the selected-unit tint uses a variant with no river test at all, so a river-shielded tile shows red although stepping onto it is legal. The river board above draws such a tile with a dashed outline.

## play.heading

See it in play

## play.body

Two owpuzzle puzzles are built on this rule. In [The Gatekeeper](https://owpuzzle.fly.dev/#the-gatekeeper) one arrow on the watchman opens the road, and [The Two Fords](https://owpuzzle.fly.dev/#the-two-fords) is a chain of pickets across two river crossings.

## appendix.heading

Appendix

## appendix.units.heading

Every unit

## appendix.grants.heading

Grants

## appendix.grants.note

{maneuversName} is a promotion for ships only, and {mahoutName} is a general trait from {mahoutDlc}. The hiding effects that silence a zone are {hiding}.

## appendix.constants.heading

Constants

## appendix.sources.heading

Sources

---

Placeholders: `{conceptLong}` `{spearmanQuote}` `{polearmCarriers}` `{mahoutName}` `{mahoutDlc}`
`{maneuversName}` `{routUnits}` `{routImmune}` `{pushUnits}` `{nonBlocking}` `{waterUnits}`
`{hiding}` `{showKey}` `{lockKey}`.
