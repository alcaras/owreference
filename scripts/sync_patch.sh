#!/usr/bin/env bash
# Sync ./reference/ from the local Old World install.
# Records the game's build identifier into data/patch.json for changelog tagging.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL="${OW_INSTALL:-$HOME/Library/Application Support/Steam/steamapps/common/Old World}"
REF_SRC="$INSTALL/Reference"
REF_DST="$ROOT/reference"
PATCH_JSON="$ROOT/data/patch.json"

if [[ ! -d "$REF_SRC" ]]; then
  echo "✗ Old World install not found at: $INSTALL" >&2
  echo "  Set OW_INSTALL=/path/to/Old\\ World to override." >&2
  exit 1
fi

echo "→ syncing $REF_SRC/{XML,Graphics} → $REF_DST/"
mkdir -p "$REF_DST"
rsync -a --delete \
  --exclude '.DS_Store' \
  --include 'XML/***' \
  --include 'Graphics/***' \
  --exclude '*' \
  "$REF_SRC/" "$REF_DST/"

# Capture build metadata
APP_INFO="$INSTALL/OldWorld.app/Contents/Resources/Data/app.info"
VERSION="unknown"
if [[ -f "$APP_INFO" ]]; then
  # app.info typically contains "CompanyName\nProductName" on first lines —
  # the real build version is exposed via UnityPlayer; for now we hash app dir mtime.
  VERSION=$(stat -f '%Sm' -t '%Y%m%d-%H%M%S' "$INSTALL/OldWorld.app" 2>/dev/null || date +%Y%m%d-%H%M%S)
fi

mkdir -p "$(dirname "$PATCH_JSON")"
cat > "$PATCH_JSON" <<EOF
{
  "version": "$VERSION",
  "syncedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "installPath": "$INSTALL"
}
EOF
echo "✓ synced, build tag: $VERSION"
