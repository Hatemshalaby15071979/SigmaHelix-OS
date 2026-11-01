#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
python_bin="${SIGMAHELIX_PYTHON:-python3}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/sigmahelix-pycache}"
export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-${TMPDIR:-/tmp}/sigmahelix-ruff-cache}"
export MYPY_CACHE_DIR="${MYPY_CACHE_DIR:-${TMPDIR:-/tmp}/sigmahelix-mypy-cache}"

ruff format --check apps/desktop
ruff check --select E4,E7,E9,F apps/desktop
mypy --ignore-missing-imports apps/desktop
"$python_bin" -m compileall -q apps/desktop
"$python_bin" -m pytest apps/desktop/tests/test_e2e_offline.py -q -p no:cacheprovider
