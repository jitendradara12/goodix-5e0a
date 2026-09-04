# 16 — Frame Decode Reversion to Contiguous 80x64 & Verification Matching

**What to build:** Deploy the clean, reverted contiguous 80x64 frame decoder (which previously produced 52–57 minutiae and +0.828 correlation) and verify matching on physical hardware. Resolve the verification mismatch (`verify-no-match (done)`) by capturing high-minutiae probe frames with firm, steady touch and matching against enrolled gallery prints with score $\ge 12$.

**Blocked by:** None — builds on Ticket 14 (established +0.828 correlation, 52–57 minutiae, and non-zero Bozorth3 scores 3–5/12) and Ticket 15 (falsified stride-132 column-major).

**Status:** superseded (successor: [17-canonical-layout-and-local-contrast.md](17-canonical-layout-and-local-contrast.md))

## Settled facts this ticket builds on (do not re-litigate)

- **Chip provisioning & FDT:** Proven and frozen. 100% silent in empty air (77s+ wait); wakes instantly on physical touch.
- **Framing & Decryption:** Proven and frozen. Canonical ChicagoH decrypted frames of 10564 bytes (`declen=10564`).
- **Stride-132 Column Extraction:** Falsified by Hardware Runs 11 & 12. Inserting 132-byte strides scrambled horizontal raster scanlines, collapsing adjacent column correlation from +0.828 to -0.348 and minutiae from 52–57 to 1. Cleanly reverted.
- **Contiguous 80x64 Decode:** Proven on hardware (Hardware Run 6/9). Decodes 5120 pixels linearly in row-major order: yields `adj_corr = +0.828`, 52–57 minutiae on firm contact, and non-zero Bozorth3 scores (3–5/12).
- **Multi-Stage Enrollment:** Proven and frozen. Completes all 8 stages without deadlock (`enroll-completed`).

## Problem Statement & Root Cause Diagnosis

In recent verification tests, `fprintd-verify` failed with:
```text
Sep 05 00:35:56 sastapc fprintd[158854]: 5e0a frame stats: active=5120, min_v=272, max_v=2548, range=2276, declen=10564, adj_corr=-0.348, all_corr=0.153, dist_corr=-0.102 (native 80x64 WxH)
Sep 05 00:35:56 sastapc fprintd[158854]: 5e0a get_minutiae: ret=0 minutiae_count=1 (image 160x128 WxH, scan_time=0.0042s)
Sep 05 00:35:56 sastapc fprintd[158854]: 5e0a bz3 match: gallery[0]_nrows=1 score=0/12 (probe_nrows=1)
```

### Why Did This Happen?
1. **Unsynchronized Patch in NixOS-Hyprland:** The unified patch file `/home/sastauser/NixOS-Hyprland/modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` had NOT been regenerated from `/tmp/libfprint-goodix`. The staged patch still contained the stride-132 column-major code. Every `nixos-rebuild switch` run by the user was rebuilding the identical broken stride-132 driver.
2. **Minutiae Floor Abort:** Because minutiae collapsed to 1 under stride-132, Bozorth3 tripped the `nrows < 10` floor abort on every comparison.

### The Fix
1. **Regenerated Unified Patch:** Synchronized the clean linear decode to both repo root and `/home/sastauser/NixOS-Hyprland/modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`.
2. **Contiguous Row-Major Decode:** Restored contiguous 12-bit linear decode on first 7,680 bytes (5,120 pixels, 80x64).
3. **Full Min-Max Contrast Normalization:** Ensures valleys map to 0 (white when inverted) and ridges map to 255 (black when inverted).
4. **Persistent Raw Capture:** Added frame dumps to `/dev/shm/live_frame.raw` so captures survive daemon teardown.

## Planned Experiments (One Variable Per Build)

### Experiment A: Verify Contiguous Decode Deployment & Touch Firmness
- Rebuild and switch NixOS configuration.
- Restart fprintd.
- Delete existing prints (`fprintd-delete "$USER"`).
- Enroll right index finger with steady, firm pressure on every stage (`fprintd-enroll`).
- Verify right index finger with firm, steady press (`fprintd-verify`).

### Predicted Journal Signatures
- **Confirm signature (Success):**
  - `5e0a frame stats: adj_corr` restored to $+0.75\text{--}+0.85$ (positive correlation).
  - `5e0a get_minutiae: minutiae_count >= 20` (predicted: 35–55).
  - `5e0a bz3 match: score >= 12` (predicted: 30–80).
  - `Verify result: verify-match (done)`.
- **Falsify signature (Minutiae still starved despite contiguous decode):**
  - `adj_corr` remains negative or minutiae count remains $< 10$ $\implies$ investigate raw frame saved at `/dev/shm/live_frame.raw`.

## Acceptance Criteria (Deployed Driver, Hardware Only)

- [ ] `adj_corr` logged in journal $\ge +0.700$.
- [ ] Both enrollment gallery prints and verification probe frame extract $\ge 20$ minutiae.
- [ ] Bozorth3 match score $\ge 12$ logged in journal against enrolled print.
- [ ] Client output reports `Verify result: verify-match (done)` on physical touch.

## Hardware Run 13 (2026-09-05 01:13–01:14, Deployed Driver)

### Client Evidence

Enrollment completed all eight stages, but four consecutive `fprintd-verify` runs returned `verify-no-match (done)`.

### Journal Evidence

- Every capture reported exactly `nonzero=3728`; this was invariant across enrollment and verification, so it was not a varying fingertip contact ellipse.
- Gallery minutiae counts were `[9, 13, 5, 10, 8, 5, 6, 14]`; five of eight gallery prints were below the Bozorth minimum of 10.
- Probe counts were 5, 10, 12, and 2. The only non-zero verification scores were `3/12`.
- Representative probe: `active=3728 ... adj_corr=0.824 ... minutiae_count=10`, followed by gallery scores no higher than `3/12`.

### Root Assumption Falsified

`3728` has an exact wire-layout explanation: `7680 = 58 * 132 + 24`, and each complete 132-byte block contributes a 36-byte zero pad (24 decoded zero pixels). Decoding the first 7,680 bytes therefore inserts 58 artificial zero bands and stops inside block 59. The claimed high correlation and minutiae were contaminated by these deterministic pad bands.

**Verdict:** falsified. Contiguous first-7,680-byte decode is not a sensor raster, and touch firmness cannot repair it. Superseded by Ticket 17.
