#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
export PATH="$repo_root/.venv/bin:$PATH"
python_bin="${SIGMAHELIX_PYTHON:-$repo_root/.venv/bin/python}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/sigmahelix-pycache}"
export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-${TMPDIR:-/tmp}/sigmahelix-ruff-cache}"
export MYPY_CACHE_DIR="${MYPY_CACHE_DIR:-${TMPDIR:-/tmp}/sigmahelix-mypy-cache}"

ruff format --check apps/desktop scripts tests
ruff check --select E4,E7,E9,F apps/desktop scripts tests
mypy --ignore-missing-imports apps/desktop scripts tests
"$python_bin" -m compileall -q apps/desktop scripts tests
"$python_bin" -m pytest tests/test_execution_ledger.py -q -p no:cacheprovider
"$python_bin" -m pytest apps/desktop/tests/test_e2e_offline.py -q -p no:cacheprovider
