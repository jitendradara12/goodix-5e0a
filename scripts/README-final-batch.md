# Final hardware batch, ticket 95

Run this checklist once, yourself, from the repository root in one Bash terminal.
No rebuild or deployment is needed. Prior software integration passed the full
required suite (see `tests/run_all_tests.sh`); this checklist
has only been syntax-checked, not run on hardware. Tickets 87/88 already verified
the safety phases, so do not repeat mandatory hands-off/20-second holds here.

Ticket 90's unresolved defect matters: public idle suspend bypasses the driver
hooks and unconditional parked-TLS disposal is **falsified in software**. The
health probe does not prove safe encrypted recovery. This batch observes disposal
and operational recovery separately; it is not a fix.

## 1. Prepare evidence and debug logging

Choose the enrolled slot, output parent and idle duration. Labels below describe
what you actually present, not what you hope matched. Close other fingerprint
clients. Avoid PAM/fingerprint authentication during measured windows; use a
password to unlock after resume. If another claim occurs, record the interference.

```bash
export LC_ALL=C
read -r -p 'Enrolled slot (for example left-index-finger): ' enrolled_finger
output_parent=${OUTPUT_PARENT:-$HOME}
idle_seconds=${IDLE_SECONDS:-20}
umask 077
out=$(mktemp -d "$output_parent/goodix-final-$(date +%Y%m%d-%H%M%S)-XXXXXX")
printf '%s\n' "$out"
systemctl show fprintd -p ExecStart > "$out/execstart.txt"
cat "$out/execstart.txt"
```

Check that `--no-timeout` is present. Stop if absent. Setup authentication and
this single restart happen **before** any measured claim. Do not paste later
steps if setup fails. Cleanup is in section 5, including for an abandoned batch.

```bash
sudo -v && sudo -n systemctl set-environment G_MESSAGES_DEBUG=all && sudo -n systemctl restart fprintd
batch_start=$(date --iso-8601=ns)
printf '%s batch-start\n' "$batch_start" >> "$out/phases.txt"
```

## 2. Optional isolated idle sample, ticket 94

With no existing client/claim, keep hands off, do not authenticate or suspend,
and run this before the first claim. Record that observation independently; the
sampler cannot detect claims. Debug journal coverage must span the whole interval.

```bash
idle_start=$(date --iso-8601=ns)
printf '%s idle-start; operator reports no open clients\n' "$idle_start" >> "$out/phases.txt"
idle_rc=0
python3 scripts/sample_fprintd_resources.py --interval "$idle_seconds" > "$out/idle-resources.json" || idle_rc=$?
idle_end=$(date --iso-8601=ns)
printf '%s idle-end exit=%s; record any interference here\n' "$idle_end" "$idle_rc" >> "$out/phases.txt"
journalctl -u fprintd --since "${idle_start/,/.}" --until "${idle_end/,/.}" -o short-precise --no-pager > "$out/idle-journal.txt" 2> "$out/idle-journal-error.txt"
```

PSS permission denial as non-root is acceptable incomplete evidence. Keep the
JSON; do not add sudo to make it green. Confirm a complete idle baseline only
with unchanged identity, complete counters, observed `--no-timeout`, and independent
no-claims/no-suspend evidence. Claims falsify the idle premise; PID replacement
falsifies process continuity. Missing counters or claim coverage are inconclusive.
No wakeup, power, stock-daemon comparison or resource-budget verdict is available.

## 3. One isolated claim block, reused for each labeled sample

Use fresh IDs: `pre-sleep`, `post-resume`, then optionally `wrong-01` or further
labeled contacts in this same batch. For the first two, present the finger known
to match the selected enrollment. Use `genuine` only when known, `wrong` for a
known different finger, otherwise `unknown`. Finger/contact tokens are anonymous
ASCII letters/digits/dot/underscore/hyphen, at most 80 characters. Never relabel
unknown historical no-matches as genuine failures.

