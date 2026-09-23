# Pillage: page prose

Every editable line of `/pillage` lives here, and `src/pages/pillage.astro` reads this
file at build time. You can edit in place with `npm run edit` and
http://localhost:4321/owreference/pillage/?edit, where ⌘S saves back into this file, or
you can edit the text below by hand and rebuild.

- Each `## key` heading is one text slot. Keep the keys; reword or delete the text under them.
- Plain paragraphs, blank-line separated. Lines starting with `- ` become bullets.
  Inline markup: `**bold**`, `*emphasis*`, `` `code` ``, `[text](url)`.
- `{placeholders}` are filled from the game data at build time and listed at the bottom.
  They render as locked chips in the editor.
- The tables are generated from `pillage.json`, so their numbers and the source citations
  are not in this file.

## lede

Pillaging is a one-Order action for any land military unit standing on an enemy improvement.
It pays the pillager a fixed lump of yields set on the improvement, switches the improvement
off until a Worker repairs it, and starts a countdown to the improvement being destroyed. The
payout is the improvement's own `aiYieldPillage` value times any pillage modifier the unit
carries, and the only pillage modifier in the game is {assyriaLink}'s **{assyriaMod}**, which
exactly doubles every number in the table below.

## how.heading

What one pillage does

## how.body

- **Pays the pillager.** Each yield on the improvement's `aiYieldPillage` list is multiplied by the unit's pillage modifier and added to your stockpile. The values are whole yields, not tenths, so a Farm really pays {farmPay} Food. Culture is the one non-global yield here: it goes to the pillager's nearest city, and if the pillager has no city it is lost.
- **Switches the improvement off.** A pillaged improvement gives no yields, no specialist output and none of its other effects until it is repaired. Luxuries stop counting, and the trade network is recomputed without it.
- **Starts the clock.** The improvement's `iPillageTurns` becomes a countdown that ticks every turn. At zero the improvement is destroyed. Most improvements get {commonTurns} turns; cathedrals get {cathedralTurns}; shrines, Estates and Slums stay pillaged forever and never disappear.
- **Costs {pillageOrders} Order, then a cooldown.** The unit gets the Pillaged cooldown, so it cannot act again this turn (the usual free-action rules apply).
- **Adds {warScore} war score** against the tile's owner. For scale: killing a unit is worth {killScore}, capturing one {captureUnitScore}, taking a city {captureCityScore}.
- **Fires events.** The owner sees a "pillaged by an enemy" or "pillaged by a tribe" trigger and the pillager a "we pillaged" trigger; {eventCount} story events hang off the three.

## table.heading

What every improvement pays

## table.note

**Pays** is the base payout for any unit. **Assyria** is the same unit under {assyriaLink}'s
{assyriaMod}. **Repair** is what the owner pays to switch the improvement back on: {repairPct}% of the
build cost (the global `IMPROVEMENT_REPAIR_MODIFIER`), then the improvement's own
`iRepairModifier` if it has one, never below 1. City cost modifiers apply before that and are
not shown. **Left alone** is what happens if nobody repairs it.
A Fort has `bRemovePillage`, so pillaging it destroys it outright, but it still pays. An
improvement that is still under construction is wiped by a pillage, and also still pays.

## assyria.heading

How Assyria's bonus works

## assyria.body

Assyria's nation effect attaches `EFFECTUNIT_ASSYRIA` to every unit the player owns, and that
effect unit carries `iPillageYieldModifier` = {assyriaMod}. `Unit.pillageModifier()` sums that
field over every effect unit on the pillaging unit, and `getPillageYield` runs each payout
through `Utils.modify(value, modifier)`, which is `value × (100 + modifier) ÷ 100` in integer
math. At +100 that is an exact ×2: a Farm pays {farmAssyria} Food instead of {farmPay}, a Fair
{fairAssyria} Money instead of {fairPay}, a Legendary Stele {steleAssyria} Stone instead of
{stelePay}.

Nothing else in the game touches that field. No promotion, law, tech, trait or wonder sets
`iPillageYieldModifier`, so the modifier column is always either 0 or +100. Two neighbouring
effects exist and are worth knowing:

