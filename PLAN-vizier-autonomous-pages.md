# Plan: two new pages — Grand Vizier city rulership & Autonomous Rule

Status: IMPLEMENTED 2026-09-07 (pages `/grand-vizier`, `/autonomous-rule`; data `scripts/build_autobuild.py`). Kept as the grounding record. Written 2026-09-07 from the current
`reference/Source` + `reference/XML/Infos` sync. Every claim below cites the
function or XML entry it comes from so the implementer can re-verify.

---

## 0. The one mechanism behind both pages

Both features are the **same engine flag** wearing different clothes:

| | Grand Vizier | Autonomous Rule |
|---|---|---|
| Carrier | `EFFECTCITY_SHARED_POWER` ("Shared Power", `text-misc-btt.xml`) | `EFFECTCITY_PROJECT_AUTONOMOUS_RULE` |
| How it reaches a city | Council seat `COUNCIL_GRAND_VIZIER` → `EffectPlayer EFFECTPLAYER_SHARED_POWER_VIZIER` → `NoGovernorEffectCity` = Shared Power → added to **every city with no governor** (`City.cs:12240`, `Player.cs:9624`, `City.cs:3637`) | Hidden project `PROJECT_AUTONOMOUS_RULE` (`project-event.xml:527`) granted by event bonuses `aeAddProjects` |
| `bAutoBuild` | 1 | 1 |
| `bNoHurry` | 1 | 1 |
| `bNoBuildUnits` | — | **1** |
| `DefaultGovernor` | `COUNCIL_GRAND_VIZIER` (Vizier becomes *acting* governor) | — |
| Yields | none | `aiYieldRatePopulation` Science 10, Money 20 → **+1 Science and +2 Money per citizen** (÷10 rule) |
| Other | — | `iMaxCount 1`, `bCaptureDestroy 1` (lost on capture), `bHidden` (never buildable by anyone) |

`City.isAutoBuild()` is simply `miAutoBuildUnlock > 0`; every active EffectCity
with `bAutoBuild` adds 1 (`City.cs:5578`). These two are the **only** EffectCities
in the game with the flag (grep `bAutoBuild` in `effectCity.xml`).

### What autobuild takes away from the player (`Game.cs:17151–17205`)
The action handler refuses `BUILD_PROJECT`, `BUILD_SPECIALIST`, `BUILD_UNIT` and
`BUILD_QUEUE` (add/move/remove) when `isAutoBuild()`. UI text:
`TEXT_HELPTEXT_AUTO_BUILD_CITY_EFFECT` = "Cannot Change Production because of {LIST}";
help line `TEXT_HELPTEXT_EFFECT_CITY_HELP_NO_YIELDS_AUTO_BUILD` = "Cannot Choose Production".
Repeat-project flag is ignored (`City.cs:8556`). Hurry is blocked by `bNoHurry`
(`City.cs:10980`). Pre-existing manual queue items are **never reached**:
`doAutomatedCityBuilds` moves the autobuild item to slot 0 each turn and
`hasBuildPlanned()` only counts autobuild-flagged items (`City.cs:7008`), so the
AI keeps inserting ahead of them.

### What autobuild does NOT touch
- Worker jobs: rural/urban improvements, roads, **wonders** are worker actions, not
  the city queue. Fully player-controlled regardless.
- Buying tiles, laws, missions, governor assignment, religion, trade — untouched.
- The AI player's own valuation of the flag is `AI_CITY_AUTOBUILD_VALUE = 0`.

### When the pick happens
`Player.doTurn()` → `processTurn()` → `AI.doDecisions(...)` → **`AI.doAutomatedCityBuilds()`**
(`Player.cs:16901`) — at the *start* of your turn, before you can act. Also
immediately on founding (`Player.cs:16155`) and after a damaged city capture
(`Unit.cs:11567` → repair pick).

