#!/usr/bin/env python3
"""Extract Old World's turn order-of-operations from the game source.

Parses the doTurn-family function bodies in
reference/Source/Base/Game/GameCore/ and emits src/data/turn_order.json:
ordered steps (source order is sacred) with loop / conditional context,
real file:line refs, and curated titles + one-line descriptions.

Steps whose call is itself a doTurn-family function (Tile/Tribe/City/Unit/
Character) embed that function's extracted steps as children. Calls without
a curated label still emit (prettified title) and are collected in
_meta.unlabeled — the audit pattern; they are printed at build time.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, 'reference', 'Source', 'Base', 'Game', 'GameCore')
OUT_PATH = os.path.join(ROOT, 'src', 'data', 'turn_order.json')

# ---------------------------------------------------------------------------
# Sequences to extract: key -> (file, signature regex, expected line)
# Expected lines are a sanity anchor (±80 tolerance for patch drift).
# ---------------------------------------------------------------------------

SEQUENCES = {
    'game':           ('Game.cs',      r'protected virtual void doTurn\(\)',          12738),
    'player':         ('Player.cs',    r'public virtual void doTurn\(\)',             16866),
    'player_process': ('Player.cs',    r'protected virtual void processTurn\(\)',     16505),
    'tile':           ('Tile.cs',      r'public virtual void doTurn\(\)',             10905),
    'tile_player':    ('Tile.cs',      r'public virtual void doPlayerTurn\(\)',       11447),
    'tribe':          ('Tribe.cs',     r'public virtual void doTurn\(\)',               289),
    'city':           ('City.cs',      r'public virtual void doPlayerTurn\(',          8217),
    'city_tribe':     ('City.cs',      r'public virtual void doTribeTurn\(\)',         8112),
    'unit':           ('Unit.cs',      r'public virtual void doTurn\(\)',              5576),
    'character':      ('Character.cs', r'public virtual void doTurn\(\)',              7447),
    'character_year': ('Character.cs', r'protected virtual void doTurnYear\(\)',       8306),
}

# Calls that, when seen inside a sequence, embed another sequence's steps as
# children: (seq, call name, receiver regex) -> child sequence key.
NEST_RULES = [
    ('game',           'doTurn',       r'pLoopTile',                'tile'),
    ('game',           'doTurn',       r'tribe\(',                  'tribe'),
    ('player_process', 'doTurn',       r'unit\(',                   'unit'),
    ('player_process', 'doTurn',       r'pLoopCharacter|pLeader',   'character'),
    ('player_process', 'doPlayerTurn', r'city\(',                   'city'),
    ('player_process', 'doPlayerTurn', r'pLoopTile',                'tile_player'),
    ('player_process', 'doTribeTurn',  r'city\(',                   'city_tribe'),
    ('character',      'doTurnYear',   r'^$',                       'character_year'),
]

# ---------------------------------------------------------------------------
# Noise filters
# ---------------------------------------------------------------------------

# Receivers that are pure plumbing (logging, text, asserts, caches).
SKIP_RECEIVERS = re.compile(
    r'(TextManager|HelpText|MohawkAssert|MohawkLog|CollectionCache|'
    r'UnityProfileScope|Constants|Math|profileScope|goodsList|textSB|logDataSB|'
    r'Scoped|\.Value$|azTileTexts|aiCityYields|aiUnits|charListScope|nameScope)'
)

# Call names that are plumbing/bookkeeping, never gameplay steps.
SKIP_CALLS = {
    # logging / UI text
    'pushLogData', 'addTurnSummary', 'pushNextPopupText', 'addTileText',
    'sendTileTexts', 'sendAnalytics', 'TEXT', 'Log', 'Assert', 'buildCommaList',
    'ProfiledToString', 'LanguageSwitchScoped', 'StringBuilder', 'TileText',
    # collections / iteration plumbing
    'Add', 'Remove', 'RemoveAt', 'Clear', 'Reverse', 'Shuffle', 'PeekFront',
    'GetListScoped', 'GetDictionaryScoped', 'GetHashSetScoped',
    'GetStringBuilderScoped', 'getAliveUnits', 'getActiveCharacters',
    'getTraits', 'getTilesInRange',
    # internal per-turn bookkeeping (state flags / counters, no player-visible
    # effect of their own)
    'nextTurnSeed', 'updateHistory', 'updateLastData',
    'setLastDoTurn', 'setProcessingTurn', 'setProcessingTurnStart',
    'setStartTurnCities', 'setTechRedraw', 'setUsedOffensive',
    'setConvertedLegitimacy', 'setTurnSummaryReady', 'setUnitsProducedTurn',
    'changeTurnsSinceLastMove', 'setTurnSteps', 'setFreeActionsTaken',
    'loadRoutChain', 'resetCriticalHit', 'setYieldOverflow',
    'setYieldPriceTurn', 'setTurnYieldPriceHistory',
    'setAnchoredTurns', 'setUnlimberedTurns', 'setAutoHeal',
    'setDeathReason', 'setRaidedTurn', 'clearCompletedBuild',
    'doNetwork', 'sendInitCycle', 'doAchievement',
    'RandomStruct', 'fillValues', 'doDebugEventLog',
    # accessor lookups assigned to locals (Tile pLoopTile = tile(iI); …)
    'tile', 'city', 'unit', 'character', 'player', 'tribe', 'leader',
    'effectCity', 'cityTerritory', 'tileAdjacent', 'unitGeneral',
    'checkDeathTrait', 'modify',
}

# Specific (file, line) statements to drop: duplicates of an adjacent labeled
# step, or alternate branches already covered by its description.
SKIP_LINES = {
    ('Player.cs', 16536),  # incrementLeaderStat YEARS_REGENT — covered by 16533
    ('Player.cs', 16567),  # changeMoney      — else-branch of the Orders sale
    ('Player.cs', 16568),  # changeYieldStockpileWhole — same
    ('Player.cs', 16585),  # setYieldStockpile — pre-found Orders top-up (setup)
    ('Player.cs', 16656),  # processYield(Orders)  — covered by 16654
    ('Player.cs', 16676),  # processYield(Science) — covered by 16674
    ('Player.cs', 16811),  # incrementLeaderStat AMBITION — part of doBonus step
    ('Tile.cs',   10919),  # clearImprovement — covered by pillage-tick step
    ('Tile.cs',   10946),  # setTradeOutpostTime decrement — part of outpost step
    ('Tile.cs',   10962),  # setCitySite(NONE)  — part of foundCity step
    ('Tile.cs',   10968),  # setTradeOutpostTime reset — same
    ('Tile.cs',   10991),  # resetImprovementUnitTurns — part of spawn step
    ('City.cs',    8233),  # verifyBuildProjects(bonusOnly) — covered by 8288
    ('City.cs',    8268),  # player().changeYieldTotal — stat tracking
    ('City.cs',    8289),  # verifyBuildSpecialists — folded into 8288 desc
    ('City.cs',    8290),  # verifyBuildUnits       — folded into 8288 desc
    ('Unit.cs',    5696),  # act() — part of the worker-construction step
    ('Unit.cs',    5697),  # incrementLeaderStat WORKER_TURNS — same
    ('Unit.cs',    5729),  # setFortifyTurns(0) in city — covered by 5733 desc
    ('Unit.cs',    5735),  # act() — part of fortify step
    ('Unit.cs',    5743),  # setFormationTurns(0) — covered by 5747 desc
    ('Unit.cs',    5749),  # act() — part of formation step
    ('Unit.cs',    5870),  # height damage — folded into terrain-damage step
    ('Unit.cs',    5910),  # convert(barbarians) — part of stopRaid step
    ('Player.cs', 16768),  # doAchievement royal couple — achievement plumbing
    ('Unit.cs',    5845),  # wake() on full heal — folded into the healing step
}

# Pure-query prefixes: a statement-call starting with one of these is skipped
# unless it has an explicit label (assignments to queries are not steps).
QUERY_PREFIXES = ('get', 'is', 'has', 'can', 'count', 'calculate', 'find')

# ---------------------------------------------------------------------------
# Curated labels: key -> (title, desc, group)
# Lookup order: LINE_LABELS[(file, line)] → LABELS["seq:call"] → LABELS[call].
# ---------------------------------------------------------------------------

LABELS = {
    # ── Game.doTurn — the turn rollover ────────────────────────────────────
    'game:halveRecentHumanAttacks': (
        'Combat heat decays',
        'The recent-human-attacks counter is halved (it stretches multiplayer turn timers while fighting is hot).',
        'world'),
    'game:doOccurrences': (
        'New Occurrences may start',
        'Every Occurrence (in shuffled order) rolls its start chance and picks a target tile; the tile owner may get an occurrence-ready Event first.',
        'world'),
    'game:adjustYieldPrice': (
        'Market prices drift',
        'Each yield\'s price moves one tick per point of built-in demand, then the turn\'s price is recorded for the history graph.',
        'economy'),
    'game:doTurn': (
        'Every tile updates',
        'Pillage timers, abandoned construction, resource regrowth, vegetation growth and spread, tribal camp raids — the per-tile sequence below.',
        'world'),
    'game:doBorderFill': (
        'Borders fill in',
        'Rural pockets fully surrounded by urban tiles are claimed, and pending city-territory expansion tiles are assigned to their owners.',
        'world'),
    'game:doTradeTurn': (
        'Trade deals expire',
        'Each player\'s trade agreements whose duration has run out are removed.',
        'diplomacy'),
    'game:doTributeTurn': (
        'Tribute deals expire',
        'Each player\'s tribute arrangements whose duration has run out are removed.',
        'diplomacy'),
    'game:doWarScores': (
        'War scores decay',
        'Every team-vs-team and tribe-vs-team war score loses 5% (×19/20).',
        'diplomacy'),
    'game:doReligionSpread': (
        'Religions spread',
        'Each founded religion rolls its spread chance; on success it spreads to one more city.',
        'religion'),
    'game:doReligionHead': (
        'Religion heads update',
        'Each religion re-evaluates which character should be its head.',
        'religion'),
    'game:doReligionFound': (
        'New religions may be founded',
        'Religions whose prerequisites are now met get founded in the highest-scoring eligible city.',
        'religion'),
    'game:updateCharacterOpinionAll': (
        'Character opinions refresh',
        'Every player recomputes what each character thinks of them.',
        'opinion'),
    'game:updateReligionOpinionAll': (
        'Religion opinions refresh',
        'Every player recomputes each religion\'s opinion of them.',
        'opinion'),
    'game:updateFamilyOpinionAll': (
        'Family opinions refresh',
        'Every player recomputes each family\'s opinion of them.',
        'opinion'),

    # ── Player.doTurn wrapper ───────────────────────────────────────────────
    'player:processTurn': (
        'Turn-start processing',   # replaced by the inlined sequence below
        '', 'bookkeeping'),
    'player:updateHistoryRates': (
        'Graphs record turn rates',
        'Military power, yield rates, family and religion opinion, victory points and legitimacy are logged for this turn\'s graphs.',
        'bookkeeping'),
    'player:doDecisions': (
        'Leftover decisions auto-resolve',
        'Decisions still pending from your previous turn are resolved by the AI before you regain control.',
        'events'),
    'player:doAutomatedCityBuilds': (
        'Automated cities pick builds',
        'Cities set to auto-manage choose what to produce.',
        'cities'),
    'player:doUnitMoveQueue': (
        'Queued unit orders execute',
        'Units with queued move-to / build-road orders carry them out (cancelled if the path is gone).',
        'units'),
    'player:updateHistoryTotals': (
        'Graphs record totals',
        'Cumulative yield totals are logged for the graphs.',
        'bookkeeping'),
    'player:doVictory': (
        'Victory check',
        'Victory conditions, defeats and game-over states are evaluated.',
        'bookkeeping'),
    'player:doEnemyPlayers': (
        'AI advisor caches refresh',
        'For human players: enemy lists, attack-target suggestions and new-city-site hints are recomputed for the UI.',
        'bookkeeping'),

    # ── Player.processTurn — the meat of turn start ────────────────────────
    'player_process:doRebelProb': (
        'Cities roll for rebels',
        'Each city (after the early-game grace period) rolls its rebel probability and may spawn a rebel unit.',
        'cities'),
    'player_process:doPlayerTurn': (
        'Owned tiles grant unit XP',
        'Units standing on XP-granting improvements (or adjacent to them) gain XP; half-elapsed pillage repairs are logged.',
        'units'),
    'player_process:incrementLeaderStat': (
        'Reign counters tick',
        'The leader\'s Years Reigned stat increments (plus Years as Regent for regents).',
        'characters'),
    'player_process:sellYield': (
        'Orders above the cap are sold',
        'Any Orders past your maximum are automatically sold for money.',
        'economy'),
    'player_process:doProjectSpread': (
        'Spreading projects propagate',
        'Projects with a spread chance roll to copy themselves from a city that has them to another of your cities.',
        'cities'),
    'player_process:doLuxuryTurn': (
        'Luxury assignments verified',
        'Each luxury resource\'s city and family assignments are re-checked; over-assigned luxuries are pulled back.',
        'economy'),
    'player_process:doMemoryTurn': (
        'Opinion memories fade',
        'Expired memories (timed opinion modifiers from past actions) are removed.',
        'diplomacy'),
    'player_process:doFamilyControl': (
        'Family supremacy check',
        'If another family has overtaken the dominant one, the family-supremacy event fires.',
        'characters'),
    'player_process:doTribeTurn': (
        'Captured tribal cities flip',
        'Tribal cities you finished capturing last turn now transfer (or raze) — see City Capture Mechanics; the per-city capture sequence below.',
        'cities'),
    'player_process:incrementGoalYieldsProduced': (
        'City output tallies toward goals',
        'Each city\'s positive yield output is added to the yields-produced counters that ambitions and quests track.',
        'goals'),
    'player_process:doShortfall': (
        'Shortfall projects forced',
        'While a shortfall yield would go negative, the best-suited city is forced onto its culture\'s shortfall project.',
        'economy'),
    'player_process:autoChooseResearch': (
        'Empty research slot auto-filled',
        'If nothing is being researched, the AI\'s best tech is slotted temporarily so incoming Science isn\'t wasted.',
        'tech'),
    'player_process:processYield': (
        'Global yields bank',
        'Non-city income plus every city\'s global yields (Money, Science, Civics, Training, Orders) hit the stockpiles — Science goes straight into the current tech and can complete it here.',
        'tech'),
    'player_process:doResearch': (
        'Research progresses / tech completes',
        'The Science stockpile flushes into the current tech; when progress reaches the cost, the tech is acquired on the spot.',
        'tech'),
    'player_process:clearTechResearching': (
        'Auto-picked tech un-selected',
        'If research was auto-slotted two steps ago, the choice is cleared again so a human can pick freely.',
        'tech'),
    'player_process:doDebts': (
        'Debts force auto-sales',
        'While money is negative, goods are sold automatically; if still short, money resets to zero.',
        'economy'),
    'player_process:setYieldStockpile': (
        'Negative stockpiles clamp to zero',
        'Any yield stockpile still below zero after debts is set to 0.',
        'economy'),
    'player_process:doBounceUnits': (
        'Stranded units bounce',
        'Units standing where they can no longer be (e.g. lost territory) are pushed to a valid tile — or killed if there is none.',
        'units'),
    'player_process:doTurn': (
        'Units process',
        'Each of your units takes its upkeep turn (wake checks, timers, work, healing, XP) — the per-unit sequence below.',
        'units'),
    'player_process:makeDead': (
        'Doomed characters may die',
        'Each character with the Doomed trait rolls the death chance and can die now.',
        'characters'),
    'player_process:doTraitProbDelay': (
        'Delayed trait probabilities resolve',
        'Traits queued by events with a delayed probability roll now.',
        'characters'),
    'player_process:doRandomTraitDelay': (
        'Delayed random traits resolve',
        'Random traits queued with a delay are assigned now.',
        'characters'),
    'player_process:doRandomCharacterRelationshipDelay': (
        'Delayed relationships resolve',
        'Pending random character relationships (rivalries, friendships) are assigned now.',
        'characters'),
    'player_process:addFamilyCharacters': (
        'Families replenish',
        'Families short on adults or children (relative to the cities they hold) spawn new characters.',
        'characters'),
    'player_process:doRetirements': (
        'Old royals retire',
        'If the royal roster exceeds roughly year/25 + 5, the character furthest down the succession retires; the leader, heirs and family heads are always un-retired.',
        'characters'),
    'player_process:updateFamilyHead': (
        'Family heads update',
        'Each family re-evaluates who leads it.',
        'characters'),
    'player_process:doFamilyReligion': (
        'Families may adopt religions',
        'From turn 10, each family (staggered, every 4 turns) adopts whichever religion is most common among its members.',
        'characters'),
    'player_process:doFamilyTurnsNoLeader': (
        'Family neglect counters tick',
        'Every family the current leader does not belong to increments its turns-without-a-leader counter.',
        'characters'),
    'player_process:doTribeDiplomacy': (
        'Tribes run diplomacy at you',
        'Each tribe evaluates its per-player diplomacy (offers, demands, attitude shifts).',
        'diplomacy'),
    'player_process:doPlayerDiplomacy': (
        'AI player diplomacy',
        'AI players (only) evaluate diplomacy toward every other player — humans are considered first.',
        'diplomacy'),
    'player_process:doEventTriggers': (
        'Story event rolls',
        'Event-class probability rolls fire first, then up to the per-turn cap of new-turn events, then event-level bonus rolls.',
        'events'),
    'player_process:updateTileEventTimers': (
        'Tile event timers tick',
        'Per-tile event timers count down and expire.',
        'events'),
    'player_process:doBonus': (
        'AI free-ambition roll',
        'AIs that simulate ambitions occasionally bank a finished-ambition credit to keep pace with humans.',
        'goals'),
    'player_process:doMissionTurn': (
        'Missions complete',
        'Missions whose duration has elapsed resolve — deliberately after character turns, so mid-event state changes (e.g. a suitor marrying) invalidate cleanly.',
        'court'),
    'player_process:doAllOccurrenceEffects': (
        'Occurrence effects apply',
        'All active Occurrences apply their per-player effects and tile changes to you.',
        'events'),
    'player_process:updateEventLinks': (
        'Event links expire',
        'Event-chain links past their turn limit (or marked immediate) are removed.',
        'events'),
    'player_process:updateGoals': (
        'Goals re-evaluate',
        'All ambition and quest progress is recomputed against the new game state.',
        'goals'),
    'player_process:removeQuest': (
        'Quests time out',
        'Unfinished quests with zero turns left are removed.',
        'goals'),
    'player_process:removeAmbition': (
        'Ambitions time out',
        'Unfinished ambitions with zero turns left are removed (failed).',
        'goals'),
    'player_process:updateDecisions': (
        'Stale decisions pruned',
        'Pending decisions that are no longer valid are removed.',
        'events'),
    'player_process:updatePings': (
        'Map pings expire',
        'Old map pins and reminders are cleared or re-announced.',
        'bookkeeping'),
    'player_process:doAmbitions': (
        'New ambition may be offered',
        'If you have a free ambition slot and nothing pending, threshold-goal offers fire first, then a standard ambition offer can roll.',
        'goals'),

    # ── Tile.doTurn ─────────────────────────────────────────────────────────
    'tile:changeImprovementPillageTurns': (
        'Pillage timer ticks',
        'A pillaged improvement counts down one turn; at zero it is destroyed outright.',
        'world'),
    'tile:changeImprovementBuildTurnsLeft': (
        'Abandoned construction regresses',
        'An unfinished improvement with no worker on it loses one turn of progress (back up to its original cost).',
        'world'),
    'tile:foundCity': (
        'Trade outpost founds a city',
        'On an active city site, a player whose trade-outpost timer just expired founds a free city there.',
        'world'),
    'tile:doTribeTurn': (
        'Tribal camps act',
        'A camp may launch a raid at a nearby city (raid-prob roll, blockable by the tribe-raid event), or — for non-diplomacy tribes — convert to a neighboring tribe.',
        'tribes'),
    'tile:incrementImprovementDevelopTurns': (
        'Improvements develop',
        'Improvements that upgrade over time tick their develop counter.',
        'world'),
    'tile:changeImprovementUnitTurns': (
        'Unit-spawning improvements tick',
        'Improvements that periodically produce units count down.',
        'world'),
    'tile:addImprovementUnit': (
        'Improvement spawns its unit',
        'When the spawn timer hits zero it resets and the improvement\'s unit appears.',
        'world'),
    'tile:clearHarvestTurn': (
        'Harvested resources regrow',
        'A harvested resource rolls to come back; odds improve every turn after the first two.',
        'world'),
    'tile:setVegetation': (
        'Vegetation grows',
        'Regrowing vegetation rolls to advance a stage; city regrowth modifiers apply.',
        'world'),
    'tile:decayRecentAttacks': (
        'Tile combat memory fades',
        'Recent-attack heat on the tile decays (paused while a damaged city or settlement sits on it).',
        'world'),

    # ── Tile.doPlayerTurn ───────────────────────────────────────────────────
    'tile_player:increaseXP': (
        'Improvement XP awarded',
        'Each promotable unit on this tile gains the XP its improvement (and adjacent friendly improvements) grant per turn.',
        'units'),

    # ── Tribe.doTurn ────────────────────────────────────────────────────────
    'tribe:updateLeader': (
        'Tribal leader replaced if dead',
        'If the tribe\'s leader has died, a new adult leader character is generated.',
        'tribes'),
    'tribe:updateReligion': (
        'Tribal religion drifts',
        'The tribe adopts whichever world religion is most represented among related characters.',
        'tribes'),
    'tribe:convertToRaider': (
        'Site-less tribes turn raider',
        'If the tribe has no settlements left (and no player ally), each unit rolls 1-in-10 to become raiders targeting the best nearby city.',
        'tribes'),

    # ── City.doPlayerTurn ───────────────────────────────────────────────────
    'city:changeDamage': (
        'City heals',
        'A damaged city heals a percentage of its max HP.',
        'cities'),
    'city:changeAssimilateTurns': (
        'Assimilation progresses',
        'A city still assimilating ticks down at its culture\'s assimilation rate.',
        'cities'),
    'city:doDistantRaidTurn': (
        'Distant raid roll',
        'From the raid start turn, the city rolls difficulty-based odds to spawn a raider party on a distant valid tile aimed at it.',
        'cities'),
    'city:pushBuildProjectFirst': (
        'Default project fills an empty queue',
        'A city building nothing is given its culture\'s default project so production is never wasted.',
        'cities'),
    'city:changeYieldProgress': (
        'City yields accrue',
        'Local yields add to their progress bars; global yields are handed up to the player to bank after all cities run.',
        'cities'),
    'city:changeCurrentBuildProgress': (
        'Production applies to the build',
        'This turn\'s production (plus stored overflow) goes into the current build.',
        'cities'),
    'city:finishBuild': (
        'Build completes',
        'If the current build\'s cost is now met, it finishes — the unit spawns / building, project or specialist takes effect immediately.',
        'cities'),
    'city:decayBuildQueue': (
        'Queued progress decays',
        'Partial progress on builds sitting in the queue (not currently first) decays by a percentage.',
        'cities'),
    'city:verifyBuildProjects': (
        'Invalid builds pruned',
        'Queued projects, specialists and units that are no longer legal are removed.',
        'cities'),

    # ── City.doTribeTurn (capture / tribal city) ───────────────────────────
    'city_tribe:changeCaptureTurns': (
        'Capture counter ticks',
        '+1 while a unit is occupying the city; the city flips at its capture threshold (see City Capture Mechanics).',
        'cities'),
    'city_tribe:changeDamage': (
        'Tribal city heals',
        'An un-besieged tribal city heals a percentage of max HP.',
        'tribes'),
    'city_tribe:doTribeImprovements': (
        'Camp may add an improvement',
        'Diplomacy-capable tribes roll to add a random improvement to the city.',
        'tribes'),
    'city_tribe:doTribeUnits': (
        'Camp may train a unit',
        'The tribal city rolls to produce a tribal unit nearby.',
        'tribes'),

    # ── Unit.doTurn ─────────────────────────────────────────────────────────
    'unit:setPass': (
        'Pass order clears',
        'A unit told to pass last turn becomes active again.',
        'units'),
    'unit:setSleep': (
        'Sleepers wake near hostiles',
        'A sleeping (non-hidden) unit wakes if a hostile unit is adjacent.',
        'units'),
    'unit:setSentry': (
        'Sentry breaks on contact',
        'A unit on sentry wakes if a hostile unit enters sentry range.',
        'units'),
    'unit:setMarch': (
        'March order clears',
        'March status resets at turn start.',
        'units'),
    'unit:checkEffectUnitTurns': (
        'Timed unit effects tick',
        'Temporary unit effects count down and expire (possibly chaining into a follow-up effect).',
        'units'),
    'unit:applyEffectUnitTurns': (
        'Territory effects may apply',
        'City-territory effects roll their chance to put a timed effect on the unit standing there.',
        'units'),
    'unit:changeImprovementBuildTurnsLeft': (
        'Workers advance construction',
        'A unit improving its tile progresses the build one turn (consuming its action); completion is announced.',
        'units'),
    'unit:reduceCooldown': (
        'Cooldown ticks down',
        'An active cooldown (attacked, stunned, trade…) decreases by one.',
        'units'),
    'unit:changeFortifyTurns': (
        'Fortification deepens',
        'A fortifying unit outside a city gains a fortify turn (reset to 0 inside cities).',
        'units'),
    'unit:changeFormationTurns': (
        'Formation deepens',
        'A unit holding formation outside a city gains a formation turn (reset to 0 inside cities).',
        'units'),
    'unit:setTempHiddenTurns': (
        'Hidden countdown',
        'Temporarily hidden units tick toward being revealed.',
        'units'),
    'unit:harvestResource': (
        'Auto-harvest fires',
        'A unit set to auto-harvest collects the resource it is standing on if it can.',
        'units'),
    'unit:increaseXP': (
        'XP from leaders and effects',
        'Generals and explorers grant their rating XP; player effects add per-turn (and idle) XP.',
        'units'),
    'unit:changeDamageText': (
        'Healing and attrition apply',
        'Effect-based heal/damage plus idle healing (if the unit did nothing and can heal here); then terrain and height attrition.',
        'units'),
    'unit:heal': (
        'Auto-heal action',
        'A unit on auto-heal spends its turn healing while still damaged (cleared once it cannot).',
        'units'),
    'unit:doCaravanMission': (
        'Caravans advance',
        'A caravan with a mission target moves toward that capital and completes its mission on arrival. (May remove the unit.)',
        'units'),
    'unit:stopRaid': (
        'Raids on dead teams end',
        'Raiders whose target team has been eliminated stop raiding and convert to barbarians.',
        'units'),

    # ── Character.doTurn ────────────────────────────────────────────────────
    'character:doTurnYear': (
        'Yearly tick (the character\'s "birthday")',
        'Runs only when turn % year-divisions matches the character\'s ID: aging, death rolls and life events — the sequence below.',
        'characters'),
    'character:removeTrait': (
        'Expiring traits removed',
        'Traits with a turn limit (or marked remove-always) fall off; a lose-trait event may fire instead of the plain notice.',
        'characters'),
    'character:doOccurrenceTrait': (
        'Occurrence traits roll',
        'Active Occurrences can inflict traits on the character, and strip them when the Occurrence ends.',
        'characters'),
    'character:increaseXP': (
        'Character XP accrues',
        'XP per turn from traits, a council seat, and city governorship.',
        'characters'),

    # ── Character.doTurnYear ────────────────────────────────────────────────
    'character_year:addTrait': (
        'Death roll → Doomed for leaders',
        'If a death trait fires, a leader gains Doomed instead of dying instantly (a one-year warning); anyone else dies now.',
        'characters'),
    'character_year:makeDead': (
        'Death roll resolves',
        'A non-leader (or already-Doomed) character whose death trait fired dies here.',
        'characters'),
    'character_year:makeInfertile': (
        'Infertility check',
        'Past maximum fertile age (hard cutoff with margin, or per-year odds), the character becomes infertile.',
        'characters'),
    'character_year:checkLifeEvent': (
        'One life event',
        'At most one fires, in priority order: new-year character event, trait gain, trait loss, archetype, first strength/weakness, birth, adult trait, rating change, marriage offer, religion, (AI) adoption.',
        'characters'),
    'character_year:assignNickname': (
        'Nickname roll',
        'A small chance the character picks up a nickname.',
        'characters'),
    'character_year:doEventTrigger': (
        'Character event rolls',
        'Event classes with a per-character probability may fire, then the new-turn character event trigger runs.',
        'events'),
    'character_year:changeRating': (
        'AI ratings drift',
        'When events are off (AI autoplay), young successors gain random rating points instead of tutored growth.',
        'characters'),
}

# (file, line)-specific labels for calls that repeat with different meanings.
LINE_LABELS = {
    ('Player.cs', 16654): (
        'Training above the cap → Orders',
        'Excess Training converts into Orders at the TRAINING_PER_ORDER rate.',
        'economy'),
    ('Player.cs', 16674): (
        'Civics above the cap → Science',
        'Excess Civics converts into Science at the CIVICS_PER_SCIENCE rate.',
        'economy'),
    ('Player.cs', 16757): (
        'Non-leader characters take their turns',
        'Every living character except the leader runs the per-character sequence below.',
        'characters'),
    ('Player.cs', 16775): (
        'The leader goes last',
        'The leader\'s character turn runs after everyone else "so that other characters don\'t have life events that would invalidate the leader\'s events" (source comment).',
        'characters'),
    ('Player.cs', 16898): (
        'AI advisor caches refresh',
        'For human players: enemy lists, attack-target suggestions and new-city-site hints update for the UI.',
        'bookkeeping'),
    ('Player.cs', 16899): None,   # doAttackTargets — folded into 16898
    ('Player.cs', 16900): None,   # checkNewCitySites — folded into 16898
    ('Tile.cs',   11034): (
        'Vegetation grows',
        'Regrowing vegetation rolls to advance a stage (faster the longer it has been regrowing; city regrowth modifiers apply).',
        'world'),
    ('Tile.cs',   11056): (
        'Vegetation spreads',
        'An empty tile can catch vegetation from an adjacent tile via that vegetation\'s spread roll.',
        'world'),
    ('Unit.cs',   5792): (
        'General grants XP',
        'A promotable unit led by a general gains XP from the general\'s ratings.',
        'units'),
    ('Unit.cs',   5800): (
        'Explorer grants XP',
        'A promotable unit led by an explorer gains XP from the explorer\'s ratings.',
        'units'),
    ('Unit.cs',   5838): (
        'Healing applies',
        'Effect heal/damage plus idle healing (only if the unit took no action and can heal on this tile); a fully-healed sleeper wakes.',
        'units'),
    ('Unit.cs',   5865): (
        'Terrain attrition',
        'Damaging terrain and heights hurt the unit standing there.',
        'units'),
    ('Unit.cs',   5894): (
        'Player-effect XP',
        'Per-turn XP (plus idle XP) from player-wide effects applies to promotable units.',
        'units'),
    ('Character.cs', 8317): (
        'Death roll → leaders gain Doomed',
        'If a death trait fires for a leader, they gain Doomed instead of dying instantly — a one-year warning.',
        'characters'),
    ('Character.cs', 8326): (
        'Death roll resolves',
        'For anyone else (or an already-Doomed leader), a fired death trait kills the character now.',
        'characters'),
    ('Character.cs', 8336): (
        'Old generals retire',
        'A general at retirement age (who is not the leader) gains the Retired General trait and leaves the unit.',
        'characters'),
    ('Character.cs', 8367): (
        'Character event-class rolls',
        'Each event class with a per-character probability may fire an event starring this character.',
        'events'),
    ('Character.cs', 8372): (
        'New-turn character event',
        'The generic new-turn character event trigger runs for this character.',
        'events'),
}

# Curated steps for gameplay that hides inside an `if (...)` condition and is
# therefore not a captured call statement. Inserted in line order.
EXTRA_STEPS = {
    'character': [
        {
            'call': 'doEventTrigger',
            'line': 7538,
            'loop': None,
            'cond': 'on the turn the character becomes an adult',
            'title': 'Coming of age',
            'desc': 'A character reaching adult age fires the adulthood event (or just a log entry if no event takes).',
            'group': 'characters',
        },
    ],
}

# ---------------------------------------------------------------------------
# Loop / condition prettifiers
# ---------------------------------------------------------------------------

LOOP_DESCS = [
    (r'Math\.Abs\(iDemand\)',                'per point of demand'),
    (r'eLoopYield|YieldType',                'for each yield'),
    (r'getNumTiles\(\)',                     'for each tile on the map'),
    (r'eLoopTribe|TribeType',                'for each tribe'),
    (r'eLoopPlayer|getNumPlayers|PlayerType','for each player'),
    (r'getCities\(\)|iCityID|cityListScoped','for each city'),
    (r'getNumUnits|getUnits\(\)\.Count',     'for each unit (reverse order)'),
    (r'getUnits\(\)|unitListScope|UnitType eLoopUnit', 'for each unit'),
    (r'charListScoped|iLoopCharacter|Character pLoopCharacter', 'for each living character'),
    (r'getFamilies\(\)|FamilyType',          'for each family'),
    (r'ReligionType',                        'for each religion'),
    (r'traitListScoped|TraitType',           'for each trait'),
    (r'eLoopEventClass|EventClassType',      'for each event class'),
    (r'getNumGoals',                         'for each goal (reverse)'),
    (r'getMemoryList',                       'for each memory'),
    (r'getTradeList',                        'for each trade deal'),
    (r'getTributeList',                      'for each tribute'),
    (r'getEffectUnitExpireTurns',            'for each timed effect'),
    (r'getActiveEffectCity|EffectCityType',  'for each active city effect'),
    (r'aiShuffledOccurrences|OccurrenceType|getNumOccurrences', 'for each occurrence'),
    (r'DirectionType',                       'for each direction'),
    (r'AchievementType',                     'for each achievement'),
    (r'TeamType',                            'for each team'),
    (r'EffectPlayerType',                    'for each player effect'),
    (r'getTiles\(\)',                        'for each owned tile'),
    (r'azMissions|getMissionList',           'for each mission'),
    (r'getQueueList',                        'while orders are queued'),
    (r'ProjectType',                         'for each project'),
    (r'ResourceType',                        'for each resource'),
    (r'getEventLinkList',                    'for each event link'),
    (r'getDecisionList',                     'for each pending decision'),
    (r'getEventTimers|timesListScoped',      'for each tile event timer'),
    (r'getSuccession\(\)',                   'for each successor'),
    (r'aiUnits',                             'for each tribal unit'),
    (r'iLoopTile',                           'for each tile in range'),
    (r'EffectUnitType|maaiTerritoryEffectUnit', 'for each territory effect'),
]

COND_REWRITES = [
    (r'pLoopTile\s*!=\s*null', None),
    (r'pLoopUnit\s*!=\s*null', None),
    (r'pCharacter\s*!=\s*null', None),
    (r'!\s*isFirstTurnProcessing\(\)', 'skipped on the player\'s very first turn'),
    (r'!\s*player\(\)\.isFirstTurnProcessing\(\)', 'owned; skipped on the first turn'),
    (r'isTribeAlive', 'tribe is alive'),
    (r'!\s*isDead\(\)', 'player alive'),
    (r'isFounded\(\)\s*&&\s*hasLeader\(\)', 'nation founded, leader alive'),
    (r'^bFinished$', 'cost met'),
    (r'^bAutoResearch$', 'research was auto-picked'),
    (r'getYieldStockpile\(eLoopYield\)\s*<\s*0', 'a stockpile is below zero'),
    (r'iExtra\s*>\s*0', 'over the cap'),
    (r'isUnitCapturingCity', 'a unit is capturing the city'),
    (r'getAssimilateTurns\(\)\s*>\s*0', 'still assimilating'),
    (r'isDamaged\(\)', 'damaged'),
    (r'hasTraitDoomed\(\).*randomPercent', 'Doomed and the death roll hits'),
    (r'isImprovingTile', 'unit is working its tile'),
    (r'adjacentToHostileUnit', 'a hostile unit is adjacent'),
    (r'hasHostileUnit', 'a hostile unit is in range'),
    (r'!hasBuild\(\)', 'nothing in the build queue'),
    (r'isLeader\(\)\s*&&\s*!hasTraitDoomed', 'leader, not yet Doomed'),
    (r'isUnitGeneral.*GENERAL_RETIRE_AGE', 'a general at retirement age'),
    (r'pLoopCharacter\.isLeader|^isLeader\(\)$', 'the leader'),
    (r'eDeathTrait != TraitType\.NONE', 'a death trait fired'),
    (r'checkMakeInfertile', 'past fertile age / failed the roll'),
    (r'randomPercent\(.*NICKNAME_PROB\)', 'small random chance'),
    (r'canDoEvents\(\)', 'events enabled'),
    (r'isCitySiteActive', 'tile is an active city site'),
    (r'pFoundPlayer != null', 'an outpost timer expired here'),
    (r'canDevelopImprovement', 'improvement can develop'),
    (r'isHarvested\(\)\s*&&\s*hasResource', 'resource was harvested'),
    (r'hasVegetation\(\)$', 'tile has vegetation'),
    (r'!hasVegetation\(\)', 'tile is bare'),
    (r'shouldDecayRecentAttacks', 'no damaged city/settlement here'),
    (r'hasActiveImprovement', 'improvement is active'),
    (r'hasImprovement\(\)', 'tile has an improvement'),
    (r'getImprovementPillageTurns\(\)\s*>\s*0', 'improvement is pillaged'),
    (r'getImprovementBuildTurnsLeft\(\)\s*>\s*0', 'construction unfinished'),
    (r'countUnitsImproving\(\)\s*==\s*0', 'no worker present'),
    (r'getImprovementUnitTurns\(\)\s*>\s*0', 'spawn timer running'),
    (r'!hasSites\(\).*!hasPlayerAlly', 'tribe has no sites and no ally'),
    (r'!tribe\(\)\.mbDiplomacy', None),
    (r'randomNext\(10\)\s*==\s*0', '1-in-10 roll'),
    (r'isPass\(\)', 'unit passed'),
    (r'isSleep\(\)', 'unit is sleeping'),
    (r'isSentry\(\)', 'unit is on sentry'),
    (r'isMarch\(\)', 'unit is marching'),
    (r'isFortify\(\)', 'unit is fortifying'),
    (r'isFormation\(\)', 'unit holds formation'),
    (r'isTempHidden', 'unit is temporarily hidden'),
    (r'isAutoHarvest', 'auto-harvest is on'),
    (r'isAutoHeal', 'auto-heal is on'),
    (r'hasGeneral\(\)', 'unit has a general'),
    (r'hasExplorer\(\)', 'unit has an explorer'),
    (r'getHP\(\)\s*>\s*0', 'unit alive'),
    (r'iHeal\s*!=\s*0', 'net heal/damage nonzero'),
    (r'isPromotable', 'unit is promotable'),
    (r'isRaidTeam.*!.*isTeamAlive', 'raid target team eliminated'),
    (r'getCapturePlayer\(\)\s*==\s*getPlayer\(\)\s*&&.*isTribe', 'tribal city you finished capturing'),
    (r'!\s*pLoopPlayer\.isAIAutoPlay|!isAIAutoPlay\(\)', 'human-controlled'),
    (r'canSimulateAmbitions', 'AI that simulates ambitions'),
    (r'turnTimer\(\)\.mbOff', 'no turn timer'),
    (r'iOutput\s*>\s*0', 'output positive'),
    (r'iXP\s*>\s*0', 'XP positive'),
    (r'pBestCity != null', 'a city qualifies'),
    (r'eBestUnit != UnitType\.NONE', 'a unit type qualifies'),
    (r'eBestReligion != ReligionType\.NONE', 'a religion qualifies'),
    (r'eImprovement != ImprovementType\.NONE', 'an improvement qualifies'),
    (r'!\(pLoopData\.mbFinished\).*isQuest', 'unfinished quest'),
    (r'!\(pLoopData\.mbFinished\).*isAmbition', 'unfinished ambition'),
    (r'getTurnsLeft\(.*\)\s*==\s*0', 'no turns left'),
    (r'eDefaultProject != ProjectType\.NONE', 'culture has a default project'),
    (r'pCity != null', 'a target city exists'),
    (r'iValue\s*>\s*0', 'chance positive'),
    (r'!hasEffectUnit', 'effect not already on the unit'),
    (r'eImprovementFinished != ImprovementType\.NONE', 'an improvement just finished here'),
    (r'!\(pTile\.improvement\(\)\.mbWonder\)', 'not a wonder'),
    (r'hasCaravanMissionTarget', 'caravan has a mission target'),
    (r'getAge\(\)\s*==\s*.*ADULT_AGE', 'on reaching adult age'),
    (r'getAge\(\)\s*==\s*.*TUTORS_AGE', 'on reaching tutors age'),
    (r'hasPlayer\(\)$', 'owned by a player'),
    (r'getMoneyWhole\(\)\s*<\s*0', 'money is negative'),
    (r'mbShortfall', 'yield can shortfall'),
    (r'getLuxuryCount.*<\s*0', 'luxury over-assigned'),
    (r'game\(\)\.isCharacters\(\)', 'characters enabled'),
    (r'getTurn\(\)\s*%\s*4', 'every 4th turn per family'),
    (r'randomNext\(.*AI_FREE_AMBITION_ROLL\)\s*==\s*0', 'random roll'),
    (r'iStartChance\s*>\s*0\s*&&\s*randomPercent', 'start chance hits'),
    (r'isReligionFounded.*!.*mbNoSpread', 'founded, can spread'),
    (r'randomPercent\(getReligionSpread', 'spread roll hits'),
    (r'canSellYield', 'Orders over the cap'),
    (r'pLeader != null', 'the leader, after everyone else'),
    (r'getBonusCount\(.*FINISHED_AMBITION', 'random roll hit; below the ambition cap'),
    (r'getImprovementBuildTurnsLeft\(\)\s*<\s*getImprovementBuildTurnsOrig', 'progress was made, no worker'),
    (r'!\s*skipImprovementUnitTurns', 'spawning not paused'),
    (r'getImprovementUnitTurns\(\)\s*==\s*0', 'timer reached zero'),
    (r'randomNext\(Math\.Max\(1,\s*\(iRoll - iTurns\)\)\)\s*==\s*0', 'the roll hits (odds improve over time)'),
    (r'randomNext\(iRoll\)\s*==\s*0', 'the roll hits'),
    (r'!\s*infos\(\)\.yield\(eLoopYield\)\.mbGlobal|mbGlobal', 'local yields only'),
    (r'mbDiplomacy', 'diplomacy-capable tribe'),
    (r'randomPercent\(iProb\)', 'probability roll hits'),
    (r'zYield\.iRate\s*!=\s*0', None),
    (r'isFortifyMax|isFormationMax', 'not yet at maximum'),
    (r'canHarvestResource', 'harvest possible here'),
    (r'^bWasDamaged', 'was damaged (or is taking damage)'),
    (r'canHeal\(pTile.*getIdleHealHP', 'still damaged beyond idle healing'),
    (r'pTile\.getTerrain\(\)\s*!=\s*TerrainType\.NONE', None),
    (r'getYearDivisions', "on the character's year turn"),
    (r'randomNext\(2\)\s*==\s*0', 'coin flip'),
    (r'^bRemove$', 'turn limit reached'),
    (r'iExtraXP\s*!=\s*0', None),
]


def loop_desc(header):
    for pat, txt in LOOP_DESCS:
        if re.search(pat, header):
            # reverse-iteration hint
            if txt and 'reverse' not in txt and re.search(r'Count\s*-\s*1.*--\s*i|\bi--|--i\b', header):
                return txt + ' (reverse)'
            return txt
    return 'loop'


def cond_desc(cond):
    cond = cond.strip()
    for pat, txt in COND_REWRITES:
        if re.search(pat, cond):
            return txt  # may be None (drop)
    # fallback: cleaned raw code
    c = cond
    for junk in ('infos().Globals.', 'infos().', 'game().', 'player().'):
        c = c.replace(junk, '')
    c = re.sub(r'\s+', ' ', c).strip()
    if len(c) > 64:
        c = c[:61] + '…'
    return 'if ' + c


def prettify(name):
    """fallback title for unlabeled calls: doFooBarBaz -> 'Foo bar baz'."""
    n = re.sub(r'^(do|update|check)(?=[A-Z])', '', name)
    words = re.findall(r'[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])', n)
    return ' '.join([words[0].capitalize()] + [w.lower() for w in words[1:]]) if words else name


# ---------------------------------------------------------------------------
# C# mini-parser
# ---------------------------------------------------------------------------

def clean_csharp(text):
    """Blank out comments and string/char literals, preserving line structure."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        if c == '/' and nxt == '/':
            while i < n and text[i] != '\n':
                out[i] = ' '
                i += 1
        elif c == '/' and nxt == '*':
            out[i] = out[i + 1] = ' '
            i += 2
            while i + 1 < n and not (text[i] == '*' and text[i + 1] == '/'):
                if text[i] != '\n':
                    out[i] = ' '
                i += 1
            if i + 1 < n:
                out[i] = out[i + 1] = ' '
                i += 2
        elif c == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == '\\':
                    out[i] = ' '
                    i += 1
                    if i < n and text[i] != '\n':
                        out[i] = ' '
                    i += 1
                    continue
                if text[i] != '\n':
                    out[i] = ' '
                i += 1
            i += 1
        elif c == "'":
            j = i + 1
            while j < n and text[j] != "'":
                if text[j] == '\\':
                    j += 1
                j += 1
            for k in range(i + 1, min(j, n)):
                if text[k] != '\n':
                    out[k] = ' '
            i = j + 1
        else:
            i += 1
    return ''.join(out)


