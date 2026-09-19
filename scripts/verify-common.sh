# Shared lifecycle for the user-run parked-TLS probes. No work happens on source.
verify_init() {
  out=$(mktemp -d "$HOME/goodix-$1-$(date +%Y%m%d-%H%M%S)-XXXXXX")
  start=$(date --iso-8601=ns)
  debug_set=0
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
}

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

verify_setup() {
  printf 'Setup authentication only; measured claims begin after the service restart.\n'
  sudo -v
  # Attempt cleanup even if setup is interrupted after changing the environment.
  debug_set=1
  sudo -n systemctl set-environment G_MESSAGES_DEBUG=all
  sudo -n systemctl restart fprintd
  start=$(date --iso-8601=ns)
}

mark() { printf '%s %s\n' "$(date --iso-8601=ns)" "$*" | tee -a "$out/phases.txt"; }
fail() { mark "$1"; exit "${2:-1}"; }

verify() {
  local label=$1 rc=0
  mark "$label start; lift then touch the enrolled index finger"
  timeout --signal=INT --kill-after=5s 60s fprintd-verify -f right-index-finger > "$out/$label.txt" 2>&1 || rc=$?
  cat "$out/$label.txt"
  mark "$label exit=$rc"
  if (( rc == 124 || rc == 137 )); then
    fail "inconclusive-because-$label-client-timed-out" "$rc"
  fi
  # A completed no-match (exit 1) is a valid park probe, not a matching success.
  if (( rc > 1 )) || ! grep -Eq '^Verify result: verify-(match|no-match) \(done\)$' "$out/$label.txt"; then
    if (( rc == 0 )); then rc=1; fi
    fail "inconclusive-because-$label-did-not-complete-normally" "$rc"
  fi
}
