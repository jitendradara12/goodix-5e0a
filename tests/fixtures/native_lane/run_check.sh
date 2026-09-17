#!/usr/bin/env bash
# Runner/build wiring only; no Nix builds or hardware. Outside discovery to avoid recursion.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/native-lane.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT
export FIXTURE_ROOT="$SANDBOX"
mkdir -p "$SANDBOX/tools" "$SANDBOX/output/bin"
cat > "$SANDBOX/tools/nix-build" <<'EOF'
#!/bin/sh
touch "$FIXTURE_ROOT/build-called"
[ "$FIXTURE_MODE" != build-error ] || exit 23
if [ "$FIXTURE_MODE" = missing ]; then
    echo "$FIXTURE_ROOT/missing"
else
    echo "$FIXTURE_ROOT/output"
fi
EOF
cat > "$SANDBOX/tools/nix-instantiate" <<'EOF'
#!/bin/sh
exit 0
EOF
cat > "$SANDBOX/tools/python3" <<'EOF'
#!/bin/sh
touch "$FIXTURE_ROOT/tests-called"
if [ "$GOODIX_NATIVE_TESTS" = required ]; then
    [ "$GOODIX_NATIVE_HARNESS" = "$FIXTURE_ROOT/output/bin/test_ssm_teardown" ] || exit 42
    "$GOODIX_NATIVE_HARNESS" || exit 43
fi
printf 'test_fixture ... ok\nRan 1 test in 0.001s\nOK\n'
EOF
printf '#!/bin/sh\nexit 0\n' > "$SANDBOX/output/bin/test_ssm_teardown"
chmod +x "$SANDBOX/tools/"* "$SANDBOX/output/bin/test_ssm_teardown"
run_fixture() {
    rm -f "$SANDBOX/build-called" "$SANDBOX/tests-called"
    rc=0
    FIXTURE_MODE="$1" GOODIX_NATIVE_TESTS="$2" GOODIX_NATIVE_HARNESS=/stale/binary \
        PATH="$SANDBOX/tools:$PATH" bash "$ROOT/tests/run_all_tests.sh" > "$SANDBOX/out.log" 2>&1 || rc=$?
}
for mode in build-error missing; do
    run_fixture "$mode" required
    test "$rc" -ne 0
    test -f "$SANDBOX/build-called"
    test ! -f "$SANDBOX/tests-called"
    echo "ok: required lane stops on $mode, ignoring inherited harness"
done
run_fixture success required
test "$rc" -eq 0
test -f "$SANDBOX/build-called"
test -f "$SANDBOX/tests-called"
echo 'ok: required lane passes newly built executable to tests'
printf '#!/bin/sh\nexit 7\n' > "$SANDBOX/output/bin/test_ssm_teardown"
run_fixture success required
test "$rc" -ne 0
test -f "$SANDBOX/tests-called"
echo 'ok: native execution failure fails the required lane'
run_fixture build-error skip
test "$rc" -eq 0
test ! -f "$SANDBOX/build-called"
grep -q 'SKIP native harness (explicit' "$SANDBOX/out.log"
echo 'ok: optional skip is explicit and does not build'
run_fixture success invalid
test "$rc" -ne 0
test ! -f "$SANDBOX/tests-called"
echo 'ok: invalid native mode fails'

# Check the real unittest gate, not just the runner stubs above.
cd "$ROOT"
case_name=tests.tier5_adversarial.test_m1_c1_lifecycle_adversarial.TestM1C1LifecycleAdversarial.test_native_c_ssm_and_cancellation_invariants
if GOODIX_NATIVE_TESTS=required GOODIX_NATIVE_HARNESS="$SANDBOX/absent" \
    python3 -m unittest "$case_name" > "$SANDBOX/unit.log" 2>&1; then
    echo 'FAIL: missing required harness passed unittest' >&2
    exit 1
fi
grep -q 'Native harness unavailable' "$SANDBOX/unit.log"
GOODIX_NATIVE_TESTS=skip GOODIX_NATIVE_HARNESS="$SANDBOX/absent" \
    python3 -m unittest "$case_name" > "$SANDBOX/unit.log" 2>&1
grep -q 'OK (skipped=1)' "$SANDBOX/unit.log"
echo 'ok: real unittest rejects missing harness and reports explicit skip'
