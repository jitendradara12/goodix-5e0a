# 84: Optimistic Verify Fast-Path (Sub-50ms Post-Touch Unlock Latency)

**What to build:** An optimistic early-match fast path in `goodix5e0a.c` during verification and identification. If the first frame of a touch burst has high contact area and strong signal, match it against the template immediately. If it matches, report success and complete the claim instantly (~50ms latency) instead of waiting for the full 4-frame burst. If the first frame is partial or fails to match, fall back seamlessly to collecting all 4 frames.

**Blocked by:** 83 (Enrollment Coverage Expansion).

**Status:** ready-for-agent

## Acceptance Criteria

- [ ] In `goodix5e0a_keep_best_frame` or `goodix5e0a_on_read_img`: during `VERIFY` or `IDENTIFY` actions, evaluate Frame 1 immediately if contact area is high (`active >= 1500`, `range >= 500`).
- [ ] If Frame 1 matches (`match_score > 0`), the scan SSM completes immediately and reports success without re-issuing `read_image` for frames 2–4.
- [ ] If Frame 1 does not match or has weak contact (`active < 1500`), the driver proceeds seamlessly to capture frames 2..4, selecting the best-of-N frame exactly as before (zero penalty on difficult touches).
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

## Implementation Plan

One variable: verify/identify burst termination gating on Frame 1 match.

- `libfprint-driver/goodix5e0a.c`:
  - When `action == FPI_DEVICE_ACTION_VERIFY || self->is_verify || self->is_identify`:
  - If `self->frame_count == 1` and `frame_active >= 1500 && frame_range >= 500`:
    - Run speculative `goodix_milan_verify_image` (or identify).
    - If `match_score > 0`: bank as best frame, bypass remaining burst reads, and jump directly to `deliver_frame`.
    - If `match_score == 0`: continue banking and re-issue `goodix_tls_read_image` for frames 2..4.

## Hardware Verify Protocol (user-only; agent has no fingers/sudo)

1. Deploy driver:
   ```bash
   cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd
   sudo systemctl set-environment G_MESSAGES_DEBUG=all
   sudo systemctl restart fprintd
   ```
2. Phase 1: Hands off 60s (silent).
3. Phase 2:
   - 5 fast, deliberate taps of enrolled finger: measure unlock latency (observe if only 1 frame is captured in journal).
   - 5 held wrong finger presses: verify attempts withheld until release, zero false accepts.
4. Inspect journal:
   ```bash
   journalctl -u fprintd --since "5 min ago" --no-pager | grep -E "5e0a frame|Milan verify|Milan identify|fast-path|submitting"
   sudo systemctl set-environment G_MESSAGES_DEBUG=
   ```

## Predicted Journal Signatures

- **Confirm:**
  - Deliberate touches show `5e0a frame 1/4` followed immediately by `Milan verify: match=1` (or identify), skipping frames 2, 3, 4; wall-clock latency noticeably instantaneous (< 50ms).
  - Sloppy or weak touches fall through to `5e0a frame 2/4`, `3/4`, `4/4` and select the best frame.
  - Impostor touches evaluate Frame 1 (`match=0`), collect all 4 frames, evaluate winner (`match=0`), and hold until lift.
- **Falsify:**
  - Fast-path causes premature rejection or USB bulk endpoint read out-of-sync on subsequent claims.
- **Inconclusive-because-[flaw]:**
  - Sensor USB transfer fails or debug logging disabled.
