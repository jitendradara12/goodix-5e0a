# 14 — Image geometry, minutiae extraction, and Bozorth3 verification matching

**What to build:** Diagnose and resolve the `score 0/12` verification mismatch. Enable the driver to produce high-confidence minutiae clusters that Bozorth3 successfully matches on the first touch (`verify-match (done)`).

**Blocked by:** None — builds on Ticket 13 (ChicagoH config, D32 energy gating, full 10564B frames, and 8/8 enrollment proven and frozen).

**Status:** in-progress

## Settled facts this ticket builds on (do not re-litigate)

- **Chip provisioning & FDT:** Proven and frozen. Sensor stays completely silent in empty air (77s+ hardware wait) and fires instant hardware interrupt on touch.
- **Framing & Decryption:** Proven and frozen. Full 10564-byte decrypted frames (`declen=10564`), 7040 decoded 12-bit words with exactly 5120 contiguous active pixels (indices 0..5119) and 1920 trailing padding zeros (indices 5120..7039).
- **Multi-Stage Enrollment:** Proven and frozen. `fprintd-enroll` completes all 8 stages without deadlock (`enroll-completed`) and persists template to `/var/lib/fprint/sastauser/goodixtls5e0a/0/7`.
- **Synchronous Deactivation:** Proven and frozen. Teardown cancels state immediately without colliding sleep commands.

## Problem Statement

In `fprintd-verify`, the driver captures the probe frame, decrypts 10564 bytes, and runs minutiae extraction, but Bozorth3 reports `score 0/12` across all 8 gallery prints:
```
Sep 04 20:40:43 sastapc fprintd[70793]: Minutiae scan completed in 0.003354 secs
Sep 04 20:40:43 sastapc fprintd[70793]: score 0/12
Sep 04 20:40:43 sastapc fprintd[70793]: score 0/12
... (8 times)
Sep 04 20:40:43 sastapc fprintd[70793]: report_verify_status: result verify-no-match
```

## Hypotheses & Predicted Journal Signatures

### Hypothesis 1: Bozorth3 Minutiae Floor Hard Abort (`MIN_COMPUTABLE_BOZORTH_MINUTIAE = 10`)
- **Mechanism:** In `nbis/bozorth3/bozorth3.c:642-672`, if `pstruct->nrows < 10` or `gstruct->nrows < 10`, Bozorth3 immediately returns `ZERO_MATCH_SCORE` without comparing minutiae clusters.
- Libfprint currently does not log the minutiae count in `fpi_print_bz3_match` or `fp_image_detect_minutiae`.
- **Confirm signature:** Logging minutiae count reveals `probe minutiae < 10` or `gallery minutiae < 10`.
- **Falsify signature:** Both probe and gallery have $\ge 10$ minutiae, but edge matching yields 0 compatible pairs.

### Hypothesis 2: Sensor Aspect Ratio & Transposition (80x64 vs 64x80)
- **Mechanism:** In `wbdi.dll:0x18004ea50`, pixels are unpacked as `row = pixel_index % 64`, `col = pixel_index / 64`.
- In `tool.py`, PGM output is written as `64 80` (width 64, height 80).
- In `goodix511.c`, dimensions are `GOODIX511_WIDTH = 64, GOODIX511_HEIGHT = 80`.
- If width and height are transposed, ridges run perpendicular to the orientation expected by NBIS directional filters, or ridge spacing is distorted.
- **Confirm signature:** Transposing mapping to 64x80 increases minutiae count and correlation.
- **Falsify signature:** Transposing reduces active columns or degrades adjacent column correlation below 0.4.

### Hypothesis 3: 2x Bilinear Interpolation Artifacts
- **Mechanism:** `fpi_image_resize (img, 2, 2)` scales the image using `pixman` bilinear filtering. If the filter blurs fine ridge endings/bifurcations, `mindtct` may detect fewer true minutiae than on the raw 80x64 grid.
- **Confirm signature:** Native resolution yields higher minutiae reliability scores than 2x resized.
- **Falsify signature:** Native resolution yields fewer minutiae due to `PERIMETER_PTS_DISTANCE = 10` boundary clipping.

### Hypothesis 4: Ridge Polarity & Dynamic Range Normalization
- **Mechanism:** Capacitive sensor registers higher counts on touch contact (ridges ~2800 ADC, valleys ~800 ADC).
- NBIS `mindtct` (`detect.c:91`) expects 0 = black (ridge), 255 = white (valley).
- Linear min-max normalization:
  `norm = ((val - min_v) * 255) / range`
  With `FPI_IMAGE_COLORS_INVERTED`, high ADC becomes low pixel (black = ridge).
- If local contrast across the sensor is uneven, global min-max normalization may wash out peripheral ridges.

