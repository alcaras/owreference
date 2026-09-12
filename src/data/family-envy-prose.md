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

Three {opinionLink} terms depend only on how many cities each family holds. **{mostCities}** pays +{mostValue}, shared by the families tied at the top, and **{fewestCities}** charges {fewestValue}, shared by the families tied at the bottom. **{envyName}** costs nothing until a family is two cities behind the leader, after which the penalty grows on a triangular scale in steps of {envyStep}, and **{landownersName}** feel both ends {landownersMost} harder. Pick your families and your city total below to rank every split, starting with the one that upsets your families least.

## rung.note

Splits are ranked by their *unhappiest* family first, and ties are broken by the sum across all families. When you favour a family, the table lists one row per city count that family could hold, and it marks the *recommended* row, which is the most cities you can give it before another family drops into Angry. Click a row to see the breakdown.

## envy.heading

How {envyName} grows

## envy.body

The formula is `triangle(lead − yours − 1) × {envyStep}`, where *lead* is the most cities any one family holds. Being one city behind is free, and after that each further city costs more than the one before it.

## ties.heading

How ties are handled

## ties.body

{mostCities} and {fewestCities} are each divided by the number of families tied at that end, truncating toward zero. When *every* family is tied, neither term applies at all, which is why a perfectly even split pays nothing to anyone instead of paying something to everyone.

## code.heading

What the code does

## code.most.heading

{mostCities}

## code.most.body

- The award goes to any family holding **at least as many** cities as every other family, so a family that only ties for the lead still qualifies.
- The amount is `({mostValue} + the class's own bonus) ÷ families tied at the top`, using C# integer division.
- Nothing is paid when **all** families are tied. A young empire where every family holds one city collects at neither end, and a game with a single family pays nothing either.

## code.fewest.heading

{fewestCities}

## code.fewest.body

- The penalty is charged to any family holding **no more** cities than every other family, and it is split across everyone tied at the bottom.
- Both ends can land on the same family only when the split is even, and an even split cancels both, so in practice no family takes both.
- A family with **zero** cities still counts. Losing its last city to a rival leaves the family at the bottom of the table rather than out of it.

## code.envy.heading

{envyName}

## code.envy.body

- The term compares every family against the **largest** family rather than against the average, so one oversized family angers the other two at the same time.
- A family with `(yours + 1) ≥ lead` pays nothing, and the free first city of the gap is what makes a 4/3/3 split so much cheaper than 4/4/1.
- The cost is triangular rather than linear, so two cities behind is {envy2}, three is {envy3}, four is {envy4} and five is {envy5}. The fifth city of a gap costs as much as the first four together.
- The term has no tie handling and no class modifier, so every family reads the same ladder.

## code.class.heading

Family class modifiers

## code.class.body

- **{landownersLink}** are the only class that changes these terms. They add `iMostCitiesOpinion` +{landownersMost} and `iFewestCitiesOpinion` {landownersFewest}, which **doubles** both ends to {landownersTop} at the top and {landownersBottom} at the bottom. {envyName} is unchanged.
- **{championsLink}** run the same mechanic on *units* instead, paying {championsLargest} for the largest military and {championsSmallest} for the smallest. The award there is not divided on a tie, because a tie pays nothing at all.
- Every other class contributes 0 to both terms, so their families use the flat global values.

## code.brackets.heading

Which bracket each family lands in

## code.reading.heading

How to read the result

## code.reading.body

- The city terms are only part of the total. Leader traits, council seats, laws, luxuries, wonders, religion and memories all add into the same number before the game brackets it, so the bracket shown here is what the cities alone would earn.
- The game recomputes the number instead of accumulating it, so **giving a city away fixes the number immediately**. There is no decay to wait out.
- The game previews the same calculation when you found a city, because the found-city tooltip shows each family's {envyName}, {mostCities} and {fewestCities} terms before and after, using the same routine with the new city already assigned.
- City count is not the only way cities move opinion. `calculateFamilyOpinionCityDist` also rewards a family whose own cities sit **close together**, measured from the average distance between them and the map's minimum spacing between city sites. Traders are the one class that wants the opposite (`bPrefersDistant`). Either way the distance term is a bonus and never a penalty, and the calculator here does not model it.

## fine

Formulas come from **PlayerOpinion.cs**, namely `calculateFamilyOpinionMostCities`, `calculateFamilyOpinionFewestCities` and `calculateFamilyOpinionEnvy`, which `calculateFamilyOpinionRate` sums and `InfoHelpers.getOpinionFamilyFromRate` brackets. The `triangle` function comes from **Utils.cs**. Constants come from `globalsInt.xml` and `familyClass.xml`, brackets from `opinionFamily.xml` and family colors from `color.xml`. Integer truncation is reproduced exactly. See {familiesLink} for the rest of each class's opinion modifiers, and {opinionLink} for the bracket effects in full.

---

Placeholders: `{mostCities}` `{fewestCities}` `{envyName}` `{mostValue}` `{fewestValue}` `{envyStep}`
`{envy2}` `{envy3}` `{envy4}` `{envy5}` `{landownersName}` `{landownersLink}` `{landownersMost}`
`{landownersFewest}` `{landownersTop}` `{landownersBottom}` `{championsLink}` `{championsLargest}`
`{championsSmallest}` `{opinionLink}` `{familiesLink}`.
