# 102: Restore Known-Working Baseline (Revert Tickets 100 & 101)

**What to build:** Revert commits `75d7307` (Ticket 101) and `ec5723d` (Ticket 100) to restore the exact known-working driver baseline from `39dad45` / `fd83146`.

**Blocked by:** none.

**Status:** closed (verdict: falsified — 39dad45 baseline lacks per-touch burst reset, producing degenerate templates with duplicated partial frames; fprintd-verify yields verify-no-match with pts=0 on hardware; successor 103 opened)

## Rationale & Root Cause Analysis

1. **Hardware Confirmation of Baseline (`39dad45`):**
   - At commit `39dad45` (Tickets 97, 98, 99), live hardware runs on Fedora 44 and NixOS confirmed 10 fingers enrolled and PAM desktop login working cleanly with positive match points (`pts=71`).
2. **Defects Introduced by Ticket 100 (`ec5723d`):**
   - Implemented without hardware testing by an automated agent bot.
   - Substituted the O(n^2) selection sort in `goodix_milan.c` with an allocation-heavy bottom-up merge sort (`sh_qsort`).
   - Altered PE section loader and export table resolution metadata parsing.
   - Refactored `goodix5e0a_identify_best_frame`, fast-path match handling, and GLib error passing.
   - Resulted in consistent `verify-no-match` / `score=-7` on all verify attempts despite 12/12 enrollment.
3. **Flawed Mitigation in Ticket 101 (`75d7307`) & Abortive Ticket 102 attempts:**
   - Ticket 101 added per-touch burst resets during enrollment, which produced degenerate/truncated templates (~21KB vs ~35-38KB working baseline).
   - An attempted patch (`0412d05`) enforced `overlap >= 25`, but live hardware produces `overlap=10..22`, causing 100% of enrollment touches to fail with `enroll-swipe-too-short`.
4. **Action:**
   - Drop commits `75d7307` and `ec5723d` entirely.
   - Return driver sources (`goodix.c`, `goodix5e0a.c`, `goodix_milan.c`, `goodixtls.c`, `goodix5xx.c`, `goodix5xx.h`, `libfprint-goodix.nix`) and unit tests to the verified `39dad45` state.

## Verification Checklist

- [x] Full test suite clean: 353/353 unit and adversarial tests pass on the restored baseline (`bash tests/run_all_tests.sh`).
- [x] Hardware enrollment: `sudo fprintd-enroll "$USER"` completes 12 touches to 100% without spurious swipe-too-short rejections.
- [x] Hardware verification: `fprintd-verify "$USER"` executed on live hardware.

## Predicted Signatures

- **Confirm (baseline restored):**
  - `fprintd-enroll "$USER"` advances stage-by-stage (1/12 .. 12/12) to `enroll-completed`.
  - `fprintd-verify "$USER"` logs `Milan verify: match=1 pts=...` and PAM login succeeds.
- **Falsify:**
  - `fprintd-verify` reports `verify-no-match` with `pts=0`.

## Hardware Run Record (2026-10-01 00:55–00:56, sastapc, fprintd[428088]) — FALSIFIED

1. Enrollment completed 12 stages, but because baseline `39dad45` does not reset burst state between touches:
   - Touch 1 banked 4 frames (winner: `overlap=3 range=1933`).
   - Touches 2–6 incremented `frame_count` past 4 (`5/4`..`9/4`), stopped after 1 frame, and re-submitted touch 1's frame 4.
   - Touches 7–11 repeated touch 7's frame 10 (`overlap=11 range=1920`).
   - Touch 12 submitted frame 15 (`overlap=11 range=2101`).
   - Master template committed with only 3 distinct partial impressions (24,846B / 31,822B).
2. Verification:
   - User verified with a normal press (`overlap=18 range=1916`).
   - Milan engine compared normal press against the degenerate template: `5e0a Milan verify: match=0 pts=0` -> `result verify-no-match`.
3. Verdict: **FALSIFIED**. Baseline `39dad45` without per-touch burst reset cannot reliably verify. Successor: Ticket 103 (restore per-touch burst reset without any bogus overlap gate).
