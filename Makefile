.PHONY: patch sync art data audit changelog dev build check contrast preview clean install

# Python runs from a venv outside Dropbox with its own pinned interpreter, so a
# Homebrew Python upgrade can't strip the packages (`make install` creates it).
# Falls back to python3 when the venv is missing.
VENV ?= $(HOME)/.venvs/owreference
PYTHON := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)

# Full per-patch pipeline. Run this after the game updates.
patch: sync art data audit changelog build check
	@echo ""
	@echo "✓ patch pipeline complete. Review CHANGELOG.md, then commit + push."

# Coverage + drift tripwires: which XML effect fields the game renders but we
# drop (hard gate — a new patch field fails the pipeline until handled), and
# whether watched game-source functions changed since last verify.
audit:
	@$(PYTHON) scripts/audit_coverage.py
	@$(PYTHON) scripts/verify_source_constants.py
	@$(PYTHON) scripts/verify_dlc_labels.py

# Post-build sanity: no broken internal links, no unresolved <Term>s.
check:
	@$(PYTHON) scripts/check_links.py
	@$(PYTHON) scripts/audit_prose.py   # writing rules: no source citations on pages, lede length (CLAUDE.md)

# Text-contrast audit of dist/ in headless Chrome (WCAG AA). Sampled by
# default; `node scripts/audit_contrast.mjs --all` for every page.
contrast:
	@node scripts/audit_contrast.mjs

sync:
	@bash scripts/sync_patch.sh

art:
	@$(PYTHON) scripts/extract_art.py

data:
	@$(PYTHON) scripts/build_data.py
	@$(PYTHON) scripts/build_tribes.py
	@$(PYTHON) scripts/build_families.py
	@$(PYTHON) scripts/build_family_pairings.py
	@$(PYTHON) scripts/build_wonders.py
	@$(PYTHON) scripts/build_projects.py
	@$(PYTHON) scripts/build_ambitions.py
	@$(PYTHON) scripts/build_laws.py
	@$(PYTHON) scripts/build_urban_buildings.py
	@$(PYTHON) scripts/build_rural_improvements.py
	@$(PYTHON) scripts/build_specialists.py
	@$(PYTHON) scripts/build_specialist_cost.py
	@$(PYTHON) scripts/build_harvest_events.py
	@$(PYTHON) scripts/build_theologies.py
	@$(PYTHON) scripts/build_world_religion_buildings.py
	@$(PYTHON) scripts/build_shrines.py
	@$(PYTHON) scripts/build_technologies.py
	@$(PYTHON) scripts/build_discoveries.py
	@$(PYTHON) scripts/build_promotions.py
	@$(PYTHON) scripts/build_unit_damage.py
	@$(PYTHON) scripts/build_zoc.py
	@$(PYTHON) scripts/build_borders.py
	@$(PYTHON) scripts/build_abilities.py
	@$(PYTHON) scripts/build_stat_scaling.py
	@$(PYTHON) scripts/build_jobs.py
	@$(PYTHON) scripts/build_council.py
	@$(PYTHON) scripts/build_difficulty.py
	@$(PYTHON) scripts/build_opinion.py
	@$(PYTHON) scripts/build_family_city_opinion.py
	@$(PYTHON) scripts/build_trait_inheritance.py
	@$(PYTHON) scripts/build_traits.py
	@$(PYTHON) scripts/build_study_events.py
	@$(PYTHON) scripts/build_archetypes.py
	@$(PYTHON) scripts/build_cognomens.py
	@$(PYTHON) scripts/build_hurry.py
	@$(PYTHON) scripts/build_victory_points.py
	@$(PYTHON) scripts/build_occurrences.py   # before the event builders: they link occurrence cards (anchors)
	@$(PYTHON) scripts/build_missions.py
	@$(PYTHON) scripts/build_mission_catalog.py
	@$(PYTHON) scripts/build_story_events.py
	@$(PYTHON) scripts/build_events.py
	@$(PYTHON) scripts/build_event_search.py  # global index — needs the four above
	@$(PYTHON) scripts/build_occurrence_events.py  # occurrence ← event backlinks — needs event-search.json
	@$(PYTHON) scripts/build_autobuild.py     # Vizier/Autonomous Rule — needs projects, council, event-search json
	@$(PYTHON) scripts/build_event_chains.py  # chain graphs — needs event-search.json
	@$(PYTHON) scripts/build_trait_events.py  # trait/cluster gates — needs event-search.json
	@$(PYTHON) scripts/build_trait_gain.py    # trait acquisition — needs event-search.json + traits.json
	@$(PYTHON) scripts/build_leaders.py       # dynasties — needs nations, traits, event-search json
	@$(PYTHON) scripts/build_diplomacy.py
	@$(PYTHON) scripts/build_regents.py
	@$(PYTHON) scripts/build_tribe_conversion.py
	@$(PYTHON) scripts/build_subjects.py
	@$(PYTHON) scripts/build_mapscripts.py
	@$(PYTHON) scripts/build_turn_order.py
	@$(PYTHON) scripts/build_conversion.py
	@$(PYTHON) scripts/build_concepts.py
	@$(PYTHON) scripts/build_hints.py
	@$(PYTHON) scripts/build_terrain.py
	@$(PYTHON) scripts/build_resources.py
	@$(PYTHON) scripts/build_culture.py
	@$(PYTHON) scripts/build_entities.py
	@$(PYTHON) scripts/build_pillage.py     # pillage payouts — needs entities, rural/urban, occurrences, event-search json
	@$(PYTHON) scripts/build_religious_spread.py   # spread roll, target pick, founding — needs entities
	@$(PYTHON) scripts/build_backlinks.py
	@$(PYTHON) scripts/build_overlay_cards.py
	@$(PYTHON) scripts/build_search_index.py

changelog:
	@$(PYTHON) scripts/changelog.py
	@$(PYTHON) scripts/build_patchnotes.py   # Mohawk-grounded patch page, distils the fresh diff

dev:
	@npx astro dev

build:
	@bash scripts/dropbox_ignore.sh
	@npx astro build

preview:
	@npx astro preview

install:
	@bash scripts/dropbox_ignore.sh
	@npm install
	@uv venv -q --allow-existing --python 3.14 --managed-python $(VENV)
	@uv pip install -q --python $(VENV)/bin/python -r requirements.txt

clean:
	@rm -rf dist .astro

# One-time seed of human-curated descriptions from the legacy xlsx
seed-annotations:
	@$(PYTHON) scripts/seed_annotations.py

overlay-server:
	@node scripts/overlay_state_server.cjs
