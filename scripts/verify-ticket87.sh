#!/usr/bin/env bash
# User-only: claims the sensor and requests sudo for service debug/PAM checks.
set -euo pipefail
export LC_ALL=C
out=$(mktemp -d "$HOME/goodix-ticket87-$(date +%Y%m%d-%H%M%S)-XXXXXX")
start=$(date --iso-8601=ns)
debug_set=0
cleanup() {
  local test_rc=$? rc journal_rc=0 cleanup_rc=0 end
  rc=$test_rc
  trap - EXIT
  trap '' INT TERM HUP
  set +e
  end=$(date --iso-8601=ns)
  journalctl -u fprintd --since "$start" --until "$end" -o short-precise --no-pager > "$out/journal.txt" 2> "$out/journal-error.txt"
  journal_rc=$?
  if (( journal_rc )); then
    printf 'WARNING: journal capture failed; partial evidence retained. Retry manually:\n' >&2
    printf 'journalctl -u fprintd --since %q --until %q -o short-precise --no-pager\n' "$start" "$end" >&2
  fi
  if (( debug_set )); then
    sudo -n systemctl unset-environment G_MESSAGES_DEBUG > "$out/cleanup.txt" 2>&1
    cleanup_rc=$?
    if (( cleanup_rc )); then
      printf 'WARNING: debug environment cleanup failed; sudo may have expired. Run manually outside the test:\nsudo systemctl unset-environment G_MESSAGES_DEBUG\n' >&2
    else
      printf 'Debug manager environment unset; running daemon not restarted.\n'
    fi
  fi
  if (( rc == 0 && (journal_rc != 0 || cleanup_rc != 0) )); then rc=1; fi
  printf 'test_exit=%s\njournal_exit=%s\ncleanup_attempted=%s\ncleanup_exit=%s\nexit=%s\n' "$test_rc" "$journal_rc" "$debug_set" "$cleanup_rc" "$rc" > "$out/status.txt"
  cat "$out/status.txt"
  printf '\nEvidence directory: %s\n' "$out"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
printf 'Setup authentication only; measured claims begin after the service restart.\n'
sudo -v
# Attempt cleanup even if setup is interrupted after changing the environment.
debug_set=1
sudo -n systemctl set-environment G_MESSAGES_DEBUG=all
sudo -n systemctl restart fprintd
start=$(date --iso-8601=ns)
mark() { printf '%s %s\n' "$(date --iso-8601=ns)" "$*" | tee -a "$out/phases.txt"; }
verify() {
  local label=$1 rc=0
  mark "$label start"
  timeout --signal=INT --kill-after=5s 60s fprintd-verify -f right-index-finger > "$out/$label.txt" 2>&1 || rc=$?
  cat "$out/$label.txt"
  mark "$label exit=$rc"
  if (( rc > 1 )) || ! grep -Eq '^Verify result: verify-(match|no-match) \(done\)$' "$out/$label.txt"; then
    mark "inconclusive-because-$label-did-not-complete-normally"
    if (( rc == 0 )); then rc=1; fi
    exit "$rc"
  fi
}
# Hands-off, steady-hold and PAM phases were covered in the previous run.
mark 'targeted close/reopen check; prior safety phases not repeated'
printf 'Lift, then touch the enrolled index finger for the first TTL claim.\n'
verify ttl-first
# Ticket 87 tests close/reopen routing, not TTL. The observed daemon exits
# after ~30s idle, so a 90s gap discards the very park we need to test.
mark '5-second gap start; lift finger, no other authentication or suspend'
sleep 5
mark '5-second gap end'
printf 'Touch the enrolled index finger again.\n'
verify ttl-second
printf '\nDo not infer success from matching alone; journal must show parked reuse.\n'
