# 47 — Verify-Retry Finger Release Guard (Prevent 3-Try Burn on Continuous Touch)

**What to build:**
When a verification attempt fails to match, PAM (`pam_fprintd`) immediately issues Retry #2 within ~15ms. Because Ticket 20 bypassed finger-lift polling to deliver sub-300ms verification on match, the resting finger immediately triggers CMD `0x32` (`FDT_DOWN`), rapidly burning Attempts 2 and 3 in $<200\text{ ms}$ on a single continuous touch.
We build a `retry_guard` state machine transition in `goodix5e0a.c` that intercepts consecutive retries within 2000ms:
1. On verify image delivery: Set `self->retry_guard = TRUE` and record `retry_guard_mono = g_get_monotonic_time ()`. Complete SSM immediately to preserve sub-300ms instant unlock on matches.
2. If PAM immediately retries (`retry_guard == TRUE` and `delta < 2000ms`): Jump the scan SSM to `SCAN_5E0A_FDT_UP_1` (CMD `0x34`).
3. CMD `0x34` waits for physical finger release: While the user holds their finger down, retries DO NOT fire.
4. When finger release is detected: Clear `retry_guard = FALSE` and jump directly to `SCAN_5E0A_FDT_DOWN` (CMD `0x32`), armed in empty air for the genuine next touch.

**Blocked by:** None.

**Status:** closed

**Verdict:** CONFIRMED on hardware 2026-09-09 (deployed driver).

## Hardware result 2026-09-09 — falsified as specified

Wrong-finger held continuously across two `fprintd-verify` invocations
(right-ring-finger, enrolled — matches fine with normal taps per ticket 46,
so the no-matches here are the awkward-hold press, valid guard-test input):
both invocations returned `verify-no-match (done)` on the SAME hold, i.e.
Attempt 2 FIRED while pressed. Journal shows the guard cycling ~1s/round:

`retry guard active (delta=39 ms): awaiting finger release` →
`retry guard: release ok, arming FDT DOWN` → (×3 cycles in ~2s, PID 16943)

So `0x34` reports "release ok" without a physical release, FDT_DOWN
re-arms onto the still-held finger as a "new touch", and the retry burns
anyway — slowed (~1s spacing vs ~15ms) but not prevented. Two candidate
causes: (a) driver treats a `0x34` timeout/error as release
(`on_fdt_up_reply` falls through to clear+arm on error); (b) MCU reports
release while held. D34 evidence below decides.

## Single next experiment (user, one held retry)

`fprintd-verify` with wrong finger held, then within 2s a second
`fprintd-verify` still holding, then:
`journalctl -u fprintd --since "5 min ago" --no-pager | grep -a -E "retry guard|D34" | tail -n 12`
- Confirm (a): `D34` shows timeout/tolerant-error then `release ok` →
  fix is driver-side (don't clear guard on error; re-issue `0x34`).
- Confirm (b): `5e0a D34 finger release reply: len=…` success while held →
  fix is sensor-side interpretation (0x34 isn't a true release gate).

## Diagnostic result 2026-09-09 — cause (a) CONFIRMED

Held-retry journal shows `5e0a D34 reply (tolerant): Command timed out:
0x34` followed immediately by `release ok, arming FDT DOWN`. Timeout
treated as release — driver-side, as hypothesized.

## Fix (2026-09-09, one variable: 0x34 error-path treatment)

`goodix5e0a_on_fdt_up_reply`: on error with a live guard, keep the guard
and re-issue the same `0x34` probe (2000ms) instead of clearing arming
FDT_DOWN; the retry claim parks in FDT_UP until a genuine release reply.
`CANCELLED` (deactivate teardown) marks failed and never re-issues
(orphaned-SSM guard via `scan_ssm == ssm`). Success path unchanged.

## Re-verify result 2026-09-09 — CONFIRMED, ticket closed

Same held-retry procedure on the fixed driver: Attempt 2 blocked with no
result while held (user had to lift); journal shows the predicted loop —
`D34 timed out: 0x34` + `finger still present, re-issuing FDT UP` every
~2s (20:16:27→35), zero `release ok` until the lift, then `D34 finger
release reply: len=16` + `release ok, arming FDT DOWN`, and the re-tap
fired Attempt 2 (`verify-no-match`, correct for a wrong finger). All four
acceptance criteria green: hands-off silence (`0` frame-stats), instant
unlock on genuine taps (per ticket 46 `verify-match` runs), no Attempts
2/3 while held, Attempt 2 only after lift + re-tap.

## Predicted journal signatures (pre-run; confirm branch matched)

- Confirm: held wrong finger, `fprintd-verify; sleep 1; fprintd-verify` →
  Attempt 1 `verify-no-match`; Attempt 2 BLOCKS (>2s, no result) while
  held, journal shows `awaiting finger release` + `finger still present,
  re-issuing FDT UP` repeating, zero `release ok`, zero second `no-match`.
  Lift → `D34 finger release reply` + `release ok` → re-tap fires Attempt 2.
- Falsify: second `no-match` while held with no lift → re-issue isn't
  reaching the MCU or `0x34` auto-releases; next experiment is USB capture
  of the re-issued `0x34` window.

## Acceptance criteria (deployed driver, hardware only)
- [ ] Hands off 60s: Device remains completely silent in FDT DOWN wait.
- [ ] Genuine finger tap: Instant unlock (<200ms) preserved.
- [ ] Wrong finger held continuously: Attempt 1 fails (`verify-no-match`), driver logs `5e0a retry guard active (delta=...): awaiting finger release` (debug env: `G_MESSAGES_DEBUG=all`). Attempts 2 and 3 DO NOT fire while finger remains pressed.
- [ ] Wrong finger lifted and re-tapped: Driver logs `5e0a retry guard: release ok, arming FDT DOWN` (debug env). Attempt 2 fires only after second physical press.
