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
  game strings and the appendix tables are computed, so you cannot
  edit them here.

## lede

Zone of control (ZOC) decides which moves enemy units stop you from making. This page shows the rule, which units it applies to, and how it plays out on the board.

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

Rout advance after a kill, which ignores zones

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

Every infantry unit, melee or ranged, tribal or unique, and the three ships.

## who.hint.ignores-mounted

Horse, camel and chariot units, which only Polearm infantry holds.

## who.hint.neither

Elephants, siege engines, Settlers, Workers, Caravans and disciples. Civilians also never block (see below).

## who.hint.ignores-all

Scouts ignore zones without being Mounted, so nothing pins them.

## who.note

The Spearman tutorial says "{spearmanQuote}." {polearmCarriers} pin Mounted units that ignore every other zone.

## movement.heading

Moving through a zone

## board.zone.caption

A land unit controls the six tiles around it.

## board.enter.caption

Stepping into the zone is free, but stepping from one controlled tile to another is refused.

## board.slip.caption

Leaving the zone is always legal, so you can walk in, out and back in on the far side.

## walls.heading

Walls

## walls.intro

Dots mark every tile you could reach with unlimited movement.

## board.wall2.caption

Every route north needs a step from one controlled tile to another, so the line holds.

## board.wall3.caption

One free tile between the zones is enough to get through, because you step in, out and in again.

## exceptions.heading

Exceptions

## board.cavalry.caption

A Horseman ignores the archer's zone, but a Polearm unit still pins it.

## board.elephant_pinned.caption

Elephants ignore nothing, so an archer pins a War Elephant like any infantry.

## board.elephant_pins_nothing.caption

Elephants also exert no zone, so a Spearman walks right around one.

## board.river.caption

An enemy exerts no zone across a river, but you can't cross that river straight into a zone.

## board.river.note

The dashed tile is one the in-game overlay paints red anyway (see Reading the overlay).

## board.city.caption

A city tile is never in a zone, so a pinned unit can always step into your city (blue), and an enemy city (red) projects a zone of its own.

## board.ships.caption

A ship controls only the water tiles next to it, so the shore beside it stays free.

## board.embarked.caption

A ship also pins land units crossing water under your own ship's control.

## board.hidden.caption

An archer hidden in woods under a Tactician leader exerts no zone at all.

## civilians.heading

Civilians, scouts and blocking

## civilians.body

- **They never block a path.** {nonBlocking} don't block, so an enemy unit walks straight through their tile.
- **But nothing can stop on them.** A move can't end on a tile holding any enemy unit. A Worker or Scout parked on a beach lets enemies pass over it but stops them landing there.
- **They exert no zone,** and only the two scouts ignore one.
- **On water,** {waterUnits} count as water units and can end a turn afloat. A Worker can stop on water inside your own territory, and the Caravan is amphibious. Every other land unit crosses water only under an anchored ship's control and must keep moving.
- **Afloat, only true water units still ignore zones.** A Scout under Exploration passes a ship's zone, but a Scout being ferried is pinned like a Warrior.

## board.landing.caption

You can march through an enemy Worker's tile but never stop on it, so nothing can land there.

## board.landing.note

Dots mark where the move can end; the Worker's beach has none.

## special.heading

Rout and Push

## special.body

Two combat abilities move units without checking zones, and they are how cavalry gets into and through a spear wall.

- **Rout advance.** After a kill, a unit with Rout ({routUnits}) advances into the emptied tile when it can attack another enemy from there, and it can attack again. Zones don't stop the advance. Each rout costs the attacker 1 HP.
- **The wall still holds against spears.** Polearm units ({routImmune}) are immune to Rout, so killing one gives no advance. Each further advance needs another kill.
- **Push.** Panic ({pushUnits}) shoves a surviving defender to one of the three tiles away from the attacker, even into another zone. The Fireship does the same on water.

## board.rout_gap.caption

Kill the unit in the gap and a Rout unit advances into it, a step normal movement would refuse; kill again to advance again.

## board.rout_gap.note

The board assumes each attack kills.

## asked.heading

What zones don't affect

## asked.body

Zones matter for two things: moving one step, and swapping two of your units. A swap is refused when both tiles are in a zone. Zones don't affect:

- **Attacks,** or the moves they cause, such as the Rout advance and the Panic push above.
- **Peace or truce.** Only war counts, including war with tribes.

## overlay.heading

Reading the overlay

## overlay.body

Hold `{showKey}` to show every tile in an enemy zone for the selected unit, and press `{lockKey}` to lock the overlay on. The game also tints the zones around each visible enemy while a unit is selected.

## overlay.callout

**The overlay overstates rivers.** Both overlays ignore rivers, so a tile across a river from an enemy shows red although you can step onto it. The river board above draws such a tile with a dashed outline.

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

{maneuversName} is a promotion for ships only. {mahoutName} is a general trait from {mahoutDlc}, and the one thing that gives an elephant a zone. The effects that hide a unit and silence its zone are {hiding}.

## appendix.constants.heading

Constants

---

Placeholders: `{conceptLong}` `{spearmanQuote}` `{polearmCarriers}` `{mahoutName}` `{mahoutDlc}`
`{maneuversName}` `{routUnits}` `{routImmune}` `{pushUnits}` `{nonBlocking}` `{waterUnits}`
`{hiding}` `{showKey}` `{lockKey}`.
