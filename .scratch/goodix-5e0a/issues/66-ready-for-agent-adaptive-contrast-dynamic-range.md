# 66 — Adaptive Contrast Dynamic Range & Ridge Boundary Preservation

**What to build:**
Eliminate severe dynamic range clipping in `process_raw_frame` where high-energy ridge residuals from -375 to +293 are currently flattened to solid 0 and 255 by the linear midpoint formula `CLAMP(128 + residual * 1.0f, 0, 255)`. Replace hard saturation with soft-knee scaling and pre-upscale ridge boundary sharpening:
1. **Dynamic Range Preservation**: In `libfprint-driver/goodix5e0a.c:process_raw_frame`, apply contrast normalization scaled by the empirical residual envelope or soft-knee curve rather than hard saturation, ensuring that ridge peaks and valleys retain continuous intensity gradients for `mindtct`.
2. **Pre-Upscale Ridge Sharpening**: Apply a lightweight 3x3 unsharp mask / Laplacian sharpening before 2x bilinear interpolation, counteracting the low-pass blurring effect of bilinear upscaling and delivering high-contrast edge gradients to NBIS.

**Blocked by:** Ticket 65 (`65-ready-for-agent-enroll-stages-and-settling-burst.md`).

**Status:** ready-for-agent

---

## 1. Problem & Diagnostic Evidence

1. **Severe Ridge Saturation in Live Journal**:
   Live journal stats consistently report:
   ```text
   5e0a local contrast: min=-375.83 max=293.22 range=669.06 window=3x3 gain=1.00
   ```
   Under the current formula:
   $$\text{pixel} = \text{CLAMP}\left(128 + \text{residual} \times 1.0, 0, 255\right)$$
   - Any negative residual $< -128$ (e.g. down to -375) saturates to 0 (flat black).
   - Any positive residual $> +127$ (e.g. up to +293) saturates to 255 (flat white).
   Over $40\%$ of the dynamic range is destroyed at the extremes, turning ridge valleys into broad flat black bands and ridge peaks into clipped white plateaus. This degrades NBIS `mindtct` orientation and minutiae position accuracy.
2. **Bilinear Upscaling Blur**:
   2x bilinear interpolation smooths pixel gradients, reducing the local high-frequency contrast necessary for NBIS's 8x8 DFT direction maps to distinguish closely-spaced ridge bifurcations.

---

## 2. Invariants & Guardrails

- `0x32` timeout 0, `0x34` finite guard loop, TLS park lifecycle, and `CANCELLED` non-reissue remain strictly untouched.
- `bz3_threshold = 14` remains locked.
- Minutiae yield on empty air must strictly remain 0 (verified by Tier 2 boundary test `test_b16_empty_air_thresholds.py`).

---

## 3. Acceptance Criteria

- [ ] `libfprint-driver/goodix5e0a.c`: `process_raw_frame` dynamic range preserves ridge gradients without flattening $>10\%$ of pixels to 0 or 255.
- [ ] Tier 2 empty-air rejection tests pass 100% (empty air produces 0 minutiae).
- [ ] Offline benchmark against `experiments/fingerprint.pgm` shows increased minutiae reliability and equal or higher genuine Bozorth scores.
- [ ] Full test runner passes: `bash tests/run_all_tests.sh` (100% green).
- [ ] Hardware verification: Genuine Bozorth scores increase on hardware without increasing FAR on un-enrolled fingers.
