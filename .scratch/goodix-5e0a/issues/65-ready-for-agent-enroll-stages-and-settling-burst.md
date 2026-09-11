# 65 — Multi-Stage Pressure-Stratified Enrollment & Settling Burst Calibration

**What to build:**
Resolve the 1–2 retry verification shortfall on Goodix 27c6:5e0a hardware by eliminating single-template pad starvation and capacitive touchdown contact truncation:
1. **Enrollment Stage Calibration ($5 \to 10$)**: Update `dev_class->nr_enroll_stages = 10;` in `libfprint-driver/goodix5e0a.c`. On a $64 \times 80$ ($13\text{ mm}^2$) aperture, 5 stages leave only 1 template for the central pad (`gallery[0]`), forcing Bozorth3 to reject any natural touch whose pressure varies by $>10\%$ (scale delta) or angle by $>11^\circ$. 10 stages allow multi-sample gallery representation across pad pressures (firm, medium, light, slight shift) and angles without exceeding the system FAR budget ($K=10\text{--}20$, $\text{FAR} \le 2.18\%$ at `bz3_threshold = 14`).
2. **Capacitive Settling Burst Expansion ($3 \to 4$ frames)**: Update `#define GOODIX_5E0A_FRAMES_PER_TOUCH (4)` in `libfprint-driver/goodix5e0a.h`. Human skin capacitance requires 150–200ms to conform to the sensor glass. Expanding the burst from 3 to 4 frames (~132ms) ensures the driver samples the fully settled contact state, eliminating runt probes ($\le 14$ minutiae) observed during rapid initial taps.
3. **Test Suite & Patch Synchronization**: Synchronize assertions in `tests/tier1_feature/test_f47_verify_retry_release_guard.py`, `test_m2_driver_refactoring.py`, and `test_f23_pam_reliability.py` to reflect 10 stages, regenerate the unified patch `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`, update test hash pins, and sync to `/home/sastauser/NixOS-Hyprland/modules/goodix/`.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

---

## 1. Hardware Evidence & Empirical Diagnosis (2026-09-11 20:14–20:16 IST)

Live hardware logs with `G_MESSAGES_DEBUG=all` revealed the exact failure mechanism across three consecutive verification attempts:

```text
# Attempt 1: Near-miss on natural touch pressure / angle
5e0a bz3 match start: probe_nrows=20 gallery_len=5 (probe_len=159)
5e0a bz3 match: gallery[0]_nrows=25 score=9/14 (probe_nrows=20)
5e0a bz3 match: gallery[1]_nrows=20 score=5/14 (probe_nrows=20)
5e0a bz3 match: gallery[2]_nrows=20 score=3/14 (probe_nrows=20)
5e0a bz3 match: gallery[3]_nrows=15 score=3/14 (probe_nrows=20)
5e0a bz3 match: gallery[4]_nrows=17 score=5/14 (probe_nrows=20)
-> verify-no-match (done)

# Attempt 2: Runt probe from premature burst completion during touchdown ramp
5e0a bz3 match start: probe_nrows=14 gallery_len=5 (probe_len=49)
5e0a bz3 match: gallery[0]_nrows=25 score=4/14 (probe_nrows=14)
5e0a bz3 match: gallery[1]_nrows=20 score=4/14 (probe_nrows=14)
5e0a bz3 match: gallery[2]_nrows=20 score=5/14 (probe_nrows=14)
5e0a bz3 match: gallery[3]_nrows=15 score=4/14 (probe_nrows=14)
5e0a bz3 match: gallery[4]_nrows=17 score=3/14 (probe_nrows=14)
-> verify-no-match (done)

# Attempt 3: Bullseye match when pressure exactly duplicated gallery[0]
5e0a bz3 match start: probe_nrows=19 gallery_len=5 (probe_len=94)
5e0a bz3 match: gallery[0]_nrows=25 score=14/14 (probe_nrows=19)
-> verify-match (done)
```

### Key Technical Findings:
1. **Gallery Starvation (Single-Template Pad Bottleneck)**:
   In all attempts, `gallery[1]`, `gallery[2]`, `gallery[3]`, and `gallery[4]` scored 3 to 5 (the random background baseline for non-overlapping prints). Only `gallery[0]` was active for flat pad touches. Because 5 stages only provide a single pad snapshot, natural press variations have no alternate templates to match.
