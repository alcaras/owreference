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
- The tables are generated from `pillage.json`, so their numbers are not in this file.

## lede

Pillaging an enemy improvement pays you a fixed amount of yields, switches the improvement off
and starts a countdown to its destruction. This page lists what every improvement pays, and how
{assyriaLink}'s **{assyriaMod}** doubles it.

## how.heading

What one pillage does

## how.body

- **Pays you.** Each yield the improvement pays is multiplied by your unit's pillage modifier and added to your stockpile, so a Farm pays {farmPay} Food. Culture goes to the pillager's nearest city instead, and is lost if the pillager has no city.
- **Switches the improvement off.** A pillaged improvement gives no yields, no specialist output and none of its other effects until it is repaired. Its luxury stops counting, and the trade network no longer runs through it.
- **Starts the clock.** Left alone, the improvement is destroyed when the countdown runs out. Most improvements get {commonTurns} turns; cathedrals get {cathedralTurns}; shrines, Estates and Slums stay pillaged forever and never disappear.
- **Costs {pillageOrders} Order, then a cooldown.** The unit can't act again this turn (the usual free-action rules apply).
- **Adds {warScore} war score** against the tile's owner. For scale: killing a unit is worth {killScore}, capturing one {captureUnitScore}, taking a city {captureCityScore}.
- **Fires events.** The owner and the pillager each get their own events; the {eventCount} story events are listed below.

## table.heading

What every improvement pays

## table.note

**Pays** is the payout for any unit. **Assyria** is the same unit under {assyriaLink}'s
{assyriaMod}. **Repair** is what the owner pays to switch the improvement back on: {repairPct}% of the
build cost, then the improvement's own repair discount if it has one, never below 1. City cost
modifiers apply before that and are not shown. **Left alone** is what happens if nobody repairs it.
Pillaging a Fort, or an improvement still under construction, destroys it outright, but it still pays.

## assyria.heading

How Assyria's bonus works

## assyria.body

Assyria's nation effect gives every unit you own {assyriaMod}, which exactly doubles every
payout: a Farm pays {farmAssyria} Food instead of {farmPay}, a Fair {fairAssyria} Money instead
of {fairPay}, a Legendary Stele {steleAssyria} Stone instead of {stelePay}.

Nothing else in the game changes the payout. Two related effects:

- **{heroLink} leader: heal while pillaging.** Every unit recovers an active heal's worth of HP on each pillage. It doesn't change the payout.
- **{stateiraName} dynasty ({stateiraNation}): {stateiraValue}% repair cost.** It makes your own repairs cheaper, on top of the improvement's own discount. It does nothing to pillage.

Razing a city harvests every improvement in its territory at the **base** payout, so Assyria gets
no bonus there.

## never.heading

What cannot be pillaged

## never.note

Wonders, tribe settlements, holy sites, the Pillar of Edicts, ruins, city sites and one event
improvement can't be pillaged. A city itself is captured, not pillaged. You also can't pillage in
friendly or neutral territory: only inside a city you are at war with, or on tiles no city owns.

## other.heading

Other ways an improvement gets pillaged

## other.body

- **Occurrences** (Wrath of Gods): a wildfire or eruption pillages every improvement it touches; the others roll a per-tile chance, listed below. No one is paid.
- **Events**: {bonusCount} event bonuses pillage a tile or every tile around one, and two repair one. Again no payout.
- **Razing**: every improvement in the razed city's territory is harvested at base payout, then cleared.
- **Burning**: a unit that could pillage can instead **Burn** the improvement for {burnTraining} Training. It pillages the tile with no payout and no cooldown. Tribes cannot burn.

## who.heading

Who can pillage

## who.body

Every land military unit can pillage except the siege line ({siegeList}). Civilians, ships and
disciples cannot. Tribal units pillage too, but only {raidersLink} do it on purpose; other tribes
pillage only when their attacks happen to leave them on an improvement.

## after.heading

What follows a pillage

## after.body

- **Family opinion.** {artisansLink} families lose {artisansValue} opinion for every pillaged tile inside their cities, for as long as it stays pillaged. No other family class cares.
- **Ambitions.** "{goalFive}" and "{goalTen}" count every improvement your units pillage.
- **Cognomens.** The same count feeds "{hunterName}" and "{scourgeName}" on the {cognomensLink} page, weighted at {cognomenWeight} each.
- **Repair.** A Worker, or any unit that could build the improvement, repairs it instantly for {repairOrders} Order plus {repairPct}% of the build cost. Only the three Aksum Steles have their own discount on top: a Legendary Stele costs {steleBuild} Stone to build and {steleRepair} to repair ({repairPct}%, then {steleOwnRepair}%). If you're short on goods, the repair button offers to buy them. Repair resets the countdown.

## ai.heading

How the AI treats it

## ai.body

- The AI never pillages an improvement that pays nothing, so Slums are safe from it.
- The AI repairs a pillaged tile sooner the less time it has left, and a tile past half its countdown becomes a Priority threat for its defenders.
- A unit in grave danger that can't wait out a pillage cooldown will Burn instead.
