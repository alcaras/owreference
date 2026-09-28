# Religious Spread: page prose

Every editable line of `/religious-spread` lives here, and `src/pages/religious-spread.astro`
reads this file at build time. You can edit in place with `npm run edit` and
http://localhost:4321/owreference/religious-spread/?edit, where ⌘S saves back into this file,
or you can edit the text below by hand and rebuild.

- Each `## key` heading is one text slot. Keep the keys; reword or delete the text under them.
- Plain paragraphs, blank-line separated. Lines starting with `- ` become bullets.
  Inline markup: `**bold**`, `*emphasis*`, `` `code` ``, `[text](url)`.
- `{placeholders}` are filled from the game data at build time and listed at the bottom.
  They render as locked chips in the editor.
- The tables and the odds are generated from `religious_spread.json` and
  `src/lib/religion-spread.ts`, so their numbers are not in this file.

## lede

A city can get a religion from the religion's own **roll every turn**, a **Disciple**, a
**shrine or other religious improvement**, a converted **tribal settlement**, or an **event**.
This page is about the roll: how often it happens, and which city it picks. For how
families and characters pick a faith, see {conversionLink}.

## roll.heading

The roll each turn

## roll.body

Once per turn, after every player has moved, each founded world religion rolls its spread
chance. On a success it spreads to exactly one city or tribal settlement, picked as described
in the next section.

- **The chance belongs to the religion,** not to a player, and the city it picks can be anyone's: yours, a rival's, or a tribe's.
- **Map size adds to it** for world religions only: {mapSizeList}.
- **Every theology the religion has established adds to it.**
- **Player bonuses add up across all players.** {pilgrimageLink} gives {pilgrimageValue} to your state religion's chance, and if two players both run it with the same state religion, that religion gets it twice. The target city is still anyone's, so the law also pushes your religion into your neighbours' cities.
- **Some religions never roll**: every nation's pagan religion, plus {noRollList}. They spread only through their shrines, improvements and events.

## roll.note

Worked chance for {exampleReligion} on a {exampleMap} map with {exampleTheology}:
{exampleBase} base + {exampleMapValue} map + {exampleTheologyValue} theology =
**{exampleTotal}% per turn**, before any player bonus.

## pick.heading

Which city the roll picks

## pick.body

When the roll succeeds, every eligible city gets a score and the **lowest score wins**. The
score starts from the city's distance to the Holy City and has a random part that grows with
that distance, so a near city isn't guaranteed to win but a far one almost never does.

1. **Distance.** Count the tiles from the Holy City to the city.
2. **Connection.** If the city is on the Holy City owner's trade network (roads, rivers and sea), multiply that distance by {connPct}%, rounded down.
3. **Religions already there.** Multiply by one more than the number of religions the city already has. **Every religion counts**, including pagan religions and the owner's state religion. A city with one religion (even just its nation's pagan faith) counts as twice as far away, a city with two as three times as far.
4. **The roll.** Call the result D. The game picks a random whole number from 1 to D and multiplies D by it, so the score is anywhere from D to D × D.

Tribal settlements join the contest for world religions, but only settlements of the tribes you
can do diplomacy with ({tribeList}) that have no religion yet. They use the plain distance with
no connection test, and they lose exact ties to cities.

## pick.eligible

A city can be picked only if:

- it doesn't already have the religion;
- the religion hasn't been purged from it (a Purge keeps the roll from bringing it back until it gets back in some other way);
- the religion is a world religion;
- if the city refuses spread ({iconographyLink} for all of the owner's cities, or a Dissent project from an event), the religion is the owner's state religion. Under {iconographyLink} with no state religion, the roll never picks your cities.

The roll does nothing for a religion that has no Holy City.

## distance.heading

What distance does

## distance.body

Because the random part is multiplied by D, a city's score grows with the square of its
distance. Two consequences:

- **Twice as far is much worse than half the chance.** At distances 6 and 12, the farther city wins {sixTwelve} of the time.
- **Some cities can't win at all.** A city's best score is D, and the nearest city's worst is D × D. So with a nearest D of 4, no city above 16 can win; with a nearest D of 6, nothing above 36.

The table shows the chance that the **farther** of two cities wins, for every pair of D values.
Apply the connection and religion multipliers first: a connected city at distance 12 is
D = {conn12}, and an unconnected city at distance 6 that already has one religion is D = 12.

## examples.heading

Worked examples

## examples.note

Three versions of the same map: a Holy City with three cities around it that don't have its
religion. Each table shows each city's D and its chance of being picked when the roll succeeds.
Multiply by the per-turn chance for the chance per turn: at {exampleTotal}% a city with a 50%
share gets the religion about one turn in {halfShareTurns}.

## example.a

No connections, no other religions. Distance alone decides.

## example.b

A road now links the farthest city to the Holy City, so its distance counts at {connPct}%.

## example.c

The nearest city has already taken another religion, so its D doubles.

## calc.heading

Calculator

## calc.note

List the cities and tribal settlements that don't have the religion yet. The odds are exact:
they add up every possible roll. Only relative distances matter, so you can leave out cities
that can never win.

## other.heading

The other ways in

## disciple.heading

Disciples

## disciple.body

A Disciple standing inside or next to a city's territory can spread its religion there, and is
used up doing so. It costs no Orders, has no roll and no distance rule, and the city can be
anyone's. The city only needs to lack the religion, so a Disciple works even on a city that
refuses the religion by the roll. The spread counts toward your religion-spread ambitions and
leader stats.

A city can train a Disciple of a religion it follows when it is that religion's Holy City, the
religion is your state religion, or you have {toleranceLink}. {clericsNote} A Disciple costs
{discipleCost}, plus {disciplePer} for each Disciple of that religion the city has trained before.

## tribe.heading

Tribal settlements

## tribe.body

A Disciple next to a settlement of a tribe you can do diplomacy with, and that isn't hostile to
you, can convert it for **{tribeBase} Money plus {tribePer} for every tribal conversion you have
made before**, on any tribe. The religion stays on the settlement's tile, and whichever city
later gains that tile gets the religion.

## improvement.heading

Shrines and religious improvements

## improvement.body

These improvements spread their religion to the city whose territory they're in as soon as
they're finished. If the religion hasn't been founded yet, finishing one founds it in that city;
that is how a nation's first shrine founds its pagan religion.

## found.heading

Where a new religion is founded

## found.body

Every turn, right after the spread rolls, the game checks whether a world religion can be
founded, and founds at most one. A city qualifies when the religion isn't founded yet and the
city's owner meets every requirement in the table. The founding city becomes the Holy City,
which every later spread roll measures distance from.

## found.pick

Among all qualifying cities, for all religions, the game adds up these weights and picks the
highest total. Ties are broken at random, and every other player with a city on the same total
gets a "lost the race" event.

## found.note

The dynasty weight applies to {dynastyList}. Events can also found a religion directly,
without these checks.
