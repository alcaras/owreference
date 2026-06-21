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

# Capture build metadata. The OldWorld.app bundle mtime is frozen at the
# original 2022 signing date and never tracks content patches, so read the real
# build from Steam's app manifest instead: `buildid` (monotonic per patch) and
# `LastUpdated` (epoch seconds of the last content update).
MANIFEST="$(cd "$INSTALL/../.." 2>/dev/null && pwd)/appmanifest_597180.acf"
BUILD_ID=""
UPDATED_AT=""
if [[ -f "$MANIFEST" ]]; then
  BUILD_ID=$(grep -o '"buildid"[[:space:]]*"[0-9]*"' "$MANIFEST" | grep -o '[0-9]*' | tail -1 || true)
  LAST_UPDATED=$(grep -o '"LastUpdated"[[:space:]]*"[0-9]*"' "$MANIFEST" | grep -o '[0-9]*' | tail -1 || true)
  if [[ -n "${LAST_UPDATED:-}" ]]; then
    UPDATED_AT=$(date -u -r "$LAST_UPDATED" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)
  fi
fi
# Version = Steam build id when available; fall back to the app-bundle mtime hash.
if [[ -n "$BUILD_ID" ]]; then
  VERSION="$BUILD_ID"
else
  VERSION=$(stat -f '%Sm' -t '%Y%m%d-%H%M%S' "$INSTALL/OldWorld.app" 2>/dev/null || date +%Y%m%d-%H%M%S)
fi

mkdir -p "$(dirname "$PATCH_JSON")"
cat > "$PATCH_JSON" <<EOF
{
  "version": "$VERSION",
  "buildId": "$BUILD_ID",
  "updatedAt": "$UPDATED_AT",
  "syncedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "installPath": "$INSTALL"
}
EOF
echo "✓ synced, Steam build: ${BUILD_ID:-$VERSION} (game updated ${UPDATED_AT:-unknown})"
