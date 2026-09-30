# 102: Restore Known-Working Baseline (Revert Tickets 100 & 101)

**What to build:** Revert commits `75d7307` (Ticket 101) and `ec5723d` (Ticket 100) to restore the exact known-working driver baseline from `39dad45` / `fd83146`.

**Blocked by:** none.

**Status:** ready-for-hardware-verify

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
- [ ] Hardware enrollment: `sudo fprintd-enroll "$USER"` completes 12 touches to 100% without spurious swipe-too-short rejections.
- [ ] Hardware verification: `fprintd-verify "$USER"` achieves `verify-match (done)` with positive match score.

## Predicted Signatures

- **Confirm (baseline restored):**
  - `fprintd-enroll "$USER"` advances stage-by-stage (1/12 .. 12/12) to `enroll-completed`.
  - `fprintd-verify "$USER"` logs `Milan verify: match=1 pts=...` and PAM login succeeds.
- **Falsify:**
  - `fprintd-verify` reports `verify-no-match` with `pts=0`.
