# 84: Optimistic Verify Fast-Path (Sub-50ms Post-Touch Unlock Latency)

**What to build:** An optimistic early-match fast path in `goodix5e0a.c` during verification and identification. If the first frame of a touch burst has high contact area and strong signal, match it against the template immediately. If it matches, report success and complete the claim instantly (~50ms latency) instead of waiting for the full 4-frame burst. If the first frame is partial or fails to match, fall back seamlessly to collecting all 4 frames.

**Blocked by:** 83 (Enrollment Coverage Expansion).

**Status:** ready-for-hardware-verify

## Acceptance Criteria

- [x] In `goodix5e0a_keep_best_frame`: during `VERIFY` or `IDENTIFY` actions, evaluate Frame 1 immediately if contact area is high (`active >= 1500`, `range >= 500`).
- [x] If Frame 1 matches (`match_pts > 0`), the scan SSM completes immediately and reports success without re-issuing `read_image` for frames 2–4.
- [x] If Frame 1 does not match or has weak contact (`active < 1500`), the driver proceeds seamlessly to capture frames 2..4, selecting the best-of-N frame exactly as before (zero penalty on difficult touches).
- [ ] Verified on hardware: Deliberate touches unlock in < 50ms post-touch (feeling instantaneous like Windows Hello).
- [ ] Held-wrong-finger test passes: un-enrolled finger continues into the full burst, rejects, and enters the FDT-UP guard loop without leaking false accepts or prematurely aborting retry gating.
- [ ] Rule-7 smoke check passes: zero `timed out|Invalid ACK|verify-unknown-error|failed to`.

## Context & Evidence

- In Ticket 33 & 38: The driver currently incurs ~160–240ms of latency post-touch simply reading `GOODIX_5E0A_FRAMES_PER_TOUCH = 4` frames sequentially over USB bulk endpoints and decrypting them over TLS before any match is evaluated.
- The Milan matching engine (`goodix_milan_verify_image` / `goodix_milan_identify_image`) takes only ~1–3ms to compute a score on a 64x80 frame once unpacked.
- On a firm touch, Frame 1 often contains a complete, high-contrast impression. Waiting for Frames 2, 3, and 4 is wasted latency when Frame 1 already has sufficient quality to achieve `score > 80`.
- Optimistic verification matches Frame 1 on the fly:
  - **Fast path:** 1 frame transferred + matched $\rightarrow$ unlock in ~50ms.
  - **Slow / fallback path:** Frame 1 doesn't match $\rightarrow$ frames 2, 3, 4 collected $\rightarrow$ best-of-4 evaluated.
  - This provides the maximum possible speedup with zero risk of degraded accuracy.

## Implementation Details

One variable: verify/identify burst termination gating on Frame 1 match.

- `libfprint-driver/goodix5e0a.c`:
  - In `goodix5e0a_keep_best_frame()`:
    - If `(action == FPI_DEVICE_ACTION_VERIFY || self->is_verify || action == FPI_DEVICE_ACTION_IDENTIFY || self->is_identify)` and `self->frame_count == 1 && active >= 1500 && range >= 500`:
      - For verify: Call `goodix_milan_verify_image(self->best_pixels, GOODIX_5E0A_WIDTH, GOODIX_5E0A_HEIGHT, self->tmpl_blob, self->tmpl_len, &match_pts)`. If `match_pts > 0`: log `"5e0a optimistic fast-path match on frame 1: pts=%d, skipping remaining burst"` and `return FALSE;`.
      - For identify: Query gallery prints via `fpi_device_get_identify_data(dev, &prints)`, unpack templates, and call `goodix_milan_identify_image(self->best_pixels, GOODIX_5E0A_WIDTH, GOODIX_5E0A_HEIGHT, blobs, lens, m, &matched_idx, &match_pts)`. If `matched_idx >= 0 && match_pts > 0`: log `"5e0a optimistic fast-path identify match on frame 1: idx=%d pts=%d, skipping remaining burst"` and `return FALSE;`.
    - If not matched (or `active < 1500` / `range < 500`), fall through to re-issue `goodix_tls_read_image` for frames 2..4.
