#!/usr/bin/env bash
# release.sh keeps the newest 3 builds, lists them, puts one back, and refuses one that is not saved. Run in a scratch folder.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d)
cp "$here/release.sh" "$scratch/"
cd "$scratch"
for i in 1 2 3 4 5; do
  rm -rf artifacts && mkdir -p artifacts/web artifacts/wheels && echo "v$i" > artifacts/chat-server && touch -d "2026-11-0$i 10:00:00" artifacts
  ./release.sh keep
done
listing=$(./release.sh list)
[ "$(echo "$listing" | wc -l)" = 3 ] || { echo "expected 3 saved builds"; exit 1; }
[[ "$(echo "$listing" | sed -n 1p)" == *20261105-100000* ]] || { echo "newest saved build should be the 5th"; exit 1; }
./release.sh rollback 3 >/dev/null
[ "$(cat artifacts/chat-server)" = v3 ] || { echo "rollback 3 should bring back v3"; exit 1; }
if ./release.sh rollback 9 2>/dev/null; then echo "rolling back to a build that is not saved must fail"; exit 1; fi
cd / && rm -rf "$scratch"
echo "release.sh: ok"