Paste this block for **one claim at a time**. It saves only that client's output,
not setup/PAM output. Lift first, then touch when prompted. Normal no-match can
exit 1; it still counts as done when the terminal marker is present. If interrupted,
finish saving the evidence below if the shell remains available.

```bash
read -r -p 'Fresh ID, label, presented-finger token, contact token: ' claim_id label presented_finger contact
# Stop this Bash session before touching existing evidence if the ID is invalid.
[[ "$claim_id" =~ ^[A-Za-z0-9_.-]{1,80}$ && ! -e "$out/$claim_id.txt" ]] || { echo 'Invalid or reused ID; stop and clean up per section 5.'; exit 2; }
claim_start=$(date --iso-8601=ns)
printf '%s %s start label=%s finger=%s contact=%s\n' "$claim_start" "$claim_id" "$label" "$presented_finger" "$contact" >> "$out/phases.txt"
timeout --signal=INT --kill-after=5s 60s fprintd-verify -f "$enrolled_finger" 2>&1 | tee "$out/$claim_id.txt"
client_rc=${PIPESTATUS[0]}
claim_end=$(date --iso-8601=ns)
printf '%s %s end client_exit=%s\n' "$claim_end" "$claim_id" "$client_rc" >> "$out/phases.txt"
journalctl -u fprintd --since "${claim_start/,/.}" --until "${claim_end/,/.}" -o short-precise --no-pager > "$out/$claim_id-journal.txt" 2> "$out/$claim_id-journal-error.txt"
read -r -p 'Disposition: done, cancelled (timeout/interruption), or incomplete: ' disposition
printf '%s disposition=%s\n' "$claim_id" "$disposition" >> "$out/phases.txt"
cancel_args=()
if [[ "$disposition" == cancelled ]]; then cancel_args=(--cancelled); fi
python3 scripts/matching_reliability.py collect --samples "$out/matching-samples.jsonl" \
  --id "$claim_id" --label "$label" --finger "$presented_finger" --contact "$contact" \
  --results "$out/$claim_id.txt" --journal "$out/$claim_id-journal.txt" "${cancel_args[@]}"
```

Mark timeout 124/137, Ctrl-C and any interruption `cancelled`, even if a partial
result exists. `done` requires `Verify result: verify-match (done)` or
`verify-no-match (done)` and no interruption. Missing completion without an
interruption is incomplete, never a pass. The importer also checks evidence;
do not use a journal from another claim to fill missing client output.

## 4. Park, real desktop sleep, then claim without restart

After `pre-sleep` finishes normally, lift and check its journal for
`parking live TLS session`. If missing, stop this scenario as inconclusive.
Record the snapshot immediately before sleep:

```bash
printf '%s before-desktop-suspend\n' "$(date --iso-8601=ns)" | tee -a "$out/phases.txt"
systemctl show fprintd -p MainPID -p ActiveState -p ExecMainStartTimestamp > "$out/pre-sleep-pid.txt"
cat "$out/pre-sleep-pid.txt"
```

**Suspend manually through the desktop now**, then wake promptly. Aim to keep
park-to-next-claim wall time under the 300-second TTL. No automated suspend is
needed. Do not restart fprintd, rerun setup, run another claim or authenticate by
fingerprint between park and the post-resume claim. In particular, do **not** use
`verify-ticket88.sh` after resume: it restarts fprintd and destroys the session
this experiment is meant to test. That script and ticket 87's script are not
required in this batch.

Immediately after waking, record the boundary, then use section 3 once with ID
`post-resume`. Record any unlock claim or delay; do not conceal it.

```bash
printf '%s after-desktop-resume\n' "$(date --iso-8601=ns)" | tee -a "$out/phases.txt"
systemctl show fprintd -p MainPID -p ActiveState -p ExecMainStartTimestamp > "$out/post-resume-pid.txt"
cat "$out/post-resume-pid.txt"
```