### The picker (`PlayerAI.cs`) — shared by both pages
`doAutomatedCityBuilds` (7995):
1. For each autobuild city, move the first `mbAutobuild` queue item to the front.
2. If any autobuild/automated city has no planned build or `shouldRepairCity`
   (damage > passive heal): `evaluateTurn()` (danger map, border cities, reachable
   tiles), `doAutomatedCityRepairs()`, then
   `doCityBuildPlanning(bCheckGoods:true, bShouldBuyYields:false, bAutoBuildOnly:true)`
   → per city `getBestBuild(..., iNumBuilds:1, bIgnoreDanger:false)`; if the winner
   isn't already queued it's registered as an **expense** with its value; then
   `sortExpenses()` and `doYieldExpenses(bAllowBuyYields:false)` executes expenses
   **across all cities in descending value**, each only if
   `testCanSpendYields` passes **without buying goods** — otherwise the yield is
   marked short and the expense dropped.
3. Fallback: any autobuild city still without a build → `chooseBuild(city, NONE, first, bIgnoreDanger:false)`
   (again no buying: `shouldBuyYields()` is false for humans — `isAIAutoPlay()`).

`getBestBuild` (17534) builds three candidate pools, sorts by value desc
(tie: build type, then id, then tile):

**Projects** — every project with `isBuildProjectValid` ∧ `canBuildProject(bBuyGoods, bTestGoods)`:
- `isBuildProjectValid` (17296): if the city is *in danger*, only **defensive**
  projects (effect has `iCityHP>0` or `iStrengthModifier>0` → **Walls, Moat,
  Towers** plus the EotI event-only **Improvised Defenses**); if the city is a **border city** and a defensive
  project is buildable, non-defensive projects are excluded too.
