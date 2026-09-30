# 103: Per-Touch Enrollment Burst Reset Without Overlap Gating

**What to build:** Reset burst frames on the enroll-continue path in `goodix5e0a_on_read_img` (`goodix5e0a_reset_touch_frames (self)` immediately before `fpi_ssm_next_state (ssm)`). This ensures every one of the 12 enrollment touches captures a fresh 4-frame burst and banks its own winner, preventing template replication without imposing any artificial overlap floor (NO `overlap >= 25` gating).

**Blocked by:** none.

**Status:** ready-for-hardware-verify

## Rationale & Root Cause

1. **Why `39dad45` Failed in Ticket 102:**
   - In baseline `39dad45`, `goodix5e0a_reset_touch_frames (self)` was never called between enrollment touches.
   - When touch 1 completed 4 frames, `frame_count` remained at 4. On touches 2..12, `keep_best_frame` saw `frame_count >= 4` on the very first frame and stopped banking immediately.
   - If that single frame had a lower proxy score than touch 1's winner, `best_pixels` was never updated.
   - Hardware logs from 2026-10-01 00:55–00:56 proved that 12 enrollment stages submitted only 3 distinct impressions (mostly duplicates of touch 1's 3% overlap edge). Verification with a normal press failed with `match=0 pts=0`.
2. **Why the Abortive Attempt Failed with `enroll-swipe-too-short`:**
   - An attempted patch added `if (self->best_overlap < 25) retry_enroll(TOO_SHORT)`.
   - On real hardware, touch overlap values are naturally 2–22. Gating on `overlap >= 25` caused 100% of touches to be rejected with `enroll-swipe-too-short`.
   - AGENTS.md rule: "Do NOT gate enrollment on overlap >= 25 (real hardware captures report overlap 7–18, causing instant swipe-too-short rejection on all touches)."
3. **The Fix:**
   - Add `goodix5e0a_reset_touch_frames (self);` in the enroll-continue branch in `goodix5e0a_on_read_img` right before `fpi_ssm_next_state (ssm)`.
   - Maintain the standard `self->best_active >= 64` threshold (no overlap gating).
   - Each of the 12 enrollment touches will capture 4 frames (`1/4`..`4/4`), bank the highest quality frame from that touch, and stitch a full composite template covering center, pad, tip, and edges.

## Verification Checklist

- [x] Driver edit: `goodix5e0a_reset_touch_frames (self)` added to enroll-continue branch (+1 line, 1997/2000 lines).
- [x] Unit test: `tests/tier1_feature/test_f101_per_touch_burst_reset.py` passes (3/3).
- [x] Full test suite: 356/356 tests pass (`bash tests/run_all_tests.sh`).
- [x] Nix derivation: builds cleanly via `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'`.
- [ ] Hardware enrollment: `sudo fprintd-enroll "$USER"` completes across 12 distinct touches without swipe-too-short rejections.
- [ ] Hardware verification: `fprintd-verify "$USER"` achieves `verify-match (done)` with `match=1` and `pts > 0`.

## Predicted Journal Signatures

- **Confirm:**
  - Enrollment journal shows every touch 1..12 capturing `frame 1/4 .. 4/4` (no `5/4+` numbering).
  - Each touch logs distinct frame statistics in `enrollment quality check: active=5120 range=... quality=0 overlap=...`.
  - Composite template commits cleanly (size ~30KB–39KB).
  - `fprintd-verify "$USER"` logs `5e0a Milan verify: match=1 pts=...` and PAM login succeeds.
- **Falsify:**
  - Verification fails with `match=0 pts=0` even after enrolling 12 distinct 4-frame touches.
