#!/usr/bin/env bash
# Full verification gate. Run this before every commit.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${SIGMAHELIX_PYTHON:-$repo_root/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo "No virtualenv found. Create one with: python3 -m venv .venv" >&2
  echo "Then install the project: .venv/bin/pip install -e '.[dev,voice]'" >&2
  exit 2
fi

export PATH="$(dirname "$python_bin"):$PATH"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/sigmahelix-pycache}"
export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-${TMPDIR:-/tmp}/sigmahelix-ruff-cache}"
export MYPY_CACHE_DIR="${MYPY_CACHE_DIR:-${TMPDIR:-/tmp}/sigmahelix-mypy-cache}"

echo "==> format"
ruff format --check src tests scripts
echo "==> lint"
ruff check src tests scripts
echo "==> types"
mypy
echo "==> compile"
"$python_bin" -m compileall -q src scripts tests
echo "==> tests"
"$python_bin" -m pytest -q
echo "==> cli"
"$python_bin" -m sigmahelix --version
echo "all gates passed"