- `tests/tier1_feature/test_f84_optimistic_verify_fast_path.py`:
  - Added hermetic structural test suite verifying gate conditions, verify/identify speculative execution, burst loop fallback, SSM non-advance inside helper, and bare `score` keyword avoidance.
- `tests/tier1_feature/test_f40_warm_activation.py` & `test_f42_conditional_reset.py`:
  - Updated `g_message` budget checks from 23 to 25 to account for the two fast-path journal messages.

## Build and Test Verification

- **Ninja Build (`libfprint-drivers.a`, `libfprint-2.so.2.0.0`):**
  ```
  ninja: Entering directory `/tmp/libfprint-goodix/build'
  [1/3] Compiling C object libfprint/libfprint-drivers.a.p/drivers_goodixtls_goodix5e0a.c.o
  [2/3] Linking static target libfprint/libfprint-drivers.a
  [3/3] Linking target libfprint/libfprint-2.so.2.0.0
  Exit: 0
  ```
- **Unified Patch Sync (`test_f25_patch_sync`):**
  ```
  Ran 9 tests in 0.011s
  OK
  ```
- **Feature 84 Test (`test_f84_optimistic_verify_fast_path`):**
  ```
  Ran 5 tests in 0.001s
  OK
  ```
- **Full Test Suite (`bash tests/run_all_tests.sh`):**
  ```
  Total Tests Passed: 316
  Total Tests Failed: 0
  Total Tests Skipped (env-gated): 1
  Total Execution Time: 5s
  ALL TEST TIERS PASSED PERFECTLY!
  ```
- **Nix Derivation Build:**
  ```
  nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'
  Output store path:
  /nix/store/jycswicwz81kfa7g0bfny24jw3fsbpr2-libfprint-goodix-1.94.5-goodixtls-5e0a
  ```
- **NixOS Module Patch Sync:**
  `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` copied to `/home/sastauser/NixOS-Hyprland/modules/goodix/` (byte-identical).

## Hardware Verify Protocol (user-only; agent has no fingers/sudo)

1. Deploy driver:
   ```bash
   cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd
   sudo systemctl set-environment G_MESSAGES_DEBUG=all
   sudo systemctl restart fprintd
   ```
2. Phase 1: Hands off 60s (verify silent / no spontaneous cycles).
3. Phase 2:
   - 5 fast, deliberate taps of enrolled finger: measure unlock latency (observe if only 1 frame is captured in journal and latency feels instantaneous like Windows Hello).
   - 5 casual / partial touches: verify fall-through to frames 2..4 and successful match.
   - 5 held wrong finger presses: verify attempts withheld until release, zero false accepts, full 4-frame burst evaluated.
4. Inspect journal:
   ```bash
   journalctl -u fprintd --since "5 min ago" --no-pager | grep -E "5e0a frame|Milan verify|Milan identify|fast-path|submitting"
   sudo systemctl set-environment G_MESSAGES_DEBUG=
   ```

## Predicted Journal Signatures

- **Confirm:**
  - Deliberate touches show:
    ```
    5e0a frame 1/4: declen=... active=... range=... quality=... overlap=... score-proxy=...
    5e0a optimistic fast-path match on frame 1: pts=..., skipping remaining burst
    5e0a best frame 1/4: quality=... overlap=... range=... score-proxy=... (submitting)
    5e0a Milan verify: match=1 pts=... (threshold=50)
    ```
    Skipping frames 2, 3, 4; post-touch latency noticeably instantaneous (< 50ms).
  - Weak / partial touches fall through: `5e0a frame 1/4`, `2/4`, `3/4`, `4/4` then `best frame ... submitting`.
  - Wrong finger touches evaluate Frame 1 (`match_pts=0`), fall through to frames 2..4, report no-match, and hold until release without false accepts.
- **Falsify:**
  - Fast-path causes premature rejection, false positive, or USB transfer desync on subsequent claims.
- **Inconclusive-because-[flaw]:**
  - Sensor USB transfer fails or debug logging disabled.
