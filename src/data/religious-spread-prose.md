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
- The tables, the odds and the source citations are generated from `religious_spread.json`
  and `src/lib/religion-spread.ts`, so their numbers are not in this file.

## lede

A city gets a religion in one of five ways: the religion's own **roll every turn**, a
**Disciple**, a finished **shrine or other religious improvement**, a converted **tribal
settlement** whose tile joins the city, or an **event**. Only the first one involves chance,
and it is the one this page takes apart: how often a religion rolls, and which city it lands
in when it does. That choice is not uniform. The game weighs every eligible city by its
distance to the religion's Holy City, whether it is connected to the Holy City, and how many
religions it already has. How families and characters pick a faith is on
{conversionLink}.

## roll.heading

The roll each turn

## roll.body

Once per game turn, after every player has moved, each founded world religion rolls its spread
chance. On a success it spreads to exactly one city or tribal settlement, chosen as described
in the next section. A religion can never spread to two places in one turn this way.

- **The chance is global.** It belongs to the religion, not to a player, and the city it picks can belong to anyone: you, a rival, or a tribe.
- **Map size adds to it** for world religions only: {mapSizeList}.
- **Every theology the religion has established adds to it**, for everyone who follows it.
- **Player bonuses add up across all players.** {pilgrimageLink} gives {pilgrimageValue} to your state religion's chance, and if two players both run it with the same state religion, that religion gets it twice. The target city is still anyone's, so the law also pushes your religion into your neighbours' cities.
- **Religions that never roll**: every nation's pagan religion, plus {noRollList}. They spread only through their shrines, improvements and events.

## roll.note

Worked chance for {exampleReligion} on a {exampleMap} map with {exampleTheology}:
{exampleBase} base + {exampleMapValue} map + {exampleTheologyValue} theology =
**{exampleTotal}% per turn**, before any player bonus.

## pick.heading

Which city the roll picks

## pick.body

When the roll succeeds, the game gives every eligible city a score and the **lowest score
wins**. The score starts from the hex distance between the city and the Holy City, and it has a
random part that grows with that distance, so a near city is not guaranteed to win but a far
one almost never does.

1. **Distance.** Count the hexes from the Holy City to the city.
2. **Connection.** If the city is on the same trade network as the Holy City (the road, river and sea network that decides whether a city is Connected, as seen by the Holy City's owner), multiply that distance by {connPct}% and drop the fraction.
3. **Religions already there.** Multiply by one more than the number of religions the city already has. **Every religion counts**: pagan religions, world religions, and the owner's own state religion alike. The game uses the city's plain religion count here, not the count that leaves out the state religion. A city with one religion (even just its nation's pagan faith) counts as twice as far away, a city with two as three times as far.
4. **The roll.** Call the result D. The game draws a whole number from 1 to D and multiplies D by it. The score is anywhere from D to D × D.

Tribal settlements join the same contest for world religions, but only settlements of the
tribes you can do diplomacy with ({tribeList}), and only ones that have no religion at all.
They use the plain distance with no connection test. The game checks every city before any
settlement, and on an exactly equal score the first one checked keeps the win, so a settlement
loses ties.

## pick.eligible

A city takes part only if all of these hold:

- it does not already have the religion;
- the religion has not been purged from it (a Purge bans that religion from coming back by the roll until it gets back in some other way);
- it is a world religion (the owner's own pagan religion also qualifies, but pagan religions never roll);
- if the city has a no-spread effect ({iconographyLink} for all of the owner's cities, or a Dissent project from an event), the religion is the owner's state religion. A player with no state religion under {iconographyLink} takes no religion by the roll at all.

The Holy City itself already has the religion. The roll does nothing for a religion that has
no Holy City.

## distance.heading

What distance does

## distance.body

Because the random part is multiplied by D, a city's score grows with the square of its
distance. Two consequences are worth knowing:

- **Twice as far is much worse than half the chance.** Between two cities, the farther one wins only when it rolls low and the nearer one rolls high. At distances 6 and 12, the farther city wins {sixTwelve} of the time.
- **Some cities cannot win at all.** The best case for a city is a score of D. The worst case for the nearest candidate is D × D. So a city whose D is larger than the square of the nearest candidate's D is never picked: with a nearest D of 4, nothing above 16; with a nearest D of 6, nothing above 36.

The table below is the chance that the **farther** of two candidates wins, for every
pair of D values. It already includes the connection and religion multipliers, so read a
connected city at distance 12 as D = {conn12}, and an unconnected city at distance 6 that
already has one religion as D = 12.

## examples.heading

Worked examples

## examples.note

Three versions of the same map. The Holy City has three cities around it that do not have its
religion. Each table shows each city's D and its chance of being the one picked when the roll
succeeds. Multiply by the per-turn chance for the chance per turn: at {exampleTotal}% a city
with a 50% share gets the religion on about one turn in {halfShareTurns}.

## example.a

No connections, no other religions. Distance alone decides.

## example.b

A road now links the farthest city to the Holy City. Its distance counts as {connPct}%.

## example.c

The nearest city has already taken another religion, so its D doubles.

## calc.heading

Calculator

## calc.note

List the cities (and tribal settlements) that do not have the religion yet. The odds are exact:
they add up every possible roll, the same way the game draws them. Only the relative
distances matter, so there is no need to include cities that can never win.

## other.heading

The other ways in

## disciple.heading

Disciples

## disciple.body

A Disciple spreads its own religion to a city when it stands inside or next to that city's
territory, and it is used up doing so. It costs no Orders. There is no roll and no distance
rule, and the city can belong to anyone. The target only needs to lack the religion, so a
Disciple can convert a city even while that city refuses the religion by the roll. The spread
counts for the Disciple's owner toward religion-spread ambitions and leader stats.

A city can train a Disciple of a religion it follows when it is that religion's Holy City, the
religion is your state religion, or you have {toleranceLink}. {clericsNote} A Disciple costs
{discipleCost}, plus {disciplePer} for each Disciple of that religion the city has trained before.

## tribe.heading

Tribal settlements

## tribe.body

A Disciple next to a settlement of a tribe you can do diplomacy with, and that is not hostile
to you, can convert it for **{tribeBase} Money plus {tribePer} for every tribal conversion you
have made before**, on any tribe, for the rest of the game. The religion stays on the
settlement's tile. Whenever that tile becomes part of a city's territory, the city receives
the religion.

## improvement.heading

Shrines and religious improvements

## improvement.body

These improvements spread their religion to the city whose territory they stand in, the moment
they are finished. If the religion has not been founded yet, finishing one founds it in that
city, which is how a nation's first shrine founds its pagan religion.

## found.heading

Where a new religion is founded

## found.body

Every turn, right after the spread rolls, the game checks whether a world religion can be
founded, and it founds at most one. A city qualifies when the religion is not founded yet and
the city's owner meets every requirement in the table. The founding city becomes the Holy City,
which is the point every later spread roll measures distance from.

## found.pick

Among all qualifying cities (and all religions), the game adds up these weights and picks the
highest total. Equal totals are broken by a random shuffle, and every other player who had a
city on the same total gets a "lost the race" event trigger.

## found.note

The dynasty weight applies to {dynastyList}. Events can also found a religion directly,
without these checks.

## code.heading

Where this comes from