def find_function(clean_lines, sig_regex, expect_line, file_rel):
    pat = re.compile(sig_regex)
    best = None
    for idx, ln in enumerate(clean_lines, start=1):
        if pat.search(ln):
            if best is None or abs(idx - expect_line) < abs(best - expect_line):
                best = idx
    if best is None:
        raise SystemExit(f'[turn_order] signature not found in {file_rel}: {sig_regex}')
    if abs(best - expect_line) > 80:
        print(f'[turn_order] WARNING: {file_rel} {sig_regex} found at {best}, '
              f'expected ~{expect_line} (patch drift?)', file=sys.stderr)
    return best


def body_range(clean_lines, sig_line):
    """Return (first_line, last_line) of the body inside the function braces."""
    depth = 0
    started = False
    for lineno in range(sig_line, len(clean_lines) + 1):
        for ch in clean_lines[lineno - 1]:
            if ch == '{':
                depth += 1
                if not started:
                    started = True
                    start = lineno
            elif ch == '}':
                depth -= 1
                if started and depth == 0:
                    return (start, lineno)
    raise SystemExit(f'[turn_order] unbalanced braces from line {sig_line}')


STMT_KEYWORDS = ('if', 'for', 'foreach', 'while', 'switch', 'return', 'break',
                 'continue', 'using', 'else', 'do', 'case', 'default', 'throw',
                 'try', 'catch', 'finally', 'goto', 'void', 'new')


