# 103: Per-Touch Enrollment Burst Reset Without Overlap Gating

**What to build:** Reset burst frames on the enroll-continue path in `goodix5e0a_on_read_img` (`goodix5e0a_reset_touch_frames (self)` immediately before `fpi_ssm_next_state (ssm)`). This ensures every one of the 12 enrollment touches captures a fresh 4-frame burst and banks its own winner, preventing template replication without imposing any artificial overlap floor (NO `overlap >= 25` gating).

**Blocked by:** none.

**Status:** closed (verdict: falsified-verify — 12 distinct enrollment touches completed cleanly to 100% and committed a 24,903B template, confirming burst reset works; but fprintd-verify failed with match=0 pts=0 due to gain 1.0 leaving frame contrast at overlap <= 6 below the Milan extractor threshold score -7; successor 104 opened for contrast gain 1.5 calibration)

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
- [x] Hardware enrollment: `sudo fprintd-enroll "$USER"` completes across 12 distinct touches without swipe-too-short rejections.
- [x] Hardware verification: `fprintd-verify "$USER"` executed on live hardware.

## Hardware Run Record (2026-10-01 11:13:41–11:13:52, sastapc, fprintd[487261]) — FALSIFIED-VERIFY

1. Enrollment:
   - 12 distinct touches captured and banked cleanly:
     - Touch 1: `overlap=10 range=1845`
     - Touch 2: `overlap=7 range=1904`
     - Touch 3: `overlap=8 range=1939`
     - Touches 4–12 logged distinct impressions.
   - Template committed cleanly: `5e0a Milan enrollment committed successfully! (template size: 24903 bytes)`.
   - No `res=131`, no stall, no `swipe-too-short` rejection.
2. Verification:
   - User verified with multiple firm touches (11:13:48 and 11:13:52).
   - Probe 1 banked frame: `quality=0 overlap=6 range=1783 score-proxy=6`.
   - Probe 2 banked frame: `quality=0 overlap=3 range=1929 score-proxy=3`.
   - Milan verify returned `5e0a Milan verify: match=0 pts=0` -> `verify-no-match`.
3. Root cause:
   - At `GOODIX_5E0A_CONTRAST_GAIN = 1.0f`, probe frames have low contrast gradients (`overlap <= 6`).
   - Milan extractor threshold requires higher gradient contrast to extract minutiae constellations (`score=-7` when overlap <= 6).
   - Successor: Ticket 104 (Calibrate contrast gain to 1.5f).
