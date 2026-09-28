# Family envy and the city split: page prose

Every editable line of `/family-envy` lives here, and `src/pages/family-envy.astro` reads
this file at build time. You can edit in place with `npm run edit` and
http://localhost:4321/owreference/family-envy/?edit, where ⌘S saves back into this file, or
you can edit the text below by hand and rebuild.

- Each `## key` heading is one text slot. Keep the keys; reword or delete the text under them.
- Plain paragraphs, blank-line separated. Lines starting with `- ` become bullets.
  Inline markup: `**bold**`, `*emphasis*`, `` `code` ``, `[text](url)`.
- `{placeholders}` are filled from the game data at build time and listed at the bottom.
  They render as locked chips in the editor.
- Some text is not in this file. The calculator's own labels (headings with live numbers,
  table headers, tooltips and the "N of M splits" line) and the bracket list are generated
  from opinion.json.

## lede

Three {opinionLink} terms depend only on how many cities each family holds: {mostCities}, {fewestCities} and {envyName}. Pick your families and your city total below to rank every split, starting with the one that upsets your families least.

## rung.note

Splits are ranked by their *unhappiest* family first, then by the total across all families. If you favour a family, the table shows one row per city count it could hold and marks the *recommended* row: the most cities you can give it before another family drops into Angry. Click a row to see the breakdown.

## envy.heading

How {envyName} grows

## envy.body

The penalty is `triangle(lead − yours − 1) × {envyStep}`, where *lead* is the most cities any one family holds. Being one city behind is free, and after that each further city costs more than the one before.

## ties.heading

How ties are handled

## ties.body

{mostCities} and {fewestCities} are each split between the families tied at that end, rounded toward zero. When *every* family is tied, neither applies, so an even split pays nothing to anyone.

## code.heading

How each term works

## code.most.heading

{mostCities}

## code.most.body

- Any family with **at least as many** cities as every other family gets it, so a family tied for the lead still qualifies.
- It pays +{mostValue} plus the class's own bonus, divided by the number of families tied at the top.
- Nothing is paid when **all** families are tied. A young empire where every family holds one city collects at neither end.

## code.fewest.heading

{fewestCities}

## code.fewest.body

- It charges {fewestValue} to any family with **no more** cities than every other family, split across everyone tied at the bottom.
- A family with **zero** cities still counts. Losing its last city leaves it at the bottom of the table, not out of it.

## code.envy.heading

{envyName}

## code.envy.body

- Each family is compared to the **largest** family, not the average, so one oversized family angers the other two at once.
- One city behind is free, which is why a 4/3/3 split is so much cheaper than 4/4/1.
- The cost grows on a triangle: two cities behind is {envy2}, three is {envy3}, four is {envy4} and five is {envy5}.
- Ties and family class don't change it, so every family reads the same ladder.

## code.class.heading

Family class modifiers

## code.class.body

- **{landownersLink}** are the only class that changes these terms. They add +{landownersMost} and {landownersFewest}, which **doubles** both ends to {landownersTop} at the top and {landownersBottom} at the bottom. {envyName} is unchanged.
- **{championsLink}** have the same mechanic for *units*: {championsLargest} for the largest military and {championsSmallest} for the smallest. There a tie pays nothing at all instead of being split.
- Every other class uses the base values.

## code.brackets.heading

Which bracket each family lands in

## code.reading.heading

How to read the result

## code.reading.body

- The city terms are only part of family opinion. Leader traits, council seats, laws, luxuries, wonders, religion and memories all add to the same number, so the bracket shown here is what the cities alone would earn.
- Opinion is recomputed, not accumulated, so **giving a city away fixes it immediately**. There is no decay to wait out.
- When you found a city, its tooltip shows each family's {envyName}, {mostCities} and {fewestCities} before and after.
- Families also like their own cities **close together**; Traders are the one class that wants them far apart. That distance term is only ever a bonus, and the calculator doesn't model it.

## fine

See {familiesLink} for the rest of each class's opinion modifiers, and {opinionLink} for the bracket effects in full.

---

Placeholders: `{mostCities}` `{fewestCities}` `{envyName}` `{mostValue}` `{fewestValue}` `{envyStep}`
`{envy2}` `{envy3}` `{envy4}` `{envy5}` `{landownersLink}` `{landownersMost}`
`{landownersFewest}` `{landownersTop}` `{landownersBottom}` `{championsLink}` `{championsLargest}`
`{championsSmallest}` `{opinionLink}` `{familiesLink}`.
