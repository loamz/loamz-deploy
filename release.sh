#!/usr/bin/env bash
# Keeps the last builds so a bad deploy can be undone, and puts one back.
#   ./release.sh keep          save what is in artifacts/ (the build before the one you are about to make) under releases/,
#                              keeping the newest KEEP (default 3). build.sh does this for you.
#   ./release.sh list          the saved builds, newest first
#   ./release.sh rollback [N]  put saved build N back into artifacts/ (1 is the newest saved, the default). Then deploy it:
#                              ansible-playbook site.yml
# A rollback undoes the program, the web app and the agents' wheels. It does not undo a database migration: chat-server runs its
# migrations when it starts, so after a release that changed the database, restore the dump taken before it
# (docs/runbooks/restore-database.md) as well.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
art="$here/artifacts"
releases="$here/releases"
keep=${KEEP:-3}

saved() { ls -1dt "$releases"/*/ 2>/dev/null | sed 's:/$::' || true; }

case "${1:-}" in
  keep)
    [ -n "$(ls -A "$art" 2>/dev/null)" ] || exit 0
    stamp=$(date -r "$art" +%Y%m%d-%H%M%S)   # when it was built
    mkdir -p "$releases"
    [ -e "$releases/$stamp" ] || cp -a "$art" "$releases/$stamp"
    saved | tail -n +"$((keep + 1))" | xargs -r rm -rf
    ;;
  list)
    n=0
    for d in $(saved); do
      n=$((n + 1))
      parts=""
      for p in chat-server chat-bridge web wheels; do [ -e "$d/$p" ] && parts="$parts $p"; done
      echo "$n  $(basename "$d")  [$parts ]"
    done
    [ "$n" -gt 0 ] || echo "nothing saved yet: a build is saved when the next one starts"
    ;;
  rollback)
    n=${2:-1}
    dir=$(saved | sed -n "${n}p")
    [ -n "$dir" ] || { echo "no saved build number $n (see ./release.sh list)" >&2; exit 1; }
    rm -rf "$art"
    cp -a "$dir" "$art"
    echo "artifacts/ is now the build of $(basename "$dir"). Deploy it:  ansible-playbook site.yml"
    ;;
  *)
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//' >&2
    exit 2
    ;;
esac
