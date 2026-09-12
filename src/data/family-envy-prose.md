# Envy & the City Split — page prose

Every editable line of `/family-envy` lives here; `src/pages/family-envy.astro` reads
this file at build time. Edit in place with `npm run edit` and
http://localhost:4321/owreference/family-envy/?edit (⌘S saves back into this file), or edit
the text below by hand and rebuild.

- Each `## key` heading is one text slot. Keep the keys; reword or delete the text under them.
- Plain paragraphs, blank-line separated. Lines starting with `- ` become bullets.
  Inline markup: `**bold**`, `*emphasis*`, `` `code` ``, `[text](url)`.
- `{placeholders}` are filled from the game data at build time (listed at the bottom);
  they render as locked chips in the editor.
- Not in this file: the calculator's own labels (headings with live numbers, table
  headers, tooltips, the "N of M splits" line) and the "What lands where" bracket list,
  which is generated from opinion.json.

## lede

**{mostCities}** (+{mostValue}, shared by families tied at the top), **{fewestCities}** ({fewestValue}, shared at the bottom) and **{envyName}** (nothing until two cities behind the leader, then {envyStep} × triangle) are the {opinionLink} terms that depend only on how many cities each family holds; **{landownersName}** feel both ends {landownersMost} harder. Pick your families and city total to rank every split, kindest first. Details below the calculator.

## rung.note

Kindest split first: the one whose *unhappiest* family is least unhappy, then by the sum. Favouring a family lists one row per city count it could hold and marks the *recommended* trade-off: the most favoured cities before anyone drops into Angry. Click a row for the breakdown.

## envy.heading

The {envyName} curve

## envy.body

`triangle(lead − yours − 1) × {envyStep}`, where *lead* is the most cities any one family holds. One city behind is free; after that each further city costs more than the last.

## ties.heading

Ties split the award

## ties.body

{mostCities} and {fewestCities} are divided by the number of families tied at that end, truncating toward zero — and if *every* family is tied, neither term applies at all. That is why a perfectly even split is worth exactly nothing rather than being worth something to everyone.

## code.heading

What the code says

## code.most.heading

{mostCities}

## code.most.body

- Goes to the family holding **at least as many** cities as every other — a family that merely ties for the lead still qualifies.
- The award is `({mostValue} + the class's own bonus) ÷ families tied at the top`, C# integer division.
- Nothing is paid when **all** families are tied — a young empire where every family holds one city collects at neither end — and nothing in a 1-family game.

## code.fewest.heading

{fewestCities}

## code.fewest.body

- The mirror image: charged to whoever holds **no more** cities than anyone else, split across everyone tied at the bottom.
- Both ends can land on the same family only if the split is even — and an even split cancels both, so in practice no family ever takes both.
- A family with **zero** cities is still counted; losing your last city to a rival leaves the family at the bottom of the table, not out of it.

## code.envy.heading

{envyName}

## code.envy.body

- Compares every family against the **largest** family, not against the average, so one runaway family makes the other two miserable at once.
- `(yours + 1) ≥ lead` pays nothing — the one-city grace is what makes a 4/3/3 split so much cheaper than 4/4/1.
- Triangular, not linear: two behind is {envy2}, three is {envy3}, four is {envy4}, five is {envy5}. The fifth city of a gap costs as much as the first four together.
- Unlike the other two it has no tie logic and no class modifier — every family reads the same ladder.

## code.class.heading

Class extras

## code.class.body

- **{landownersLink}** are the only class that bends these terms: `iMostCitiesOpinion` +{landownersMost} and `iFewestCitiesOpinion` {landownersFewest}, which **doubles** both — {landownersTop} at the top, {landownersBottom} at the bottom. Envy is unchanged.
- **{championsLink}** run the same mechanic on *units* instead ({championsLargest} / {championsSmallest} for the largest and smallest military), and there the award is not divided on a tie — ties simply pay nothing.
- Every other class contributes 0 to both, so their families read the flat globals.

## code.brackets.heading

What lands where

## code.reading.heading

Reading the result

## code.reading.body

- The city terms are only part of the sum. Leader traits, council seats, laws, luxuries, wonders, religion and memories all add into the same number before it is bracketed, so the bracket shown here is what the cities alone would earn.
- Because it is recomputed rather than accumulated, **giving a city away fixes the number immediately**. There is no decay to wait out.
- Founding a city is also previewed this way in-game: the found-city tooltip shows each family's Envy and Most/Fewest terms *before and after*, which is the same routine run with the new city already assigned.
- The count is not the only way cities move opinion — `calculateFamilyOpinionCityDist` also rewards a family whose own cities sit **close together**, off the average distance between them and the map's minimum city-site spacing. Traders are the one class that wants the opposite (`bPrefersDistant`), and either way it is a bonus only, never a penalty. It is not modelled here.

## fine

Formulas from **PlayerOpinion.cs** — `calculateFamilyOpinionMostCities`, `calculateFamilyOpinionFewestCities`, `calculateFamilyOpinionEnvy`, summed by `calculateFamilyOpinionRate` and bracketed by `InfoHelpers.getOpinionFamilyFromRate`; `triangle` from **Utils.cs**. Constants from `globalsInt.xml` and `familyClass.xml`, brackets from `opinionFamily.xml`, family colors from `color.xml`. Integer truncation is reproduced exactly. See {familiesLink} for the rest of each class's opinion modifiers and {opinionLink} for the bracket effects in full.

---

Placeholders: `{mostCities}` `{fewestCities}` `{envyName}` `{mostValue}` `{fewestValue}` `{envyStep}`
`{envy2}` `{envy3}` `{envy4}` `{envy5}` `{landownersName}` `{landownersLink}` `{landownersMost}`
`{landownersFewest}` `{landownersTop}` `{landownersBottom}` `{championsLink}` `{championsLargest}`
`{championsSmallest}` `{opinionLink}` `{familiesLink}`.
