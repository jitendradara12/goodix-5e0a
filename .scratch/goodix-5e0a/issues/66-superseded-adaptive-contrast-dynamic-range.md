# 66 — Adaptive Contrast Dynamic Range & Ridge Boundary Preservation

**What to build:**
Eliminate severe dynamic range clipping in `process_raw_frame` where high-energy ridge residuals from -375 to +293 are currently flattened to solid 0 and 255 by the linear midpoint formula `CLAMP(128 + residual * 1.0f, 0, 255)`. Replace hard saturation with soft-knee scaling and pre-upscale ridge boundary sharpening:
1. **Dynamic Range Preservation**: In `libfprint-driver/goodix5e0a.c:process_raw_frame`, apply contrast normalization scaled by the empirical residual envelope or soft-knee curve rather than hard saturation, ensuring that ridge peaks and valleys retain continuous intensity gradients for `mindtct`.
2. **Pre-Upscale Ridge Sharpening**: Apply a lightweight 3x3 unsharp mask / Laplacian sharpening before 2x bilinear interpolation, counteracting the low-pass blurring effect of bilinear upscaling and delivering high-contrast edge gradients to NBIS.

**Blocked by:** Ticket 65 (closed, verified on hardware 2026-09-11 — 10 stages + 4-frame burst live).

**Status:** superseded (successor: 67 — sharpen dose-response 1.0 -> 0.25 on dense live; see Run 3 falsify note)

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

---

## 4. Agent implementation (2026-09-11, code complete — awaiting hardware verify)

- Driver: `libfprint-driver/goodix5e0a.c:1504-1532` replaces `CLAMP(128 + residual*GAIN)` with sharpen-then-soft-knee: 3x3 unsharp on the residual field (`sharpened = r + 1.0*(r - blur)`, uniform stays uniform so the `active<64||range<8` and `residual_range<1` NULL gates above still hold) followed by `128 + 127*tanhf(sharp/127)` (derivative 1.0 at zero preserves ticket-17 gain; live envelope -375.83..+293.22 maps to ~2..253 with no hard saturation). No new `g_message` (budget holds at 23), non-empty LOC 1522/1525. Header `goodix5e0a.h:44-52` adds `SOFT_KNEE_SCALE (127.0f)` + `SHARPEN_AMOUNT (1.0f)` with rationale; `CONTRAST_GAIN (1.0f)` kept as the linear-region gain pin.
- Tests: `test_m1_c1` contrast test updated to pin new defines + `tanhf`/`SHARPEN` strings; patch SHA rolled `746eca20…6343dd6` -> `980cd6ac6dffbac5eaefe3d9f92959a57424d763f62d0f203b6300580ee6a142`.
- Patch: new-file sections for `goodix5e0a.c` (1702->1719 lines, index `e9410be`) and `goodix5e0a.h` (160->170 lines, index `1447393`) regenerated from repo sources; `test_f25_patch_sync` 9/9 OK; repo patch byte-identical to `/home/sastauser/NixOS-Hyprland/modules/goodix/`; build tree `diff -q` in sync; ninja drivers-only build clean (`[3/3] Linking target libfprint-2.so.2.0.0`, 0 warnings/errors).
- Suite: `bash tests/run_all_tests.sh` -> 459 passed / 0 failed / 1 skipped (env-gated native C harness absent).
- Offline benchmark (driver-faithful NBIS harness vs `experiments/fingerprint.pgm`, 64x80 -> 128x160, mindtct + Bozorth3 perturbed-probe): baseline `128+res` clip 4.39% (0:0 255:225), minutiae 0/0, bz 0; proposed tanh+sharpen-1.0 clip 0.57% (0:29 255:~0 avg), minutiae 18 pert 15, bz pert 36 self 95. Synthetic live-envelope stress (affine stretch to [-375.83,+293.22]): baseline clip 88.63% (0:4477 255:61), proposed 1.72% — confirms the ticket's >40% range-destruction claim at pixel level and the <10% acceptance (both real and stressed pass). Uniform-128 sharpened stays 128, upscaled minutiae 0 (empty-air safe; driver returns NULL even earlier on uniform).
- Independent reviews (user-gated): two general subagents PASS, no load-bearing issues (`ses_f6e666223ffeW9hr19AX4OsmDZ` driver/invariants incl. 0x32/0x34/park/CANCELLED/bz3=14 untouched, LOC 1522, `-lm` link verified; `ses_f6e666220ffeqIZBBV81QXuFfV` tests/patch incl. SHA parity, f25 9/9, tree sync, 459 green). One comment-precision nit fixed (tail maps to ~2..253, not 252; verified `128+127*tanh(293/127)=252.51->253`); one scope flag noted (ticket-65 hunks share the working tree, but 65 is closed/verified so 66 is the single new variable on top of the deployed 65 driver).

