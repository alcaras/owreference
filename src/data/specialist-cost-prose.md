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
- The tables and lists are generated from `specialist_cost.json`, so their numbers, headers
  and list items are not in this file.

## lede

Specialist pages list a base price of {base1} Civics, but that is only what a city's first
specialist costs. Every specialist a city trains makes the next one in **that same city** cost
{perProduced}% of the base more, for the rest of the game.

## formula.heading

The cost of the next specialist

## formula.note

- **base** is the {civicsLink} price on {ruralLink} and {urbanLink}: {base1} for every rural specialist and every Apprentice, {base2} for a Master, {base3} for an Elder.
- **n** is how many specialists this city has produced. Each city keeps its own count, so a new city starts again at the base price.
- **city modifiers** are the percentages in the table further down, added together. A {landownersName} family takes {landownersValue}% off rural specialists, so a Landowners city with four specialists behind it pays less than the base price.
- The result is rounded down and never drops below 1 Civics.

## ramp.heading

What the count does to the price

## ramp.note

Find the row for the number of specialists the city has already produced. The columns are the
three base prices, without city modifiers. The count keeps going past {rampMax}: each further
specialist adds another {perProduced}% of the base.

## counts.heading

What adds to the count

## counts.note

The count only ever goes up.

## ignores.heading

What doesn't

## ignores.note

A free specialist still works its tile and pays yields. It just doesn't raise the price of the
city's next one.

## modifiers.heading

City modifiers

## modifiers.note

These add to the count's percentage. The Civics rows change the build price; the Food rows
change the up-front Food price instead, which the count never touches. Nothing here changes the
Citizen: an urban specialist takes one Citizen from the city, and only when the tile has no
specialist to upgrade.

## example.heading

A worked example

## example.body

A city that has produced six specialists wants a Master Scribe, a {base2} Civics specialist. It
is a {landownersName} city, which doesn't help because a Scribe is urban. The modifier total is
{exampleModifier}%, so the price is {base2} × {exampleMultiplier} = {exampleCost} Civics. The
same Master Scribe in a new city costs {base2}.
