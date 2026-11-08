#!/usr/bin/env bash
# Remove a user-level SigmaHelix install created by packaging/install.sh.
# User data in ~/.local/share/sigmahelix and ~/.config/sigmahelix is kept
# unless --purge is passed.
set -euo pipefail

prefix="${SIGMAHELIX_PREFIX:-$HOME/.local}"
app_dir="$prefix/share/sigmahelix"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
purge=false
[[ "${1:-}" == "--purge" ]] && purge=true

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

say "removing $prefix/bin/sigmahelix"
rm -f "$prefix/bin/sigmahelix"

say "removing $app_dir"
rm -rf "$app_dir"

rm -f "$data_dir/applications/sigmahelix.desktop"
rm -f "$data_dir/icons/hicolor/scalable/apps/sigmahelix.svg"
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database "$data_dir/applications" >/dev/null 2>&1 || true

if $purge; then
  say "purging user data"
  rm -rf "$data_dir/sigmahelix" "${XDG_CONFIG_HOME:-$HOME/.config}/sigmahelix"
else
  say "user data kept in $data_dir/sigmahelix (use --purge to delete it)"
fi

say "done"
