#!/usr/bin/env bash
# Install SigmaHelix for the current user.
#
#   ./packaging/install.sh            # install into ~/.local
#   ./packaging/install.sh --dev      # editable install into a local .venv
#
# No sudo, no system packages, no files outside the install prefix.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
prefix="${SIGMAHELIX_PREFIX:-$HOME/.local}"
app_dir="$prefix/share/sigmahelix"
venv_dir="$app_dir/venv"
bin_dir="$prefix/bin"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
python_bin="${SIGMAHELIX_PYTHON:-python3}"
mode="${1:-release}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v "$python_bin" >/dev/null 2>&1 || die "$python_bin not found"
"$python_bin" - <<'PY' || die "Python 3.11 or newer is required"
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY

if [[ "$mode" == "--dev" ]]; then
  say "editable install into $repo_root/.venv"
  [[ -d "$repo_root/.venv" ]] || "$python_bin" -m venv "$repo_root/.venv"
  "$repo_root/.venv/bin/python" -m pip install --quiet --upgrade pip
  "$repo_root/.venv/bin/python" -m pip install --quiet -e "$repo_root[voice]"
  say "run it with: $repo_root/.venv/bin/sigmahelix"
  exit 0
fi

say "installing into $app_dir"
mkdir -p "$app_dir" "$bin_dir"
[[ -d "$venv_dir" ]] || "$python_bin" -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --quiet --upgrade pip
"$venv_dir/bin/python" -m pip install --quiet --force-reinstall "$repo_root[voice]"

say "linking $bin_dir/sigmahelix"
ln -sfn "$venv_dir/bin/sigmahelix" "$bin_dir/sigmahelix"

# Personal skills live in the app config so they survive reinstalls and can be
# edited by the user. The package also ships copies; a file here wins.
say "installing skills into $data_dir/sigmahelix/skills"
mkdir -p "$data_dir/sigmahelix/skills"
for skill in "$repo_root"/src/sigmahelix/skills/personal/*.md; do
  [[ -f "$skill" ]] || continue
  install -m 0644 "$skill" "$data_dir/sigmahelix/skills/"
done

# Desktop entry and icon (silently skipped on headless machines).
mkdir -p "$data_dir/applications" "$data_dir/icons/hicolor/scalable/apps"
install -m 0644 "$repo_root/packaging/sigmahelix.desktop" \
  "$data_dir/applications/sigmahelix.desktop"
install -m 0644 "$repo_root/packaging/sigmahelix.svg" \
  "$data_dir/icons/hicolor/scalable/apps/sigmahelix.svg"
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database "$data_dir/applications" >/dev/null 2>&1 || true

say "verifying"
"$bin_dir/sigmahelix" --version || die "the installed command does not run"

case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) say "note: add $bin_dir to PATH to run 'sigmahelix' from any terminal" ;;
esac

say "done — type 'sigmahelix' to start the app, 'sigmahelix doctor' to check it"