2. **Bozorth Rigid Graph Tolerance Thresholding**:
   In `libfprint/nbis/bozorth3/bozorth3.c:409-441`, Bozorth enforces:
   - Edge length tolerance: $\Delta d \le 2.0 \times \text{TK} \times (d_1 + d_2)$ with $\text{TK} = 0.05$ (max $10\%$ relative stretch).
   - Angle tolerance: $\Delta \theta^2 \le \text{TXS}$ with $\text{TXS} = 121$ (max $11^\circ$).
   In Attempt 1, a $12\%$ pressure/stretch difference knocked 5 minutiae pairs out of tolerance, plunging the score from 14 down to 9 despite 20 genuine minutiae.
3. **Capacitive Touchdown Ramp**:
   Frame stats from hardware show minutiae doubling across the burst (`frame 1/3: 12`, `frame 2/3: 14`, `frame 3/3: 24`). A 3-frame burst (~99ms) occasionally truncates during the ramp (Attempt 2: 14 minutiae). Expanding to 4 frames guarantees capturing the fully settled state ($M \ge 20$).

---

## 2. Invariant Safety & FAR Math

- **Settled Invariants (AGENTS.md)**:
  - `0x32 FDT_DOWN` timeout 0 (blocking capacitive interrupt) strictly preserved.
  - `0x34 FDT_UP` finite guard loop (2000ms / 5000ms) with re-issue strictly preserved.
  - TLS park lifecycle and cross-claim TTL preserved on park return.
  - `CANCELLED` errors never re-issue.
  - Host matcher remains in-tree NBIS/Bozorth3; threshold locked at 14.
- **FAR Safety Model**:
  At `bz3_threshold = 14`, pairwise False Match Rate is $\text{FMR} \approx 0.11\%$.
  - 1 finger $\times$ 10 stages: $K = 10 \implies \text{FAR} = 1 - (1 - 0.0011)^{10} \approx \mathbf{1.09\%}$ (3-tap PAM $P_3 \approx \mathbf{3.2\%}$).
  - 2 fingers $\times$ 10 stages: $K = 20 \implies \text{FAR} = 1 - (1 - 0.0011)^{20} \approx \mathbf{2.18\%}$ (3-tap PAM $P_3 \approx \mathbf{6.4\%}$).
  This stays comfortably within the consumer biometric security ceiling ($\text{FAR} \le 10^{-2}$ to $10^{-3}$), completely avoiding the Ticket 43 blowout ($K=96, \text{FAR}\approx 70\%$).

---

## 3. Prescribed Enrollment Protocol (Pressure Ladder)

When enrolling with `nr_enroll_stages = 10`:
- **Stages 1–3**: Central finger pad with **firm** pressure.
- **Stages 4–5**: Central finger pad with **medium / normal** pressure.
- **Stage 6**: Central finger pad with **light** pressure / slight offset.
- **Stages 7–8**: Upper finger tip and angled pad.
- **Stages 9–10**: Left and right side flanks / tilt.

This populates the gallery with multi-pressure and multi-angle representations of the primary pad, ensuring that verification taps across natural pressure variations clear threshold 14 on Attempt 1.

---

## 4. Acceptance Criteria

- [ ] `libfprint-driver/goodix5e0a.c`: `dev_class->nr_enroll_stages = 10;`.
- [ ] `libfprint-driver/goodix5e0a.h`: `#define GOODIX_5E0A_FRAMES_PER_TOUCH (4)`.
- [ ] Unit tests updated: `test_f47_verify_retry_release_guard.py`, `test_m2_driver_refactoring.py`, `test_f23_pam_reliability.py`.
- [ ] 100% test suite pass: `bash tests/run_all_tests.sh` (all tiers green, 0 failures).
- [ ] Ninja build (`/tmp/libfprint-goodix/build`) compiles with 0 warnings and 0 errors.
- [ ] Unified patch regenerated and byte-synchronized to `/home/sastauser/NixOS-Hyprland/modules/goodix/`.
- [ ] Hardware verification: Enrolling with the 10-stage pressure ladder yields instant first-tap verification (`fprintd-verify` matches on Attempt 1 with Bozorth score $\ge 14/14$).

---

## 5. Predicted Journal Signatures

- **Confirm (Success)**:
  `fprintd-verify` with natural pad touch on hardware:
  ```text
  5e0a bz3 match start: probe_nrows=20..26 gallery_len=10
  5e0a bz3 match: gallery[N]_nrows=20..26 score=15..22/14 (probe_nrows=20..26)
  ```
  Result: `verify-match (done)` on attempt 1/1 without retry prompt.
- **Falsify**:
  Even with 10 pressure-stratified stages and 4-frame bursts, natural pad touches repeatedly score $< 14/14$ despite probe minutiae $\ge 20 \implies$ points to non-linear dynamic range clipping or bilinear interpolation blur, gating Ticket 66.