## Review Directives & Invariants
- **Never lower NBIS floors or match thresholds:** `MIN_COMPUTABLE_BOZORTH_MINUTIAE = 10` and `bz3_threshold = 12` are invariant biometric standards. If `nrows < 10`, fix content/contrast/pipeline, never constants.
- **Strict $W \times H$ convention everywhere:** $W = \text{width/columns/horizontal}$ (native 80, scaled 160), $H = \text{height/rows/vertical}$ (native 64, scaled 128). Never invert or mix notations.
- **One variable per build:** Experiment A changes zero image processing code. It adds diagnostic logging only.

## Planned Experiments (One Variable Per Build)

1. **Experiment A (Minutiae Diagnostic Observability):**
   - In `goodix5e0a.c`: Log `decoded_px`, `nonzero_px`, `min`, `max`, `assumed_geometry=80x64 (WxH)`, and layout span (`first_nz`, `last_nz`).
   - In `fp-image.c`: Log `get_minutiae` result and `minutiae_count` for each captured frame.
   - In `fpi-print.c`: Log `probe_nrows` and `gallery[i]_nrows` during `bz3_match`, with explicit warning if the floor `< 10` is tripped.
   - **Predicted journal signatures:**
     - *Branch 1 (Minutiae starvation):* `5e0a minutiae: detected=K` with $K < 10$, or `5e0a bz3 floor tripped: probe_nrows < 10` $\implies$ Next step: isolate 2x upscale vs native and polarity inversion.
     - *Branch 2 (Geometric mismatch):* `5e0a bz3 match: probe_nrows >= 10 gallery[i]_nrows >= 10 score=0/12` $\implies$ Next step: investigate column-major vs row-major transpose or aspect ratio distortion.

## Hardware Run 2 (2026-09-04 22:03–22:08, Deployed Driver — Exp B)

### Journal Evidence
- **Enrollment completed 8/8 stages**, but minutiae counts were starved:
  - Touches registered 0–5 minutiae (only 1 touch registered 14 minutiae).
- **Verification failure:**
  ```text
  Sep 04 22:08:05 sastapc fprintd[95347]: 5e0a frame stats: active=5120, min_v=540, max_v=2668, range=2128, declen=10564, adj_corr=-0.212, all_corr=0.219, dist_corr=0.242 (native 80x64 WxH)
  Sep 04 22:08:05 sastapc fprintd[95347]: 5e0a scaled image: 160x128 (WxH) flags=0x04 active=5120 range=2128
  Sep 04 22:08:05 sastapc fprintd[95347]: 5e0a get_minutiae: ret=0 minutiae_count=0 (image 160x128 WxH, scan_time=0.0137s)
  Sep 04 22:08:05 sastapc fprintd[95347]: Failed to detect minutiae: No minutiae found
  ```
- **Flaw identified:**
  - In `goodix5e0a_decode_frame_strided`, the 10564-byte payload was assumed to consist of 80 columns of 132 bytes with 36 padding bytes per column, mapping 4 consecutive pixels vertically into columns.
  - This destroyed the true horizontal raster scanlines: consecutive horizontal sensor pixels were written vertically down columns, shredding ridge continuity and producing negative adjacent correlation (`adj_corr = -0.212`) and 0 minutiae.

### Offline Empirical Proof (`experiments/test_bozorth_verify.c` & `experiments/test_roundtrip.c`)
- Unpacking the first 7680 bytes ($5120 \text{ pixels} \times 1.5$) linearly in row-major order ($W=80, H=64$):
  - **Bit-exact round-trip:** 0 diffs / 5120 pixels.
  - **Adjacent column correlation:** jumps from $-0.212$ to **$+0.860$**!
  - **Minutiae extraction (`mindtct`):** yields **22 minutiae** (well above the $\ge 10$ floor).
  - **Bozorth3 matching:** achieves **Self-Match Score = 110** and **Probe-Match Score = 89** (well above the match threshold of 12).
- The remaining 2884 bytes ($10564 - 7680$) in the payload are trailing sensor MCU metadata / padding rows and must simply be ignored.

## Experiment C: Linear Row-Major Unpack ($80 \times 64 \to 160 \times 128$)
1. Decode the first 7680 bytes linearly in row-major order: `out_row_major[r * 80 + c]`.
2. Compute min-max normalization over active pixels.
3. Upscale 2x to $160 \times 128$ via bilinear interpolation with `flags = FPI_IMAGE_COLORS_INVERTED` (omitting `FPI_IMAGE_PARTIAL`).
4. Set device class dimensions: `img_width = 160, img_height = 128, bz3_threshold = 12`.

## Acceptance Criteria (Deployed Driver, Hardware Only)

- [ ] Probe and gallery prints both contain $\ge 10$ detected minutiae logged in journal (predicted: 20–25).
- [ ] Adjacent column correlation logged $\ge 0.500$ (predicted: ~0.800).
- [ ] `fprintd-verify` achieves score $\ge 12$ against enrolled gallery (predicted: > 50).
- [ ] Successful `Verify result: verify-match (done)` on first touch.


