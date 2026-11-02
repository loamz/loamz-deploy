#!/usr/bin/env bash
# Builds what the playbook installs from a loamz-chat checkout: the ARM server binary and the web app. Run from anywhere.
#   CHAT_REPO=../loamz-chat   where the loamz-chat checkout is (default: the folder next to this one)
#   ./build.sh [target]     target defaults to aarch64-unknown-linux-gnu.2.35 (Oracle's Ubuntu 24.04 ARM)
#   LEGAL=on                            show the privacy, terms and consent screens (only once docs/legal has no OWNER TO markers)
#   AUTH_URL=https://auth.example.com   where people sign in (Keycloak); the web app is built to use it
# Needs: cargo-zigbuild and zig (or `pip install ziglang`), wasm-pack, pnpm.
# The previous build is saved first (see ./release.sh), so ./release.sh rollback can put it back.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "${CHAT_REPO:-$here/../loamz-chat}" && pwd)
target=${1:-aarch64-unknown-linux-gnu.2.35}
out="$here/artifacts"
"$here/release.sh" keep   # the last build is kept (3 of them) so a bad deploy can be undone: ./release.sh rollback
rm -rf "$out" && mkdir -p "$out"
cd "$root"
cargo zigbuild --release -p chat-server --target "$target"
cp "target/${target%%.*}/release/chat-server" "$out/chat-server"
cargo zigbuild --release -p chat-bridge --target "$target"
cp "target/${target%%.*}/release/chat-bridge" "$out/chat-bridge"
# The legal pages and the consent step appear only when the texts are final: LEGAL=on, and then no draft marker may remain.
legal=off
if [ "${LEGAL:-off}" = "on" ]; then
  if grep -rq "OWNER TO" "$root/docs/legal"; then echo "docs/legal still has OWNER TO markers: finish the texts first" >&2; exit 1; fi
  legal=on
fi
cd web
pnpm install --frozen-lockfile
pnpm wasm
# The Google client that lets people keep backups in their own Drive. It is public (it identifies the app, and holds no secret): the app uses
# the browser-only flow, which needs no client secret, so none is stored anywhere. Set GOOGLE_DRIVE_CLIENT_ID to use another, or empty to turn it off.
drive="${GOOGLE_DRIVE_CLIENT_ID-53018822558-fsjrnun497g9eofguuok9ggi8toe47nb.apps.googleusercontent.com}"
VITE_LEGAL="$legal" VITE_GOOGLE_DRIVE_CLIENT_ID="$drive" VITE_OIDC_AUTHORITY="${AUTH_URL:?set AUTH_URL to your sign-in address, like https://auth.example.com}/realms/loamz" pnpm build
cp -r dist "$out/web"
echo "built: $out"
