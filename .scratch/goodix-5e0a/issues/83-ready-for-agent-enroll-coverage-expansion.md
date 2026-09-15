# 83: Enrollment Coverage Expansion for Sloppy & Edge-Touch Tolerance

**What to build:** Expand enrollment stages from 8 to 12 (or up to 16) touches so the Milan matching engine can stitch an expansive composite template covering the fingertip, lateral edges, and pad. This enables casual, off-center, and sloppy touches to match reliably on real hardware with positive scores instead of returning `pts=0`.

**Blocked by:** 82 (Enroll-Time Shaping and Pipeline Comparison, closed 2026-09-15 — confirmed Milan pipeline identity and valid multi-touch template stitching).

**Status:** ready-for-agent

## Acceptance Criteria

- [ ] `libfprint-driver/goodix5e0a.c` updates `dev_class->nr_enroll_stages` from 8 to 12 (or 16).
- [ ] `libfprint-driver/goodix_milan.c` aligns `*(u16*)((char*)ctx + 8)` to match the target touch count (e.g. 12).
- [ ] Enrollment on hardware completes across all stages, progressively logging `progress_pct` through 100%, and successfully commits a composite template via `m_templatePack`.
- [ ] Verified on hardware: Casual, off-center, and edge touches of the enrolled finger successfully match with `match=1` and positive match points (`pts > 0`).
- [ ] Strict 0% FAR preserved: Impostor/un-enrolled fingers remain 100% rejected (`match=0 idx=-1 pts=0`).
- [ ] Rule-7 smoke check passes: `journalctl -u fprintd` has zero unhandled timeouts or errors.

## Context & Evidence

- In Ticket 77 Hardware Run 7:
  - Deliberate center presses of enrolled fingers matched cleanly with `pts=83..90`.
  - Casual or light taps produced `match=0 pts=0` because the physical sensor is only 64x80 pixels (~5.1mm x 6.4mm). A casual touch contacting the edge or tip of the finger has near-zero overlap with a template constructed from only 8 center touches.
- In Windows Hello, the enrollment wizard takes 12 to 16 touches and explicitly directs the user to touch the edges, sides, and tip of the finger.
- In `goodix_milan.c`, `m_enrolStartEx` is initialized with `max_images = 16`, but the target touch count was previously clamped to 8 (`*(ctx+8) = 8`). Expanding to 12–16 touches leverages Milan's full template stitching capacity.

## Implementation Plan

One variable: enrollment touch count only. Bursts, TLS, and matching thresholds (`match_score > 0`) remain untouched.

- `libfprint-driver/goodix_milan.c`: Set target touch count `*(u16*)((char*)ctx + 8) = 12;` in `goodix_milan_enroll_start`.
- `libfprint-driver/goodix5e0a.c`: Update `dev_class->nr_enroll_stages = 12;` in `fpi_device_goodixtls5e0a_class_init`.

## Hardware Verify Protocol (user-only; agent has no fingers/sudo)

1. Deploy driver and enroll:
   ```bash
   cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd
   fprintd-delete "$USER"
   sudo systemctl set-environment G_MESSAGES_DEBUG=all
   sudo systemctl restart fprintd
   fprintd-enroll
   ```
   (Follow prompts: touch center 4-5 times, then edges, sides, and tip for remaining touches until complete).
2. Phase 1: Hands off 60s (verify silent / no spontaneous cycles).
3. Phase 2: Test unlocks using PAM (`sudo -v`) or `fprintd-verify`:
   - 5 deliberate center presses.
   - 5 casual / sloppy / edge touches.
   - 5 stranger / wrong finger touches.
4. Inspect journal:
   ```bash
   journalctl -u fprintd --since "5 min ago" --no-pager | grep -E "Milan enrollAddImage|Milan enrollment committed|Milan verify|Milan identify|timed out|Invalid ACK|failed to"
   sudo systemctl set-environment G_MESSAGES_DEBUG=
   ```

## Predicted Journal Signatures

- **Confirm:**
  - Enrollment shows 12 stages progressing to 100% and commits a ~18KB–25KB template.
  - Casual and edge touches produce `match=1 pts=50..90` and successfully unlock.
  - Stranger touches show `match=0 pts=0`.
  - Smoke grep empty of unhandled errors.
- **Falsify:**
  - Enrollment stalls or rejects touches beyond stage 8 (`add_res != 0`), or template commits but casual edge touches still yield `match=0 pts=0`.
- **Inconclusive-because-[flaw]:**
  - Enrollment failed due to dirty finger contact, or user enrolled only the exact center spot 12 times rather than varying edge/side angles.
