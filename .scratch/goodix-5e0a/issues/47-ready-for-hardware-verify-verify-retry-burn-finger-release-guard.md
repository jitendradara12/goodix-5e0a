# 47 — Verify-Retry Finger Release Guard (Prevent 3-Try Burn on Continuous Touch)

**What to build:**
When a verification attempt fails to match, PAM (`pam_fprintd`) immediately issues Retry #2 within ~15ms. Because Ticket 20 bypassed finger-lift polling to deliver sub-300ms verification on match, the resting finger immediately triggers CMD `0x32` (`FDT_DOWN`), rapidly burning Attempts 2 and 3 in $<200\text{ ms}$ on a single continuous touch.
We build a `retry_guard` state machine transition in `goodix5e0a.c` that intercepts consecutive retries within 2000ms:
1. On verify image delivery: Set `self->retry_guard = TRUE` and record `retry_guard_mono = g_get_monotonic_time ()`. Complete SSM immediately to preserve sub-300ms instant unlock on matches.
2. If PAM immediately retries (`retry_guard == TRUE` and `delta < 2000ms`): Jump the scan SSM to `SCAN_5E0A_FDT_UP_1` (CMD `0x34`).
3. CMD `0x34` waits for physical finger release: While the user holds their finger down, retries DO NOT fire.
4. When finger release is detected: Clear `retry_guard = FALSE` and jump directly to `SCAN_5E0A_FDT_DOWN` (CMD `0x32`), armed in empty air for the genuine next touch.

**Blocked by:** None.

**Status:** ready-for-hardware-verify

## Acceptance criteria (deployed driver, hardware only)
- [ ] Hands off 60s: Device remains completely silent in FDT DOWN wait.
- [ ] Genuine finger tap: Instant unlock (<200ms) preserved.
- [ ] Wrong finger held continuously: Attempt 1 fails (`verify-no-match`), driver logs `5e0a retry guard: awaiting finger release (0x34)`. Attempts 2 and 3 DO NOT fire while finger remains pressed.
- [ ] Wrong finger lifted and re-tapped: Driver logs `5e0a retry guard: finger release confirmed, arming FDT DOWN`. Attempt 2 fires only after second physical press.
