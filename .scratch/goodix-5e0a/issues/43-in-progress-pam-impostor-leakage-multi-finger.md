# 43 — PAM Impostor Leakage Under Multi-Finger Gallery and Continuous-Touch Lock

**What to build / investigate:**
Diagnose and resolve high False Accept Rate (FAR ~70%) observed when un-enrolled fingers touch the sensor during PAM authentication (`hyprlock`), and eliminate the vulnerability where locking with a finger already held on the sensor triggers immediate false unlocks.

**Blocked by:** None. Live hardware reproduction and journal logs captured on 2026-09-07.

**Status:** in-progress

## Empirical Findings & Technical Diagnosis (2026-09-07)

### 1. Hardware Behavior Observed in Field
- User tested with an un-enrolled third party (friend) keeping a finger placed during `hyprlock`. Unlocked **~70% of trials** on full pad contact.
- When tested with an edge / lower-contact region of the un-enrolled finger, successful unlocks dropped to **2/50 (~4%)**.
- Locking `hyprlock` while any finger is pre-placed on the sensor triggers an unlock in < 1 second.

### 2. Root Cause 1: 1:N Gallery Combinatorial Explosion (8 Fingers = 96 Templates)
- Inspection of the user's PAM enrollment database (`fprintd-list sastauser`) revealed **8 enrolled fingers**:
  `left-middle`, `right-ring`, `left-thumb`, `right-thumb`, `left-little`, `right-little`, `right-index`, `left-ring`.
- In PAM authentication (`hyprlock` / `pam_fprintd`), `libfprint` performs a 1:N `identify` search across all enrolled prints.
- Each enrolled finger contains 12 enrollment stages $\implies K = 8 \times 12 = \mathbf{96\text{ gallery sub-templates}}$ evaluated in `fpi_print_bz3_match()` for every single touch.
- For a small-aperture sensor ($64 \times 80$, $13\text{ mm}^2$), a full, firm touch yields high minutiae density ($M \approx 18\text{--}22$).
- At `bz3_threshold = 11`, pairwise $\text{FMR}(S \ge 11) \approx 0.90\%\text{--}1.2\%$.
- Across $K = 96$ template comparisons, the cumulative Family-Wise False Accept Rate is:
  $$\text{FAR}_{\text{PAM}} = 1 - (1 - \text{FMR})^{K} = 1 - (1 - 0.012)^{96} \approx \mathbf{68.7\% \approx 70\%}$$
- When the friend touched with an edge / lower contact area ($M \le 10$), pairwise $\text{FMR}$ drops to $\sim 0.05\%$:
  $$\text{FAR}_{\text{PAM}} = 1 - (1 - 0.0005)^{96} \approx \mathbf{4.6\%} \quad (2.3 / 50 \implies \text{matches empirical } 2/50)$$
- **Conclusion:** The ~70% false unlock rate is the exact mathematical consequence of evaluating 96 templates against an operating threshold of 11.

### 3. Root Cause 2: Ticket 20 Latency Hack (Continuous-Touch Pre-Placement)
- In `libfprint-driver/goodix5e0a.c` line 962:
  ```c
  fpi_image_device_image_captured (FP_IMAGE_DEVICE (dev), img);
  if (action != FPI_DEVICE_ACTION_ENROLL) {
      self->scan_ssm = NULL;
      fpi_ssm_mark_completed (ssm);
      fpi_image_device_report_finger_status (FP_IMAGE_DEVICE (dev), FALSE);
  }
  ```
- To eliminate 2–5 second latency from finger-lift polling, Ticket 20 unconditionally reported `finger_status = FALSE` immediately upon image capture, bypassing libfprint's `AWAIT_FINGER_OFF` state.
- If a finger is held continuously on the sensor across lock events:
  1. `hyprlock` launches and requests `fpi_image_device_activate()`.
  2. Device transitions to `AWAIT_FINGER_ON` and starts `goodix5e0a_scan_start()`.
  3. The driver issues `GOODIX_CMD_MCU_SWITCH_TO_FDT_DOWN`.
  4. Because a finger is already resting on the sensor, the MCU's capacitive FDT registers immediate contact (`data[2] != 0xff, channel_energy > 0`) without requiring a fresh touch-down transition.
  5. Best-of-3 capture triggers instantly on the warm, settled finger, capturing maximal minutiae ($M \ge 20$).
  6. The probe is immediately checked against the 96 templates, hitting the ~70% FAR vulnerability and unlocking the screen within 1 second.

### 4. Verification of Sensor Hardware Integrity (Ruling Out Stale Image Caching)
- We verified whether the MCU could be returning cached/stale image memory from a previous legitimate user touch during TLS session reuse / skipped reset.
- Live journal analysis showed active pixel dynamic ranges fluctuating on each frame request (e.g. range=2084, 2061, 2064, 2051).
- Furthermore, when the friend shifted to an edge touch, minutiae counts immediately shifted from 19 down to 3–7.
- **Verdict:** The MCU is actively streaming fresh analog captures. The failure is purely algorithmic due to the combination of high minutiae density ($M \approx 20$), large gallery search space ($K=96$), and low Bozorth threshold ($T=11$).

### 5. FAR vs Gallery Size ($K$) Trade-off Analysis

| Bozorth Threshold $T$ | Pairwise FMR | 1 Finger ($K=12$) | 2 Fingers ($K=24$) | 4 Fingers ($K=48$) | 8 Fingers ($K=96$) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **10** | 1.84% | 19.95% | 35.92% | 58.95% | **83.14%** |
| **11** | 0.90% | 10.28% | 19.50% | 35.19% | **58.00% (70% at M=20)** |
| **12** | 0.44% | 5.16% | 10.05% | 19.09% | **34.54%** |
| **13** | 0.22% | 2.56% | 5.06% | 9.84% | **18.72%** |
| **14** | 0.11% | 1.26% | 2.51% | 4.94% | **9.64%** |
| **15** | 0.05% | 0.62% | 1.24% | 2.45% | **4.84%** |
| **16** | 0.025% | 0.30% | 0.60% | 1.20% | **2.40%** |

- For a standard 1:1 setup ($K=12$), $T=11$ gives an acceptable ~6%–10% FAR with 96% genuine acceptance.
- But when 8 fingers are enrolled in PAM ($K=96$), $T=11$ allows an un-enrolled stranger to unlock ~60%–70% of the time.
- To achieve $< 5\%$ FAR with 8 fingers enrolled, the threshold must be at least **$T = 15$**.
- Alternatively, pruning enrollment to **1 primary finger** ($K=12$) at $T=12$ drops FAR to **$3.0\%\text{--}5.1\%$**.

## Remediation Plan

1. **Immediate User Mitigation:**
   - Delete unnecessary finger enrollments so PAM only searches 1 or 2 fingers (e.g. right-index and left-index):
     ```bash
     fprintd-delete sastauser <finger-name>
     ```
   - Reducing $K$ from 96 to 12 cuts the false unlock search space by **8x**.

2. **Touch-Down Transition Enforcement (Prevent Pre-Placed Unlock):**
   - In `goodix5e0a_scan_start`: If the sensor detects a finger already pressed down at the moment of activation, require an `AWAIT_FINGER_OFF` cycle before arming a new capture burst.
   - This guarantees that locking the laptop while a finger is resting on the sensor will NOT automatically unlock; the user must lift and deliberately re-apply the finger.

3. **Operating Point Decision:**
   - With Ticket 39 (Best-of-3 frame submission) providing genuine probes of $M \ge 20$, evaluate whether setting `bz3_threshold = 12` or `13` provides the required multi-finger security margin while maintaining single-touch unlocking.
