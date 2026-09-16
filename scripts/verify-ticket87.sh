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
printf 'Keep hands OFF the sensor for the next 60 seconds.\n'
mark 'hands off'
verify hands-off &
pid=$!
sleep 60
wait "$pid" || true
mark 'hands off ended; early client timeout makes active-wait coverage incomplete'
printf 'Place and HOLD the enrolled index finger steadily for 60 seconds.\n'
read -r -p 'Press Enter when holding: ' </dev/tty
mark holding
verify steady-hold &
pid=$!
sleep 60
wait "$pid" || true
mark 'holding ended'
printf 'Lift your finger. Next check uses PAM: hold an UNENROLLED finger.\n'
printf 'Keep holding after the first rejection, then lift after about 18s.\n'
printf 'If PAM falls back to a password, finish with your password.\n'
read -r -p 'Press Enter to start the wrong-finger check: ' </dev/tty
mark 'wrong-finger PAM start'
sudo -k
sudo -v || true
mark 'wrong-finger PAM end'
printf 'Lift, then touch the enrolled index finger for the first TTL claim.\n'
verify ttl-first
if ! grep -q 'Verify result: verify-match' "$out/ttl-first.txt"; then
  mark 'inconclusive-because-first-TTL-claim-did-not-match'
  exit 1
fi
mark '90-second gap start; hands off, no other authentication or suspend'
sleep 90
mark '90-second gap end'
printf 'Touch the enrolled index finger again.\n'
verify ttl-second
printf '\nDo not infer success from matching alone; journal must show parked reuse.\n'
