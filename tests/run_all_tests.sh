#!/usr/bin/env bash
# Software checks only; no sensor access or hardware verification.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}:${ROOT_DIR}/legacy-experiments:${PYTHONPATH:-}"
cd "$ROOT_DIR"

export GOODIX_NATIVE_TESTS="${GOODIX_NATIVE_TESTS:-required}"
export GOODIX_SUSPEND_TESTS="${GOODIX_SUSPEND_TESTS:-$GOODIX_NATIVE_TESTS}"
# Integrated runs must build from this checkout, never reuse inherited binaries.
unset GOODIX_NATIVE_HARNESS GOODIX_SUSPEND_HARNESS GOODIX_SUSPEND_DISPATCH_HARNESS
case "$GOODIX_NATIVE_TESTS" in
    required)
        echo 'Building required native harness...'
        GOODIX_NATIVE_HARNESS=$(bash scripts/build_native_harness.sh)
        export GOODIX_NATIVE_HARNESS
        [[ -x "$GOODIX_NATIVE_HARNESS" ]] || { echo 'Required native harness unavailable' >&2; exit 1; }
        ;;
    skip) echo 'SKIP native harness (explicit GOODIX_NATIVE_TESTS=skip; not a required-lane pass)' ;;
    *) echo 'GOODIX_NATIVE_TESTS must be required or skip' >&2; exit 1 ;;
esac
case "$GOODIX_SUSPEND_TESTS" in
    required|skip) ;;
    *) echo 'GOODIX_SUSPEND_TESTS must be required or skip' >&2; exit 1 ;;
esac

if command -v nix-instantiate >/dev/null 2>&1; then
    echo 'Evaluating Nix package and effective NixOS configuration...'
    nix-instantiate --eval -E "let pkgs = import <nixpkgs> {}; in pkgs.callPackage ${ROOT_DIR}/libfprint-goodix.nix {}" >/dev/null
    nix-instantiate --eval --strict tests/tier1_feature/test_f96_nixos_module.nix >/dev/null
else
    echo 'SKIP Nix evaluation (nix-instantiate not installed)'
fi

TOTAL_PASSED=0
TOTAL_SKIPPED=0
run_tier() {
    local name=$1 directory=$2 output count skipped passed
    echo "Running $name"
    if ! output=$(python3 -m unittest discover -s "$directory" -v 2>&1); then
        printf '%s\n' "$output"
        return 1
    fi
    printf '%s\n' "$output"
    count=$(printf '%s\n' "$output" | sed -nE 's/^Ran ([0-9]+) tests? in .*/\1/p')
    [[ $count =~ ^[0-9]+$ && $count -gt 0 ]] || { echo "Missing or empty unittest test count for $name" >&2; return 1; }
    skipped=$(printf '%s\n' "$output" | sed -nE 's/^OK \(.*skipped=([0-9]+).*\)$/\1/p')
    skipped=${skipped:-0}
    passed=$(printf '%s\n' "$output" | grep -c '\.\.\. ok$' || true)
    echo "$name: $passed passed, $skipped skipped"
    TOTAL_PASSED=$((TOTAL_PASSED + passed))
    TOTAL_SKIPPED=$((TOTAL_SKIPPED + skipped))
    TOTAL_EXECUTED=$((TOTAL_EXECUTED + count - skipped))
}

TOTAL_EXECUTED=0
run_tier 'Tier 1 (Feature Coverage)' tests/tier1_feature
run_tier 'Tier 4 (Application Scenarios)' tests/tier4_realworld
run_tier 'Tier 5 (Adversarial Tests)' tests/tier5_adversarial

printf '\nTotal Tests Executed: %d\nTotal Tests Passed: %d\nTotal Tests Skipped: %d\n' \
    "$TOTAL_EXECUTED" "$TOTAL_PASSED" "$TOTAL_SKIPPED"
echo 'Software test suite completed without failures. See skipped count above.'
echo 'Hardware verification and release readiness are not established by this suite.'
