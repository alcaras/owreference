.PHONY: patch sync art data changelog dev build preview clean install

# Full per-patch pipeline. Run this after the game updates.
patch: sync art data changelog build
	@echo ""
	@echo "✓ patch pipeline complete. Review CHANGELOG.md, then commit + push."

sync:
	@bash scripts/sync_patch.sh

art:
	@python3 scripts/extract_art.py

data:
	@python3 scripts/build_data.py
	@python3 scripts/build_families.py
	@python3 scripts/build_wonders.py
	@python3 scripts/build_laws.py
	@python3 scripts/build_urban_buildings.py
	@python3 scripts/build_rural_improvements.py
	@python3 scripts/build_specialists.py
	@python3 scripts/build_harvest_events.py
	@python3 scripts/build_theologies.py
	@python3 scripts/build_world_religion_buildings.py
	@python3 scripts/build_shrines.py
	@python3 scripts/build_technologies.py
	@python3 scripts/build_promotions.py
	@python3 scripts/build_unit_damage.py
	@python3 scripts/build_jobs.py
	@python3 scripts/build_opinion.py
	@python3 scripts/build_trait_inheritance.py
	@python3 scripts/build_study_events.py
	@python3 scripts/build_archetypes.py
	@python3 scripts/build_cognomens.py
	@python3 scripts/build_stats.py
	@python3 scripts/build_missions.py
	@python3 scripts/build_conversion.py
	@python3 scripts/build_entities.py
	@python3 scripts/build_backlinks.py

changelog:
	@python3 scripts/changelog.py

dev:
	@npx astro dev

build:
	@npx astro build

preview:
	@npx astro preview

install:
	@npm install
	@pip3 install --break-system-packages -q openpyxl pyyaml UnityPy Pillow

clean:
	@rm -rf dist .astro

# One-time seed of human-curated descriptions from the legacy xlsx
seed-annotations:
	@python3 scripts/seed_annotations.py
