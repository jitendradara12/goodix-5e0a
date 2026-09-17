#!/usr/bin/env bash
# Builds the ticket-90 suspend/resume lifecycle harnesses from the pinned,
# patched libfprint tree (scripts/suspend-harness.nix) and prints the
# containing binary directory. Offline: compiles the driver with mocked
# transport and runs it against libfprint's fake device; no USB, no sensor,
# no system suspend, no fingerprint claims.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

output=$(nix-build "$ROOT_DIR/scripts/suspend-harness.nix" --no-out-link)
suspend="$output/bin/test_suspend_recovery"
dispatch="$output/bin/test_idle_suspend_dispatch"
[[ -x "$suspend" && -x "$dispatch" ]] || { echo "Suspend harness binaries unavailable: $output" >&2; exit 1; }
printf '%s\n' "$suspend" "$dispatch"
