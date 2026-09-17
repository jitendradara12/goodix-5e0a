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
out="$HOME/goodix-$label-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"
start=$(date --iso-8601=seconds)
debug_set=0
cleanup() {
  local rc=$?
  trap - EXIT
  journalctl -u fprintd --since "$start" -o short-precise --no-pager > "$out/journal.txt" || rc=1
  if (( debug_set )); then
    sudo systemctl unset-environment G_MESSAGES_DEBUG || rc=1
  fi
  printf '\nEvidence saved in %s (exit=%s)\n' "$out" "$rc"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mark() { printf '%s %s\n' "$(date --iso-8601=ns)" "$*" | tee -a "$out/phases.txt"; }
fail() { mark "$*"; exit 1; }

systemctl show fprintd -p ExecStart > "$out/execstart.txt"
if ! grep -Eq '(^|[[:space:]])--no-timeout([[:space:];}]|$)' "$out/execstart.txt"; then
  fail 'inconclusive-because-service-flag-absent; deploy ticket 88 first'
fi
sudo systemctl set-environment G_MESSAGES_DEBUG=all
debug_set=1
sudo systemctl restart fprintd

verify() {
  local label=$1 rc=0
  mark "$label start; lift then touch the enrolled index finger"
  timeout --signal=INT --kill-after=5s 60s fprintd-verify -f right-index-finger > "$out/$label.txt" 2>&1 || rc=$?
  cat "$out/$label.txt"
  mark "$label exit=$rc"
  if (( rc == 124 || rc == 137 )); then
    fail "inconclusive-because-$label-client-timed-out"
  fi
  # fprintd-verify exits 1 on a completed no-match; that is a valid park probe.
  if (( rc > 1 )) || ! grep -Eq '^Verify result: verify-(match|no-match) \(done\)$' "$out/$label.txt"; then
    fail "inconclusive-because-$label-did-not-complete-normally"
  fi
}
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
