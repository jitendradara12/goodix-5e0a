# 87: Restore idle close parking after the FpDevice port

**Status:** ready-for-hardware-verify

**Blocked by:** None. Blocks hardware acceptance of 85.

## Evidence and scope

User supplied `/home/sastauser/goodix-ticket85-journal.txt`, PID 91142,
2026-09-16. Lines 598, 607, 625 show close at 22:46:28.029607,
USB reset on dirty close at 22:46:28.039904, then cold activation.
Lines 785, 803, 820 repeat the sequence after a successful match.
No park messages appear. This is new evidence for the close/reopen path;
ticket 75's open-held orphan shutdown remains unchanged.

`dev_close` frees the scan and calls `goodix_dev_deinit` without invoking
`goodix5e0a_deactivate`. Only the latter stamps the park and marks clean.
The image-device to FpDevice port removed automatic deactivation.

One variable: route healthy, already-idle close through existing parking.
Keep ticket 85's 300s TTL fixed. Do not park after freeing an active scan.
Active/error closes retain their previous cleanup. No changes to matching,
FDT timeouts, cancellation loops, or the ticket-75 orphan check.

## Implementation and checks

- `dev_close`: if scan is NULL, warm_ok is true and TLS is alive, invoke
  existing deactivate before deinit. This selects its success-only park
  branch, so it cannot complete CLOSE through an action-error callback.
- Existing park branch retains retry guard/monotonic state and advances
  the activation generation before stamping the park.
- Structural regression test: `python3 -m unittest tests.tier1_feature.test_f87_close_park`.
  Before fix: FAIL, missing idle-close gate. After fix: PASS.
- With f38/f42 regression checks: 18 tests, OK. This does not establish
  runtime USB behavior; deployed evidence is still required.

## Build evidence

- `bash tests/run_all_tests.sh`: runner reports 320 tests, 0 failures,
  1 skip after flake synchronization. The skip is the absent native harness;
  the runner's total includes skipped tests. Log: `/tmp/opencode/ticket87-tests.log`.
- `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'`:
  exit 0, `/nix/store/q2qbsdmcjcz8zkcffywyfbyyrmdi9h08-libfprint-goodix-1.94.5-goodixtls-5e0a`.
- Repo/flake patch SHA256:
  `8aa6b733ec7868584f8484535162d7ca69e929947a7678c2eb23c104461dfac3`.
- `bash -n scripts/verify-ticket87.sh`: exit 0. Script not executed by agent.

## User-only verification

Use `bash scripts/verify-ticket87.sh` after deployment. The script prompts
for timestamped hands-off and steady-hold phases, performs an actual
90-second sleep between verify calls, and saves unfiltered journal output.
It does not change driver code or claim success automatically.

Predictions:
- Confirm: after a completed claim, `parking live TLS session`; next open
  `USB reset skipped (clean close)`; next activation health-checks and logs
  `TLS session reused`. At 90s this also exercises ticket 85's extended TTL.
- Falsify: completed idle close remains dirty, probe fails, or transport
  desynchronizes (`Invalid ACK`, `verify-unknown-error`). Stop before more edits.
- Inconclusive-because-client-timeout, missing phases, failed first match,
  daemon PID changed during the gap, or no idle park was stamped.

Rule-7 enrolled-match window must have no error grep hits. Held wrong finger
must reject once and withhold subsequent attempts until release, with tolerant
0x34 timeouts allowed in that hold window. A one-shot verify exits on rejection
and cannot alone prove retry withholding; use the PAM prompt in the script.

Conclude only confirmed / falsified / inconclusive-because-[flaw], plus the
single next experiment. Hardware acceptance is not yet checked.
