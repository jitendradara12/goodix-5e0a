#!/usr/bin/env bash
# Run explicitly; outside unittest discovery to avoid runner recursion.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/runner-summary.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

# Bypass preflight tools; only the runner's reporting is under test.
for tool in ninja nix-shell nix-instantiate; do
    printf '#!/bin/sh\nexit 0\n' > "$SANDBOX/$tool"
    chmod +x "$SANDBOX/$tool"
done
cat > "$SANDBOX/python3" <<'EOF'
#!/bin/sh
if [ "${FAKE_PY_FAIL:-0}" = 1 ]; then
    printf 'test_a ... FAIL\nRan 1 test in 0.001s\nFAILED (failures=1)\n'
    exit 1
fi
printf 'test_a ... ok\ntest_b ... ok\ntest_c ... ok\n'
printf 'test_d ... skipped '\''fixture'\''\ntest_e ... skipped '\''fixture'\''\n'
printf 'Ran 5 tests in 0.001s\nOK (skipped=2)\n'
EOF
chmod +x "$SANDBOX/python3"

fail=0
check() {
    local desc=$1; shift
    if "$@"; then
        echo "ok: $desc"
    else
        echo "FAIL: $desc"
        fail=1
    fi
}
run_fixture() {
    rc=0
    GOODIX_NATIVE_TESTS=skip FAKE_PY_FAIL="$1" PATH="$SANDBOX:$PATH" bash "$ROOT/tests/run_all_tests.sh" > "$SANDBOX/raw.log" 2>&1 || rc=$?
    sed $'s/\033\\[[0-9;]*m//g' "$SANDBOX/raw.log" > "$SANDBOX/out.log"
}
LOG="$SANDBOX/out.log"
run_fixture 0
check "successful tiers exit zero" test "$rc" -eq 0
check "passed excludes skips" grep -qx 'Total Tests Passed: 9' "$LOG"
check "executed excludes skips" grep -qx 'Total Tests Executed: 9' "$LOG"
check "skips counted separately" grep -qx 'Total Tests Skipped: 6' "$LOG"
check "per-tier counts" grep -q '3 passed, 2 skipped' "$LOG"
check "no hardware or release claim" test "$(grep -Ec 'DRIVER IS VERIFIED|READY FOR RELEASE' "$LOG" || true)" -eq 0

run_fixture 1
check "tier failure exits nonzero" test "$rc" -ne 0
check "failure output retained" grep -q 'FAILED (failures=1)' "$LOG"
check "failure stops before next tier" test "$(grep -c 'Running Tier 4' "$LOG" || true)" -eq 0
check "failure has no success banner" test "$(grep -Ec 'ALL TEST TIERS|Software test suite completed' "$LOG" || true)" -eq 0
exit "$fail"
