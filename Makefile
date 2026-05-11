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