After that claim, take the final identity snapshot. Optional wrong-finger samples
come only after this snapshot, using section 3 and a new ID for each.

```bash
systemctl show fprintd -p MainPID -p ActiveState -p ExecMainStartTimestamp > "$out/post-claim-pid.txt"
```

## 5. Save, analyze and clean up

End the measured window before cleanup. Keep unfiltered journals and permission
errors. Empty/inaccessible logs are missing evidence, not silent hardware.

```bash
batch_end=$(date --iso-8601=ns)
printf '%s batch-end\n' "$batch_end" >> "$out/phases.txt"
journalctl -u fprintd --since "${batch_start/,/.}" --until "${batch_end/,/.}" -o short-precise --no-pager > "$out/journal.txt" 2> "$out/journal-error.txt"
python3 scripts/matching_reliability.py report "$out/matching-samples.jsonl" > "$out/matching-report.json"
python3 scripts/analyze_activation_timing.py "$out/journal.txt" > "$out/activation-timing.json"
cleanup_rc=0
sudo -n systemctl unset-environment G_MESSAGES_DEBUG > "$out/cleanup.txt" 2>&1 || cleanup_rc=$?
printf 'cleanup_exit=%s\n' "$cleanup_rc" | tee "$out/cleanup-status.txt"
if (( cleanup_rc != 0 )); then
  printf 'WARNING: cleanup failed, possibly expired sudo. Outside the test run manually: sudo systemctl unset-environment G_MESSAGES_DEBUG\n'
fi
```

Cleanup must be noninteractive. Do not authenticate again inside the measured
window. Unsetting the manager environment does not change the running daemon's
debug state; any desired restart belongs **after** all evidence is saved. If the
terminal was lost, perform the same manual cleanup outside the test. Keep this
private evidence directory; do not collect raw images/templates.

## Verdict checklist

- **89 matching:** confirm report accounting when labeled client completion and
  `Milan verify`/`report_verify_status` agree, with duplicates counted once.
  Falsify accounting if duplicates inflate counts or unknown/cancelled samples
  enter accuracy rates. Genuine no-match is a labeled miss, wrong-finger no-match
  is rejection; missing/interrupted samples are inconclusive. First-touch is a
  reported-status proxy, not a physical-touch count or a population accuracy claim.
- **90 disposal:** `TLS session reused` after real sleep falsifies unconditional
  disposal even if capture works. A new handshake followed by working capture
  with no reuse confirms fresh-session recovery for this run only. Timeout,
  `Invalid ACK` or TLS error followed by successful full handshake is fallback
  recovery, not proof of disposal. A health-check ACK alone proves neither.
- **90 operation:** completed post-resume encrypted capture/verification without
  duplicate completion supports operational recovery. Failed capture or duplicate
  completion falsifies it. Require a pre-sleep park, real sleep boundaries, same
  nonzero PID/start identity, no intervening claims/restart and an in-TTL window.
  Missing evidence, changed PID, expired TTL or interruption makes this parked
  recovery scenario inconclusive. Do not describe the unresolved defect as fixed.
- **93 timing:** confirm repeated complete actual-reuse-to-0x32 command envelopes;
  falsify the earlier attribution if most delay lies outside those envelopes.
  Missing markers or insufficient repeated reuse intervals are inconclusive.
  These are journal intervals, not USB readiness or physical-touch latency.
- **91/92/94:** preserve client status, bounded logs and explicit cleanup status;
  hidden cleanup failure/extra PAM prompts falsify cleanup isolation. Ticket 92
  adds no hardware step. Apply section 2's idle criteria without inventing metrics.

Write each conclusion as `confirmed`, `falsified`, or
`inconclusive-because-[flaw]`, name the invariant and evidence file/lines, and
choose one next experiment only after reviewing the saved batch. No per-ticket
hardware checkpoint or automatic rerun is required.
