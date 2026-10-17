#!/usr/bin/env bash
# Keeps the generated folders out of Dropbox. Syncing node_modules through
# Dropbox leaves "foo 2" conflict copies and empty packages (npx astro goes
# missing), and builds into a synced dist/ hang. The File Provider ignore flag
# lives on the folder itself, so it is lost whenever the folder is deleted and
# recreated (npm ci keeps the folder, rm -rf does not); `make build` and
# `make install` re-apply it. No-op outside Dropbox.
set -euo pipefail
cd "$(dirname "$0")/.."
case "$PWD" in
  */Library/CloudStorage/Dropbox*) ;;
  *) exit 0 ;;
esac
for d in node_modules dist .astro; do
  mkdir -p "$d"
  if [ "$(xattr -p 'com.apple.fileprovider.ignore#P' "$d" 2>/dev/null)" != 1 ]; then
    xattr -w 'com.apple.fileprovider.ignore#P' 1 "$d"
    echo "dropbox: stopped syncing $d/"
  fi
done
conflicts=$(ls -d node_modules\ [0-9]* dist\ [0-9]* .astro\ [0-9]* 2>/dev/null || true)
if [ -n "$conflicts" ]; then
  echo "dropbox: conflict copies left by a sync race; delete them:" >&2
  echo "$conflicts" >&2
fi
