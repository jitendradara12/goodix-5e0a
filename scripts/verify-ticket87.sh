#!/usr/bin/env bash
# User-only: claims the sensor and requests sudo for service debug/PAM checks.
set -eu
out="$HOME/goodix-ticket87-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"
sudo systemctl set-environment G_MESSAGES_DEBUG=all
sudo systemctl restart fprintd
start=$(date --iso-8601=seconds)
cleanup() {
  journalctl -u fprintd --since "$start" -o short-precise --no-pager > "$out/journal.txt"
  sudo systemctl unset-environment G_MESSAGES_DEBUG
  printf '\nEvidence saved in %s\n' "$out"
}
trap cleanup EXIT
mark() { printf '%s %s\n' "$(date --iso-8601=ns)" "$*" | tee -a "$out/phases.txt"; }
verify() {
  local label=$1 rc=0
  mark "$label start"
  timeout --signal=INT --kill-after=5s 60s fprintd-verify -f right-index-finger > "$out/$label.txt" 2>&1 || rc=$?
  cat "$out/$label.txt"
  mark "$label exit=$rc"
}
# Hands-off, steady-hold and PAM phases were covered in the previous run.
mark 'targeted close/reopen check; prior safety phases not repeated'
printf 'Lift, then touch the enrolled index finger for the first TTL claim.\n'
verify ttl-first
if ! grep -Eq 'Verify result: verify-(match|no-match) \(done\)' "$out/ttl-first.txt"; then
  mark 'inconclusive-because-first-claim-did-not-complete-normally'
  exit 1
fi
# Ticket 87 tests close/reopen routing, not TTL. The observed daemon exits
# after ~30s idle, so a 90s gap discards the very park we need to test.
mark '5-second gap start; lift finger, no other authentication or suspend'
sleep 5
mark '5-second gap end'
printf 'Touch the enrolled index finger again.\n'
verify ttl-second
printf '\nDo not infer success from matching alone; journal must show parked reuse.\n'
