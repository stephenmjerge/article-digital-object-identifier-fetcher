#!/usr/bin/env bash
set -euo pipefail

# Keep pytest cache when possible; fall back if the FS is read-only.
if ! mkdir -p .pytest_cache 2>/dev/null; then
  export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -p no:cacheprovider"
fi

exec pytest "$@"
