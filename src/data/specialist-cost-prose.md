# Specialist cost: page prose

Every editable line of `/specialist-cost` lives here, and `src/pages/specialist-cost.astro`
reads this file at build time. You can edit in place with `npm run edit` and
http://localhost:4321/owreference/specialist-cost/?edit, where ⌘S saves back into this file,
or you can edit the text below by hand and rebuild.

- Each `## key` heading is one text slot. Keep the keys; reword or delete the text under them.
- Plain paragraphs, blank-line separated. Lines starting with `- ` become bullets.
  Inline markup: `**bold**`, `*emphasis*`, `` `code` ``, `[text](url)`.
- `{placeholders}` are filled from the game data at build time and listed at the bottom.
  They render as locked chips in the editor.
- The tables are generated from `specialist_cost.json`, so their numbers, headers and the
  source citations under "What the count includes" are not in this file.

## lede

Specialist pages list a base price of {base1} Civics, and that is only the price of the first
one. Every specialist a city trains makes the next specialist in **that same city** cost
{perProduced}% more of its base, for good. The count is per city, so a second city starts again
at the base price, and nothing you do later brings the count back down. Free specialists from
events and wonders are the exception: they arrive without adding to the count.

## formula.heading

The cost of the next specialist

## formula.note

- **base** is the {civicsLink} price on {ruralLink} and {urbanLink}: {base1} for every rural specialist and every Apprentice, {base2} for a Master, {base3} for an Elder.
- **n** is how many specialists this city has produced. Look at the city, not the empire.
- **city modifiers** are the percentages in the table further down, added together before the multiply. A {landownersName} family takes {landownersValue}% off rural specialists, so a Landowners city with four specialists behind it pays less than the base price.
- The multiply truncates and the result never drops below 1 Civics.

## ramp.heading

What the count does to the price

## ramp.note

Read the row for the number of specialists the city has already produced. The columns are the
three base prices, with no city modifiers applied. The count keeps going up, so the table just
stops at {rampMax}: each further specialist adds another {perProduced}% of the base.

## counts.heading

What the count includes

## counts.note

The count is `City.getSpecialistProducedCount()`, and it only ever goes up. Each line cites the
game code it comes from.

## ignores.heading

What the count ignores

## ignores.note

A free specialist is still a specialist on the tile, working and paying yields. It just never
touched the build queue, so the city's price for the next one is unchanged.

## modifiers.heading

City modifiers

## modifiers.note

These stack with the count inside the same multiply. The Civics rows move the build price; the
Food rows move the up-front Food price instead, which the count never touches. Nothing here
moves the Citizen: an urban specialist takes exactly one Citizen from the city, and only when
the tile has no specialist to upgrade, so a percentage never applies to it.

## example.heading

A worked example

## example.body

A city with six specialists already produced wants a Master Scribe, a {base2} Civics specialist,
and it holds a {landownersName} seat, which does not help because a Scribe is urban. The
modifier total is {exampleModifier}%, so the price is {base2} × {exampleMultiplier} =
{exampleCost} Civics. Train the same Master Scribe in a new city instead and it costs {base2}.

## code.heading

Where this comes from

## code.body

{perProduced}% is `SPECIALIST_COST_PRODUCED_MODIFIER` in `globalsInt.xml`, and the multiply is
`Player.getSpecialistBuildCost` in `Player.cs`, through `Utils.modify`, which is integer
truncation. The separate Food price is `Player.getSpecialistYieldCost`. The count itself is a
field on the city, `City.miSpecialistProducedCount`, written in only two places, so the list of
what it ignores is a list of everything else that can put a specialist on a tile.

`scripts/verify_source_constants.py` watches both cost functions, so a patch that changes the
formula is flagged instead of quietly making this page wrong.
