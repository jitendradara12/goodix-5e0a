#!/usr/bin/env bash
# User-only: restarts the service and claims the sensor twice. Run after deployment.
set -euo pipefail
export LC_ALL=C
gap=${1:-90}
case "$gap" in
  90) label=ticket88 ;;
  310) label=ticket85-expiry ;;
  *) printf 'Usage: bash %s [90|310]\n' "$0" >&2; exit 2 ;;
esac
source "$(dirname -- "${BASH_SOURCE[0]}")/verify-common.sh"
verify_init "$label"

systemctl show fprintd -p ExecStart > "$out/execstart.txt"
if ! grep -Eq '(^|[[:space:]])--no-timeout([[:space:];}]|$)' "$out/execstart.txt"; then
  fail 'inconclusive-because-service-flag-absent; deploy ticket 88 first'
fi
verify_setup
pid_snapshot() {
  systemctl show fprintd -p MainPID -p ActiveState -p ExecMainStartTimestamp > "$out/$1.txt"
  cat "$out/$1.txt"
}
# Ticket 87 already captured hands-off, steady-hold and PAM evidence.
# Use AGENTS.md's already-verified exception; only the idle pair is new.
mark "targeted ${gap}s probe; prior safety phases not repeated"
verify first
pid_snapshot before-idle
before=$(sed -n 's/^MainPID=//p' "$out/before-idle.txt")
[[ "$before" =~ ^[1-9][0-9]*$ ]] || fail 'inconclusive-because-no-daemon-before-idle'
mark "${gap}s idle start PID=$before; lift finger, no authentication or suspend"
sleep "$gap"
pid_snapshot after-idle
after=$(sed -n 's/^MainPID=//p' "$out/after-idle.txt")
mark "${gap}s idle end PID=$after"
[[ "$after" == "$before" ]] || fail 'falsified: daemon did not survive idle with the same PID'
verify second
pid_snapshot after-second
after_second=$(sed -n 's/^MainPID=//p' "$out/after-second.txt")
[[ "$after_second" == "$before" ]] || fail 'falsified: daemon changed during second claim'
mark 'claim pair complete; journal review required for parked reuse and activation latency'
printf '\nPaste phases.txt, execstart.txt, client logs, PID snapshots and unfiltered journal.txt.\n'