- **{heroLink} leader: heal while pillaging.** `EFFECTUNIT_HERO_ALL` (from the Hero archetype's leader effect) sets `bHealPillage`, so every unit recovers an active heal's worth of HP on each pillage. It does not change the payout.
- **{stateiraName} dynasty ({stateiraNation}): {stateiraValue}% repair cost.** The only player-level `iRepairModifier` in the game, applied after the improvement's own. It makes your own repairs cheaper; it does nothing to pillage.

Razing a city harvests every improvement in its territory at the **base** payout with no
modifier applied: `Game.razeCity` reads `aiYieldPillage` directly instead of going through
the unit, so Assyria gets no bonus there.

## never.heading

What cannot be pillaged

## never.note

`Game.canPillageTile` refuses any improvement whose `iPillageTurns` is 0. That is every
wonder, every tribe settlement, the holy sites, the Pillar of Edicts, ruins and city sites,
and one event improvement. A city itself is captured, not pillaged. Being in friendly or
neutral territory also blocks it: you can only pillage inside a city you are at war with, or
on tiles no city owns.

## other.heading

Other ways an improvement gets pillaged

## other.body

- **Occurrences** (Wrath of Gods): a wildfire or eruption pillages every improvement it touches; the others roll a per-tile chance, listed below. No one is paid.
- **Events**: {bonusCount} event bonuses pillage a tile or every tile around one, and two repair one. Again no payout.
- **Razing**: every improvement in the razed city's territory is harvested at base payout, then cleared.
- **Burning**: a unit that could pillage can instead **Burn** the improvement for {burnTraining} Training. It pillages the tile with no payout and, unlike pillage, applies no cooldown. Tribes cannot burn.

## who.heading

Who can pillage

## who.body

Every land military unit has `bPillage`; the only combat units without it are the siege line
({siegeList}). Civilians, ships and disciples cannot. Tribal units pillage too, and a tribe's
`iPillagePriority` decides how eagerly its AI does: only {raidersLink} have a non-zero
priority, so Raiders pillage on purpose and the other tribes only when their attack AI happens
to stand on an improvement.

## after.heading

What follows a pillage

## after.body

- **Family opinion.** {artisansLink} families lose {artisansValue} opinion for every pillaged tile inside their cities, for as long as it stays pillaged. No other family class cares.
- **Ambitions.** "{goalFive}" and "{goalTen}" count the `STAT_IMPROVEMENT_PILLAGED` lifetime stat, which every pillage by one of your units increments.
- **Cognomens.** The same stat feeds "{hunterName}" and "{scourgeName}" on the {cognomensLink} page, weighted at {cognomenWeight} each.
- **Repair.** A Worker (or any unit that could build the improvement) repairs it instantly for {repairOrders} Order plus {repairPct}% of the build cost, times the improvement's own `iRepairModifier`. Only the three Aksum Steles set one: a Legendary Stele costs {steleBuild} Stone to build and {steleRepair} to repair ({repairPct}% then {steleOwnRepair}%). If the owner is short on goods, the repair button offers to buy them. Repair resets the countdown.

## ai.heading

How the AI treats it

## ai.body

- The AI never pillages an improvement whose payout list is empty (`PlayerAI` and `UnitAI` both check `maiYieldPillage.Count == 0`), so Slums are safe from it.
- Its repair priority scales a pillaged tile's value by `iPillageTurns ÷ turns left`, and a tile past half its countdown becomes a Priority threat for its defenders.
- A unit in grave danger that cannot afford to wait for a pillage cooldown will Burn instead.

## code.heading

Where this comes from

## code.body

Every number on this page is read from `improvement.xml` (`aiYieldPillage`, `iPillageTurns`,
`bRemovePillage`, `aiYieldCost`), `effectUnit.xml` (`iPillageYieldModifier`, `bHealPillage`,
`bPillage`), `effectPlayer.xml` (`iRepairModifier`), `yield.xml` (`iBurnCost`, `bGlobal`),
`globalsInt.xml` (`UNIT_PILLAGE_COST`, `UNIT_REPAIR_COST`), `occurrence.xml`, `familyClass.xml`
and `tribe.xml`. The rules come from the game code cited in the list beside this text, and
`verify_source_constants.py` watches those functions for drift each patch.