### Hardware verify protocol (user only — do NOT run as agent)
1. Deploy: `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`. CORRECTION 23:51 UTC: image-processing change invalidates old galleries — always `fprintd-delete` + fresh 10-stage pressure-ladder re-enroll under the 66 driver (the "no re-enroll" line above was wrong).
2. Phase 1, hands off 60s ("hands off" + timestamp): expect silence (blocking 0x32 wait, no timeouts).
3. Phase 2, press-hold steady 60s ("holding" + timestamp): `fprintd-verify` natural pad taps should `verify-match` with `gallery_len=10`, probe minutiae >= 20, scores >= prior 14-15 baseline (confirm = higher scores, e.g. 16-22, on same fingers); then held-wrong-finger test must show exactly one `verify-no-match` with attempts withheld (~18s FDT-UP re-issue loop) until lift (FAR guard).
4. Conclude only: confirmed / falsified / inconclusive-because-[flaw] + the single next experiment. Smoke per AGENTS.md rule 7 scoped to the serving instance match-claim window.

## 5. Hardware runs

### Run 1 — 23:39-23:46 UTC (stale gallery, protocol-incomplete)
- `23:39:50 probe_nrows=16 gallery_len=10`, max `4/14` -> `verify-no-match`; `23:46:42 probe_nrows=12`, max `5/14` -> `verify-no-match`. Both probes <20 (falsify gate needs >=20). Gallery was the old linear enroll; no `fprintd-delete` done. Verdict: inconclusive-because-[stale-gallery + no-timestamps].

### Run 2 — 23:50-23:51 UTC (fresh 66 gallery, single tap)
- Fresh `fprintd-delete` + ladder re-enroll under 66: `enroll-completed` with 3x `enroll-swipe-too-short` rejections (gate working); tail `best frame 3/4: minutiae=15`, `best frame 2/4: minutiae=18` (23:50:33-34, pid 327928). Residuals `-416..+323`, range ~677-713 — envelope confirmed.
- Verify 23:51:48 pid 328619: 4 full frames (`declen=10564`, `active=5120`), `best frame 3/4: minutiae=14`, `probe_nrows=14 gallery_len=10 (12-19)`, scores 0-5 -> `verify-no-match`. No `timed out`/`Invalid ACK`/`failed to` in window.
- 75s silence 23:50:33->23:51:48 with no frames = blocking 0x32 hold OK, but no journal "holding" marker (lazy command dropped `logger`) and only one tap at unknown pressure. Probe 14 <20 so falsify gate still not met, but direction is concerning: 65-linear gave probes 16-22 with matches; two 66 taps give 12,14 with background scores.
- Verdict: inconclusive-because-[single-tap-probe-14-below-gate + missing-holding-marker]. Next: 3 pressure-varied taps (firm/medium/light) with timestamps to separate touch variation from driver regression before any falsify call.

### Run 3 — 23:53 UTC (pressure ladder, fresh 66 gallery — FALSIFIES)
- `firm 18:23:12 UTC` -> 23:53:16 pid 329567 `best frame 4/4: minutiae=13`, `probe_nrows=13`, max `6/14` (gallery[6]) -> `verify-no-match`. Residuals `-391..+270`, range ~644-662.
- `medium 18:23:16 UTC` -> 23:53:17 `best frame 1/4: minutiae=7` (runt), `probe_nrows=7`, all `0/14` -> `verify-no-match`. Residuals `-389..+304`.
- `light 18:23:17 UTC` -> 23:53:18-19 `best frame 1/4: minutiae=12`, `probe_nrows=12`, max `4/14` -> `verify-no-match`. Residuals `-431..+286`, range ~707-713.
- Tally post-enroll under 66 with fresh tanh gallery: 5/5 no-match (probes 14,13,7,12 + earlier 12; enroll probes 15,18). Same finger matched 2/3 under 65-linear (probes 22/16/19, scores 15/11/14). Pressure variation ruled out (firm/medium/light all fail, one runt).
- Verdict: **falsified**. Sharpen-1.0-before-tanh preserves range (clip <10% holds) but depresses dense-live minutiae yield (7-14 vs 16-22) — the sparse-`fingerprint.pgm` offline proxy (0->18) misled; dense live (active=5120, h_corr ~0.95) fragments under 1.0 high-freq boost. No `timed out`/`Invalid ACK`/`failed to` in window; empty-air gates untouched.
- Single next experiment: successor ticket 67 — sharpen dose-response (1.0 -> 0.25, same tanh) with dense-live minutiae >= 20 and score >= 14 as the gate; if 0.25 still yields <20, fall back to 65-linear and close the contrast line.