- `canBuildProject` (City.cs ~10000): hidden/DLC/`isProjectNotValid` out;
  `canHaveProject` (unique, requires-damage, maxCount, bonus doable, invalidated-by,
  project prereq, game option); culture gates; tech; maxCount incl. queued;
  `iExtraPopRequired`; family seat; **`bRequiresGovernor` → `isGoverned()`**
  (which is TRUE under the Vizier's acting governorship); minimum culture; goods.
- Value: `getProjectBuildValue` = `getBuildValue(projectValue(...), cityYield(project yield), cost, 2, 8)`;
  halved if 0 citizens and Growth-costed. `projectValue` (13012) = effectCity value
  (skipped if redundant: `bSingle` already present) + effectCityExtra + effectPlayer
  + finish-bonus value (`bonusValue`) + yield-modifier value + `FINISHED_AMBITION_BONUS`
  if an active ambition counts it − value of projects it invalidates × count
  − (production cost + `aiYieldCost`) weighted by AI yield values + ½ value of what
  it unlocks; floored at 1 → **every legal project is always a candidate**.

**Specialists** — skipped entirely when in danger. Per territory tile with an active
improvement: `tile.getNextSpecialist()`'s class → first specialist of that class the
city `canBuildSpecialist` (17476). Value = `getBuildValue(specialistValue, Civics rate, cost, 2, 8)`.

**Units** — every unit passing `isBuildUnitValid` (17321):
- `isUnitSpawnPossible`; `canBuildUnit(bTestEnabled)` — **this is where `bNoBuildUnits`
  removes every unit** (City.cs:10916), incl. workers/settlers/disciples.
- In danger → only units that `canDamage`. Not in danger → land military capped at
  `current > 1.5 × target` (regular) and warships per water area at 1.5 × target.
- Then a need test: workers per family (target = max(1, min(1.5 × family cities,
  0.5 × Orders × familyCities ÷ cities)); build while current < 1.5 × target);
  disciples (30 per 100 cities, 10 per 100 Orders; none if nowhere to spread and
  idle ones exist); settlers if reachable vacant/allied city sites; missionaries if
  religion unspread and none exist; **regular military always passes**; emergency
  units (`canDamage && !bRegular`) only under danger or under-target with no
  latest-upgrade unit available; scouts while < cities ÷ 2.
- Value: `getUnitBuildValue` = `unitValue` (base × need modifier: city production vs.
  average, family cities share, target gap, danger, family military opinion; +
  ambition bonuses − consumption − cost) halved if city production < 75% of the
  unit's average (`AI_NO_UNIT_BUILD_PERCENT`), then `getBuildValue(..., 4, 8)` unless
  the unit is needed (`getUnitTypeNeedModifier > 0`).

**Military target** `calculateTargetMilitaryUnitNumber` (~10200): max(10, 2.5 × cities)
+ forts + revealed tribal camps; ±50% by war likelihood vs. contacted players (or
+50% if not peaceful); then **for human players only**: sum of `iUnitBuildModifier`
over traits of council characters whose seat has `bTraitsAffectAutobuild` —
**only the Grand Vizier has that flag** (`council-btt.xml`). Clamp −50..+100.
Traits: Hero/Commander/Tactician archetype +25, Warlike +25, Diplomat −15,
Scholar −15, Timid −15, Builder −25 (`trait.xml`).

**Turn discount** `getBuildValue(base, rate, cost, min, half)`:
turns = ceil(cost × 10 / rate); if turns ≤ min → base; else
base × (half − min) ÷ (turns + half − 2·min). Constants (`globalsAI.xml`):
projects 2/8, specialists 2/8, units 4/8. A project taking 8 turns is worth ~½,
20 turns ~¼.

**Repairs** `chooseRepairBuild`: when damage > passive heal, best project whose
Bonus has `iHPCity`/`iHPCityPercent`; note it passes `bBuyGoods:true`.

**Danger** `isCityInDanger`: cached danger > `AI_CITY_MIN_DANGER` (1) and > tile
protection. If the danger-filtered pass returns nothing, `getBestBuild` reruns
with `bIgnoreDanger:true`.

---

## 1. Page A — `/grand-vizier` · "Grand Vizier Rulership"

Section: **Court** (right after Council & Courtiers in `tabs.ts`). Mark 📜 or 🏛️.
Status `built`. Cross-link from `council.astro`'s Grand Vizier column ("how the
Vizier picks builds →") and from `stat-scaling.astro`'s existing Vizier note.

### Content outline
1. **Lede** — Behind the Throne seat (`GameContentRequired EVENTPACK_SCANDAL`);
   candidate must have **Power Hungry** or **Rising Star** (`abTraitPrereq`);
   +40 opinion, 10 XP/turn, `bNoNotifications`; grants **Grand Vizier Rulership**
   (`TEXT_EFFECTPLAYER_COUNCIL_VIZIER`) = "Shared Power" in every city without a
   governor. In-game phrasing to reuse: "[Cities without Governor] {effect}" and
   "{character} acts as a Governor" (`TEXT_HELPTEXT_EFFECT_CITY_HELP_NO_YIELDS_DEFAULT_GOVERNOR`).
2. **Which cities the Vizier runs** — rule + a 3-row "how to opt out" table:
   assign any governor to that city (effect removed, manual control back);
   dismiss the Vizier (all cities back); a governor dying/leaving re-adds it.
3. **Acting governor: what the Vizier's character does to those cities**
   (`City.governor(bIncludeActing)`, `updateDefaultGovernor`):
   - trait **GovernorEffectCity** of each Vizier trait applies in every such city
     (45 traits carry one; render from `trait.xml` via humanizer, link to /traits);
   - **governor-opinion yields** (`calculateGovernorOpinionYield` → `yield.maiOpinionCharacterRate`)
     keyed to the Vizier's opinion of you;
   - `isGoverned()` true → **Suppress Dissent** projects become buildable (6, `bRequiresGovernor`);
   - no rating yields (seat has none), no Civics governor cost, `isGovernorLeader` false.
4. **When the Vizier decides** — start of your turn (before you act), on founding,
   after damaged capture. Manual queue frozen; items preserved but never reached.
5. **How the Vizier chooses** — the shared picker (Section 0) rendered as:
   a. numbered procedure (candidates → filters → value → turn discount → global
      execution by value with **no purchasing**);
   b. **Filters table** (danger / border / unit caps / worker-disciple-settler-scout
      needs, with the constants);
   c. **Value & discount table** with min/half turns per build type and a worked
      example (e.g. 60-Civics project at 6/turn → 10 turns → 6/16 = 37.5% value);
   d. **The only trait lever**: unit-build-modifier traits table (8 rows) and how
      it moves the military target.
6. **What the Vizier never does** — buy goods/yields, hurry, repeat, wonders or
   improvements (workers), honor your queue order, build in danger anything but
   defenders/Walls/Moat/Towers (unless nothing qualifies).
7. **Compared** — Manual · City Automation button (`CITY_AUTOMATE`, "Start City
   Automation") · Grand Vizier · Autonomous Rule matrix (who picks, queue locked?,
   hurry?, units?, opt-out, yields, governor). Note: the Automation button uses
   the same planner but does **not** lock the queue or block hurry (Game.cs gates
   only test `isAutoBuild`), and has no `chooseBuild` fallback (line 8036 is
   `isAutoBuild` only) — an automated city with nothing affordable idles.
8. **Source references** footer list (file:function).

---

## 2. Page B — `/autonomous-rule` · "Autonomous Rule"

Section: **Cities** (after Projects). Mark 🏙️/🗽. Status `built`. Cross-link from
`projects.astro` row `autonomous_rule` (its entity home stays `/projects`), from
the three event pages that host the events, and from Page A's comparison table.

### Content outline
1. **Lede** — what the project is (hidden, event-granted, one per city, lost on
   capture) and its yields: +1 Science, +2 Money per citizen; Cannot Choose
   Production / Cannot Build Units / Cannot Hurry (already humanized in `projects.json`).
2. **How a city becomes autonomous** — table generated from
   `eventStory*.xml` + `eventOption*.xml` + `bonus-event*.xml`:
   - `EVENTSTORY_CITY_AUTONOMY` "Autonomy in {city}" (Zenobia; target is a non-capital,
     non-family-seat city; weight 2, once). Yes → `aeAddProjects AUTONOMOUS_RULE` +
     Zenobia made governor (`iGovernorOfSubject 0`) + event link; No → happiness down.
   - `EVENTSTORY_CLAIMANT_ARRIVES_BTT` / `_CONT` (BTT claimant chain, `eventStory-eoti.xml:11653/11713`)
     via `BONUS_PROJECT_AUTONOMOUS_RULE` — render the exact option text.
   - CORRECTION (found by the auto-scan in `build_autobuild.py`): **Demand for
     Autonomy DOES grant it** (its option carries `BONUS_EVENTOPTION_CITY_AUTONOMY_YES_CITY`
     alongside the memory bonus), and so do Independent City, Autonomous Vassal,
     Corruption of the Youth (BTT) and Son of the Star (SaP). Eight grant events in
     total; four end events (Empress, End of Autonomy, Autonomous Liberties,
     Reclaiming Control on succession). Never hand-list these — detect from bonuses.
3. **What the city can and cannot build** (the user's core ask):
   - **Can**: any *project* the city could normally build — Treasury/Forum/… tiers,
     **Decrees I–IV** (Statesmen seat + Constitution, repeatable but repeat is
     ignored so each is re-chosen on merit), Festivals, Inquiries, Hunts, Walls/Moat/
     Towers, **Opulence** (`PROJECT_LAVISH_LIFESTYLE`, display name confirmed
     "Opulence"; BTT, 100 Civics + 500 Money, Developing Culture, needs Luxurious
     Estates with a luxury; one per city, `bNoHurry`; slug `lavish_lifestyle` on
     /projects), Suppress Dissent only if governed; and
     **specialists** (rural & urban, next tier per tile).
   - **Cannot**: **any unit** (military, workers, settlers, disciples, scouts,
     ships) — `bNoBuildUnits`; hurrying; player queue edits; repeat.
   - **Unaffected**: worker actions (improvements, roads, wonders), tile buys,
     governor assignment, laws.
   - Show the "in danger" corner case: specialists drop out and only Walls/Moat/
     Towers remain; if none legal, the danger filter is lifted and all projects
     return.
4. **How it picks** — short version of the shared picker with a link to Page A's
   full breakdown; note the Autonomous city is planned in the same global
   value-ordered expense pass as Vizier cities and never buys goods.
5. **How it ends** — table: `EVENTSTORY_CITY_AUTONOMY_EMPRESS` (4 turns after,
   via `EVENTLINK_CITY_ZENOBIA_AUTONOMY`; "far enough" → project removed + 4 rebel
   units + Zenobia imprisoned; "admired" → happiness, endeared, −6 Legitimacy in the
   BTT variant); `EVENTSTORY_CITY_AUTONOMY_END` (new turn, 10%, repeat 15, any
   autonomous city; "take back" → removed + 4 rebels; "earned freedom" → keep, XP);
   `EVENTSTORY_AUTONOMOUS_LIBERTIES` (needs a non-leader governor there; "experiment
   must end" → removed + governor disappointed); city captured → `bCaptureDestroy`.
6. **Compared** — same 4-way matrix as Page A (shared component or duplicated markup).
7. **Source references**.

---

## 3. Data layer — `scripts/build_autobuild.py` → `src/data/autobuild.json`

Single script feeding both pages (deterministic `sort_keys=True`), registered in
`Makefile data:`. Contents:
- `constants`: from `globalsAI.xml` — AI_MIN/HALF_VALUE_{PROJECT,SPECIALIST,UNIT}_BUILD_TURNS,
  AI_NO_UNIT_BUILD_PERCENT, AI_CITY_MIN_DANGER, AI_MAX_NUM_WORKERS_PER_HUNDRED_{CITIES,ORDERS},
  AI_MAX_NUM_DISCIPLES_PER_HUNDRED_{CITIES,ORDERS}, AI_CITY_AUTOBUILD_VALUE.
- `carriers`: the two EffectCities with flags + humanized yields (via `humanize.render_effect_city`).
- `vizier`: council entry (reuse `build_council.py` logic or import its output), trait
  prereqs, effectPlayer name/text, in-game help strings.
- `unitBuildModifierTraits`: `[ {id, name, modifier} ]` from `trait.xml`.
- `defensiveProjects`: computed from `effectCity.iCityHP>0 || iStrengthModifier>0` (currently Walls, Moat, Towers).
- `governorRequiredProjects`: `bRequiresGovernor` list (6 Suppress Dissent).
- `governorTraitEffects`: count + list of traits with `GovernorEffectCity` (+ humanized effect) for Page A §3.
- `autonomy.events`: grant/end events with options, bonuses (add/remove project,
  rebels, legitimacy, governor), story/option en-US text with `link()` stripped
  (`_strip_link_templates`), and links into existing event pages (`event-search.json` `h` field).
- `autonomyProject`: pull from `projects.json` row `autonomous_rule`.
- `opulence` (`PROJECT_LAVISH_LIFESTYLE`) and `decree` example rows (ids only; page reads `projects.json`).

Hard-coded prose constants (min/half turns etc.) must come from this JSON, not
literals in `.astro`.

## 4. Guardrails
- Add to `scripts/verify_source_constants.py` `WATCHED`: `PlayerAI.doAutomatedCityBuilds`,
  `getBestBuild`, `isBuildProjectValid`, `isBuildUnitValid`, `getBuildValue`,
  `calculateTargetMilitaryUnitNumber`, `City.updateDefaultGovernor`, `City.canBuildUnit`
  (the `isNoBuildUnits` gate), `Game` action gates are too big — skip.
- `make audit` untouched (no new effect fields). `make check` must pass with the
  new internal links; entities: no new homes needed (Autonomous Rule stays on /projects).
- Design rules: dark, Cinzel headings, `.ntbl` for the matrices, `.yield-*` only
  where a cell is about a yield (Science/Money cells for the autonomy yields),
  `LinkedText` on prose, `Term` for PROJECT_*/TRAIT_*/COUNCIL_* ids.
- Mobile: comparison matrix needs `col[data-X]` widths (see memory note).

## 5. Open questions to resolve during implementation (not blockers)
- `BuildType` tie-break order (PROJECT/SPECIALIST/UNIT enum order) — cosmetic.
- (Resolved) "Opulence" = `PROJECT_LAVISH_LIFESTYLE`; the XML id says Lavish
  Lifestyle but the en-US name is Opulence. Always render the display name.
- Zenobia subject constraints (`SUBJECT_ZENOBIA` → `CHARACTER_ZENOBIA`): confirm
  how the character is generated (character.xml) for the event table's "who".

## 6. Order of work
1. `build_autobuild.py` + Makefile + run `make data` (verify JSON by eye).
2. `grand-vizier.astro` (full picker breakdown) — the reference page.
3. `autonomous-rule.astro` reusing the comparison matrix and picker summary.
4. `tabs.ts` entries; cross-links from council/projects/stat-scaling/event pages.
5. `verify_source_constants.py` WATCHED additions → `make audit`.
6. `npx astro build && make check`; headless-Chrome mobile screenshot of both.