def call_from_statement(stmt):
    """Extract (receiver, method) of the outermost trailing call, or None."""
    stmt = stmt.strip()
    if not stmt.endswith(')'):
        return None
    depth = 0
    open_idx = -1
    for i in range(len(stmt) - 1, -1, -1):
        c = stmt[i]
        if c == ')':
            depth += 1
        elif c == '(':
            depth -= 1
            if depth == 0:
                open_idx = i
                break
    if open_idx <= 0:
        return None
    m = re.search(r'([A-Za-z_]\w*)\s*$', stmt[:open_idx])
    if not m:
        return None
    name = m.group(1)
    recv = stmt[:m.start()].rstrip()
    recv = recv.rstrip('?').rstrip('.')
    # strip leading declarations/assignment: "bool b =", "Unit pUnit ="
    if '=' in recv:
        recv = recv.split('=')[-1].strip()
    return recv, name


def extract_sequence(seq_key, sources, unlabeled):
    file_rel, sig_regex, expect = SEQUENCES[seq_key]
    clean_lines, raw_lines = sources[file_rel]
    sig_line = find_function(clean_lines, sig_regex, expect, file_rel)
    b0, b1 = body_range(clean_lines, sig_line)

    steps = []
    stack = []          # block headers: {'kind','text'}
    cur = ''
    cur_line = None
    paren = 0

    def header_kind(hdr):
        h = hdr.strip()
        if h.startswith(('for', 'foreach', 'while')):
            return 'loop'
        if h.startswith('if') or h.startswith('else if'):
            return 'cond'
        if h == 'else':
            return 'else'
        return 'other'

    def header_inner(hdr):
        i = hdr.find('(')
        if i < 0:
            return hdr
        depth = 0
        for j in range(i, len(hdr)):
            if hdr[j] == '(':
                depth += 1
            elif hdr[j] == ')':
                depth -= 1
                if depth == 0:
                    return hdr[i + 1:j]
        return hdr[i + 1:]

    def emit(stmt, line):
        stmt = stmt.strip()
        if not stmt:
            return
        first = re.match(r'[A-Za-z_]\w*', stmt)
        if first and first.group(0) in STMT_KEYWORDS:
            if first.group(0) == 'return' and '(' in stmt:
                stmt = stmt[len('return'):].strip()
            elif first.group(0) in ('if', 'else'):
                return  # single-statement conditionals — context only
            else:
                return
        res = call_from_statement(stmt)
        if not res:
            return
        recv, name = res
        if name in SKIP_CALLS:
            return
        if recv and SKIP_RECEIVERS.search(recv):
            return
        if (file_rel, line) in SKIP_LINES:
            return
        in_labels = (f'{seq_key}:{name}' in LABELS or (file_rel, line) in LINE_LABELS)
        if not in_labels and name.startswith(QUERY_PREFIXES):
            return

        loops = [e for e in stack if e['kind'] == 'loop']
        conds = [e for e in stack if e['kind'] in ('cond', 'else')]
        loop = loop_desc(header_inner(loops[-1]['text'])) if loops else None
        cond = None
        if conds:
            e = conds[-1]
            cond = 'otherwise' if e['kind'] == 'else' else cond_desc(header_inner(e['text']))

        label = LINE_LABELS.get((file_rel, line), '__miss__')
        if label is None:
            return  # explicitly folded into a neighbor
        if label == '__miss__':
            label = LABELS.get(f'{seq_key}:{name}')
        if label is None:
            title, desc, group = prettify(name), '', 'misc'
            unlabeled.add(f'{seq_key}:{name} ({file_rel}:{line})')
        else:
            title, desc, group = label

        step = {
            'call': name,
            'recv': recv or None,
            'file': file_rel,
            'line': line,
            'loop': loop,
            'cond': cond,
            'title': title,
            'desc': desc,
            'group': group,
        }
        for (s, n, rx, child) in NEST_RULES:
            if s == seq_key and n == name and re.search(rx, recv or ''):
                step['child'] = child
                break
        steps.append(step)

    for lineno in range(b0, b1 + 1):
        text = clean_lines[lineno - 1]
        # trim the function's own outer braces
        if lineno == b0:
            text = text[text.find('{') + 1:]
        if lineno == b1:
            text = text[:text.rfind('}')]
        for ch in text:
            if ch == '{' and paren == 0:
                hdr = cur.strip()
                stack.append({'kind': header_kind(hdr), 'text': hdr})
                cur, cur_line = '', None
            elif ch == '}' and paren == 0:
                if stack:
                    stack.pop()
                cur, cur_line = '', None
            elif ch == ';' and paren == 0:
                emit(cur, cur_line if cur_line else lineno)
                cur, cur_line = '', None
            else:
                if ch == '(':
                    paren += 1
                elif ch == ')':
                    paren = max(0, paren - 1)
                if cur == '' and ch.isspace():
                    continue
                if cur == '':
                    cur_line = lineno
                cur += ch

    # splice curated extra steps (gameplay hidden in `if` conditions)
    for extra in EXTRA_STEPS.get(seq_key, []):
        e = dict(extra)
        e.update({'call': extra['call'], 'recv': None, 'file': file_rel})
        pos = len(steps)
        for i, s in enumerate(steps):
            if s['line'] > e['line']:
                pos = i
                break
        steps.insert(pos, e)

    fn_name = re.match(r'\w+', sig_regex.split('void ')[-1]).group(0)
    return {
        'fn': f"{file_rel.replace('.cs', '')}.{fn_name}",
        'file': file_rel,
        'sig_line': sig_line,
        'steps': steps,
    }


