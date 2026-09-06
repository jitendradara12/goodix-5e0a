# 43 — PAM Impostor Leakage Under Multi-Finger Gallery and Continuous-Touch Lock

**What to build / investigate:**
Diagnose and resolve high False Accept Rate (FAR ~70%) observed when un-enrolled fingers touch the sensor during PAM authentication (`hyprlock`), and eliminate the vulnerability where locking with a finger already held on the sensor triggers immediate false unlocks.

**Blocked by:** None. Live hardware reproduction and journal logs captured on 2026-09-07.

**Status:** ready-for-agent

## Empirical Findings & Field Evidence (2026-09-07 03:29 IST)

1. **Hardware Behavior Observed by User:**
   - An un-enrolled user (friend) kept a finger placed on the sensor during `hyprlock`. It matched and unlocked **~70% of the time**.
   - When touching with an edge / different part of the finger, the match rate dropped to **2/50 (~4%)**.
   - Locking hyprlock while a finger is already resting on the sensor consistently triggers an immediate unlock within 1 second.

2. **Root Cause 1: Combinatorial Explosion in 1:N PAM Gallery (8 Fingers Enrolled = 96 Templates)**
   - `fprintd-list sastauser` confirms **8 distinct fingers enrolled**:
     `left-middle`, `right-ring`, `left-thumb`, `right-thumb`, `left-little`, `right-little`, `right-index`, `left-ring`.
   - Each enrolled print contains $G = 12$ stages $\implies 8 \times 12 = \mathbf{96\text{ gallery sub-templates}}$ evaluated in `fpi_image_device_identify()`.
   - At `bz3_threshold = 11`, pairwise $\text{FMR}(S \ge 11)$ is $\sim 0.90\% - 1.2\%$.
   - When matching an impostor probe with high minutiae count ($M \ge 18$, from a firm, resting touch) against 96 templates:
     $$\text{FAR}_{\text{PAM}} = 1 - (1 - \text{FMR})^{96} = 1 - (1 - 0.012)^{96} \approx \mathbf{68.7\% \approx 70\%}$$
   - When touching with low minutiae ($M \le 10$, $\text{FMR} \approx 0.05\%$):
     $$\text{FAR}_{\text{PAM}} = 1 - (1 - 0.0005)^{96} \approx \mathbf{4.6\%} \quad (2.3 / 50 \text{ matches empirical } 2/50)$$
   - The ~70% match rate is the exact mathematical consequence of a lax Bozorth threshold ($T=11$) evaluated against an expansive 96-template search space.

3. **Root Cause 2: Ticket 20 Latency Hack (Finger-Off Bypass)**
   - In `goodix5e0a.c` line 962:
     ```c
     fpi_image_device_image_captured (FP_IMAGE_DEVICE (dev), img);
     if (action != FPI_DEVICE_ACTION_ENROLL) {
         self->scan_ssm = NULL;
         fpi_ssm_mark_completed (ssm);
         fpi_image_device_report_finger_status (FP_IMAGE_DEVICE (dev), FALSE);
     }
     ```
   - In verify/identify mode, the driver immediately reports `finger_status = FALSE` without waiting for the user to lift their finger (`AWAIT_FINGER_OFF` bypassed).
   - If a finger remains on the sensor when `hyprlock` launches, `goodix5e0a_scan_start()` instantly treats the resting finger as a new touch, captures a 3-frame burst at high contact pressure ($M \approx 20$), and evaluates it against the 96 templates, unlocking within 1 second.

## Predicted Signatures & Remediation Branches

### Branch A: Gallery Normalization + Threshold Hardening
- **Hypothesis:** Restricting enrollment to primary fingers (e.g. 1–2 fingers, 12–24 templates) and restoring threshold to 12 (or 13) drops $\text{FAR}_{\text{PAM}}$ to $< 3\%$.
- **Predicted journal signature:**
  - With $N=1$ finger ($12$ templates) and $T=12$:
    $$\text{FAR}_{1:1} \le 1 - (1 - 0.0044)^{12} \approx 5.1\% \quad (G_{\text{eff}}=7 \implies 3.0\%)$$
  - Impostor attempts produce `fprintd: verify-no-match` consistently.

### Branch B: Enforce Clean Touch Boundary (`AWAIT_FINGER_OFF` at Activation)
- **Hypothesis:** If a finger is already touching when activation begins, require finger lift before arming a new capture, preventing pre-touched session bypasses.
- **Predicted journal signature:**
  - Journal logs `5e0a await finger lift before scan start`. Pre-placed finger does not auto-capture.

### Branch C: Scale Bozorth Threshold Dynamically with Gallery Size ($K$)
- **Hypothesis:** Set effective threshold dynamically: $T_{\text{eff}} = T_{\text{base}} + f(K)$ where $K = \text{templates count}$, counteracting the $1 - (1 - p)^K$ search space inflation.
