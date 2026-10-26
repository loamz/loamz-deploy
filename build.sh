#!/usr/bin/env bash
# Builds what the playbook installs: the ARM server binary and the web app. Run from anywhere.
#   deploy/ansible/build.sh [target]     target defaults to aarch64-unknown-linux-gnu.2.35 (Oracle's Ubuntu 24.04 ARM)
#   AUTH_URL=https://auth.example.com   where people sign in (Keycloak); the web app is built to use it
# Needs: cargo-zigbuild and zig (or `pip install ziglang`), wasm-pack, pnpm.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
target=${1:-aarch64-unknown-linux-gnu.2.35}
out="$root/deploy/ansible/artifacts"
rm -rf "$out" && mkdir -p "$out"
cd "$root"
cargo zigbuild --release -p chat-server --target "$target"
cp "target/${target%%.*}/release/chat-server" "$out/chat-server"
cd web
pnpm install --frozen-lockfile
pnpm wasm
VITE_OIDC_AUTHORITY="${AUTH_URL:?set AUTH_URL to your sign-in address, like https://auth.example.com}/realms/loamz" pnpm build
cp -r dist "$out/web"
echo "built: $out"
