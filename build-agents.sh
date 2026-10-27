#!/usr/bin/env bash
# Builds the wheels the agents role installs: the agent server and runtime (loamz-agents), the storage engines (loamz-data)
# and the client and identity libraries (loamz-python). They are pure Python, so one build serves any machine.
#   ./build-agents.sh        (the three repositories sit next to this one; override with AGENTS_REPO, DATA_REPO, PYTHON_REPO)
# Run it after ./build.sh (that one empties artifacts/).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
agents=${AGENTS_REPO:-$here/../loamz-agents}; data=${DATA_REPO:-$here/../loamz-data}; py=${PYTHON_REPO:-$here/../loamz-python}
out="$here/artifacts/wheels"; rm -rf "$out"; mkdir -p "$out"
(cd "$agents" && uv build --package loamz-agents-server --wheel -o "$out" && uv build --package loamz-runtime --wheel -o "$out")
(cd "$data" && uv build --package loamz-engine --wheel -o "$out")
(cd "$py" && uv build --package loamz-core --wheel -o "$out" && uv build --package loamz-identity --wheel -o "$out" && uv build --package loamz-data --wheel -o "$out")
ls -1 "$out"