def main():
    sources = {}
    for file_rel in sorted({v[0] for v in SEQUENCES.values()}):
        path = os.path.join(SRC_DIR, file_rel)
        with open(path, encoding='utf-8') as f:
            raw = f.read()
        clean = clean_csharp(raw)
        sources[file_rel] = (clean.split('\n'), raw.split('\n'))

    unlabeled = set()
    seqs = {k: extract_sequence(k, sources, unlabeled) for k in SEQUENCES}

    # sanity: the anchor steps we present as facts must exist
    def has_call(seq, call, line=None):
        return any(s['call'] == call and (line is None or s['line'] == line)
                   for s in seqs[seq]['steps'])
    for seq, call in [('game', 'doOccurrences'), ('game', 'doBorderFill'),
                      ('player_process', 'doResearch'), ('player_process', 'doAmbitions'),
                      ('player_process', 'doEventTriggers'), ('city', 'finishBuild'),
                      ('unit', 'doCaravanMission'), ('character', 'doTurnYear')]:
        if not has_call(seq, call):
            raise SystemExit(f'[turn_order] expected step missing: {seq}:{call}')

    # resolve nesting (embed copies; player gets processTurn inlined)
    def resolve(seq_key, depth=0):
        out = []
        for s in seqs[seq_key]['steps']:
            t = dict(s)
            child = t.pop('child', None)
            if child and depth < 3:
                t['children'] = resolve(child, depth + 1)
                t['childEntry'] = f"{seqs[child]['file']}:{seqs[child]['sig_line']}"
                t['childFn'] = seqs[child]['fn']
            out.append(t)
        return out

    game_steps = resolve('game')

    player_steps = []
    for s in seqs['player']['steps']:
        if s['call'] == 'processTurn':
            for t in resolve('player_process'):
                t['via'] = f"processTurn (Player.cs:{seqs['player_process']['sig_line']})"
                player_steps.append(t)
        else:
            t = dict(s)
            t.pop('child', None)
            player_steps.append(t)

    # ids for anchors: g1, g2… / p1, p2… / children p4.1…
    def assign_ids(steps, prefix):
        for i, s in enumerate(steps, start=1):
            s['id'] = f'{prefix}{i}'
            if 'children' in s:
                assign_ids(s['children'], f'{prefix}{i}.')
    assign_ids(game_steps, 'g')
    assign_ids(player_steps, 'p')

    data = {
        '_meta': {
            'source': 'reference/Source/Base/Game/GameCore',
            'note': 'Step order mirrors source order exactly — do not sort.',
            'unlabeled': sorted(unlabeled),
        },
        'bands': [
            {
                'key': 'game',
                'title': 'Turn rollover (start of round)',
                'fn': 'Game.doTurn',
                'entry': f"Game.cs:{seqs['game']['sig_line']}",
                'steps': game_steps,
            },
            {
                'key': 'player',
                'title': "Each player's turn",
                'fn': 'Player.doTurn',
                'entry': f"Player.cs:{seqs['player']['sig_line']}",
                'steps': player_steps,
            },
        ],
    }

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write('\n')

    def count(steps):
        return len(steps) + sum(count(s.get('children', [])) for s in steps)
    total = sum(count(b['steps']) for b in data['bands'])
    print(f'[turn_order] wrote {os.path.relpath(OUT_PATH, ROOT)}: '
          f'{count(game_steps)} rollover + {count(player_steps)} player steps '
          f'(total {total} incl. nested)')
    if unlabeled:
        print(f'[turn_order] {len(unlabeled)} unlabeled calls (audit):')
        for u in sorted(unlabeled):
            print(f'  - {u}')


if __name__ == '__main__':
    main()
