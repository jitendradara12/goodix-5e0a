# 87: Restore idle close parking after the FpDevice port

**Status:** closed

**Verdict:** confirmed on deployed hardware, 2026-09-16; evidence below.

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

## Hardware run 2026-09-16 23:34–23:41

Evidence: `/home/sastauser/goodix-ticket87-20260916-233440/`.

- `journal.txt:354`: 23:39:14.076166, PID 21957 parks gen=2 after a match.
- `journal.txt:360`: 23:39:44.003460 service exits, about 29.93s later.
  Next claim uses PID 22494. An in-memory 300s TTL cannot survive that exit.
- `journal.txt:997`: 23:41:31.306578, PID 22494 parks gen=6 after the
  first TTL claim returns no-match. The script incorrectly required a match
  and stopped before a second claim. No-match can still produce a healthy park.
- `phases.txt`: hands off ran 60s and hit the script's timeout, not an early
  timeout. Steady hold returned a match in about 0.94s; observation lasted 60s.
- Wrong-finger PAM: no-match at 23:40:42.081745; FDT-UP reissues through
  23:41:10.516108. A second no-match is logged at cancellation 23:41:12.084021;
  do not claim exactly one status across the whole PAM window without scoping
  terminal cancellation. No Invalid ACK or failed-to lines appear in the file.

Verdict: `inconclusive-because-script-aborted-before-reuse-check`.
Parking itself is observed; reopen/reuse has not been exercised after a park.
Single next experiment: same build, two normally completed claims 5 seconds
apart. Accept match or no-match for the first claim; journal must prove reuse.
No daemon keepalive or driver modification is included in this experiment.

## User-only verification

Use `bash scripts/verify-ticket87.sh` after deployment. The script reuses the
prior safety-phase evidence under the user's AGENTS.md exception, performs
an actual 5-second sleep between verify calls, and saves unfiltered journal output.
It does not change driver code or claim success automatically.

Predictions:
- Confirm: after a completed claim, `parking live TLS session`; next open
  `USB reset skipped (clean close)`; next activation health-checks and logs
  `TLS session reused` at 5s. This tests ticket 87, not ticket 85's extended TTL.
- Falsify: completed idle close remains dirty, probe fails, or transport
  desynchronizes (`Invalid ACK`, `verify-unknown-error`). Stop before more edits.
- Inconclusive-because-client-timeout, missing phases, first claim aborted,
  daemon PID changed during the gap, or no idle park was stamped.

Rule-7 enrolled-match window must have no error grep hits. Held wrong finger
must reject once and withhold subsequent attempts until release, with tolerant
0x34 timeouts allowed in that hold window. A one-shot verify exits on rejection
and cannot alone prove retry withholding; the prior run includes the PAM check.

## Hardware confirmation 2026-09-16 23:58–23:59

Evidence: `/home/sastauser/goodix-ticket87-20260916-235856/journal.txt`.
Both claims are served by PID 30198:

```text
line 207 23:58:57.157390 report_verify_status: result verify-no-match
line 222 23:58:57.158465 5e0a parking live TLS session (gen=2)
line 232 23:59:02.281345 5e0a USB reset skipped (clean close, boot_seq=1)
line 252 23:59:02.294765 5e0a parked TLS session candidate fresh, health-checking (gen=3)
line 258 23:59:02.295328 5e0a TLS session reused (parked 5.1s, gen=3)
line 335 23:59:03.595831 report_verify_status: result verify-match
line 350 23:59:03.596727 5e0a parking live TLS session (gen=4)
```

The health-check interval is 563 microseconds. Only the first claim starts
TLS; no `timed out|Invalid ACK|verify-unknown-error|failed to` matches appear
in this journal. Prior safety phases were not repeated at user request.

Verdict: confirmed for idle-close parking and subsequent reuse on hardware.
This does not confirm ticket 85's longer TTL: 5.1s is inside both TTLs.
Single next experiment: read-only investigation of the daemon's observed
~30s idle exit before proposing any longer-gap run or service change.
