#!/usr/bin/env bash
# Symlink every plugin of this repo into a PotionUI checkout as content/plugins/local/<id>.
# Usage: scripts/link-plugins.sh [/path/to/PotionUI]   (or set POTIONUI_SRC in .env.local)
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
src="${1:-${POTIONUI_SRC:-}}"
if [ -z "$src" ] && [ -f "$repo_root/.env.local" ]; then
  src="$(grep -E '^POTIONUI_SRC=' "$repo_root/.env.local" | cut -d= -f2- | tr -d '"')"
fi
[ -n "$src" ] || { echo "usage: $0 <PotionUI checkout>  (or set POTIONUI_SRC in .env.local)" >&2; exit 1; }
[ -d "$src/content/plugins" ] || { echo "not a PotionUI checkout: $src" >&2; exit 1; }

mkdir -p "$src/content/plugins/local"
for dir in "$repo_root"/*/; do
  [ -f "$dir/manifest.yml" ] || continue
  name="$(basename "$dir")"
  link="$src/content/plugins/local/$name"
  if [ -e "$link" ]; then
    echo "exists  $link"
  else
    ln -s "${dir%/}" "$link"
    echo "linked  $link -> ${dir%/}"
  fi
done
