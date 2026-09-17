#!/usr/bin/env bash
# Software only. Requires Nix and a nixpkgs channel/NIX_PATH; see scripts/README-native-tests.md.
# stdout is the executable path; build diagnostics go to stderr.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v nix-build >/dev/null || { echo 'Native harness requires nix-build and <nixpkgs>.' >&2; exit 1; }
output=$(nix-build "$ROOT_DIR/scripts/native-harness.nix" --no-out-link)
harness="$output/bin/test_ssm_teardown"
[[ -x "$harness" ]] || { echo "Native harness unavailable: $harness" >&2; exit 1; }
printf '%s\n' "$harness"
