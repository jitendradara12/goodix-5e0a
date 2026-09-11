# 67 — Sharpen Dose-Response and Live Frame Preprocessing Calibration

**What to build:**
Empirically calibrate the pre-upscale residual sharpening dose (`GOODIX_5E0A_SHARPEN_AMOUNT` from 1.0 down to 0.25) and evaluate soft-knee contrast compression on genuine dense-contact capacitive frames. Establish an offline benchmark against real sensor captures to measure minutiae yield and Bozorth scores across candidate doses before hardware deployment. If reduced sharpening restores high minutiae yield ($\ge 20$) and achieves first-tap verification ($\ge 14/14$), lock in the optimal dose. If any sharpening or soft-knee compression degrades minutiae compared to the Ticket 65 linear baseline, permanently close the image filtering line and lock the proven linear contrast formula.

**Blocked by:** 66 (superseded — hardware-falsified on 2026-09-11 23:53 UTC).

**Status:** ready-for-agent

---

## 1. Hardware Evidence & Diagnostic Findings (Ticket 66 Run 3)

In Ticket 66, an unsharp mask with amount $1.0\times$ was applied to the residual field followed by $\tanh$ soft-knee scaling:
$$\text{sharpened} = \text{residual} + 1.0 \times (\text{residual} - \text{mean}_{3\times 3}(\text{residual}))$$
$$\text{pixel} = 128 + 127 \times \tanh(\text{sharpened} / 127)$$

The offline test against `experiments/fingerprint.pgm` passed (minutiae increased from 0 to 18 on that fixture). However, deployment to hardware resulted in complete verification failure across all test runs:

```text
# Run 3 Hardware Evidence (Fresh 66 Gallery, Pressure Ladder, pid 329567):
firm touch   18:23:12 UTC -> best frame 4/4: minutiae=13, probe_nrows=13, max score 6/14 (gallery[6]) -> verify-no-match
medium touch 18:23:16 UTC -> best frame 1/4: minutiae=7 (runt), probe_nrows=7, all scores 0/14 -> verify-no-match
light touch  18:23:17 UTC -> best frame 1/4: minutiae=12, probe_nrows=12, max score 4/14 -> verify-no-match
Earlier tap  23:51:48 UTC -> best frame 3/4: minutiae=14, probe_nrows=14, max score 5/14 -> verify-no-match
Earlier tap  23:46:42 UTC -> best frame 2/4: minutiae=12, probe_nrows=12, max score 4/14 -> verify-no-match
```

### Contrast with Ticket 65 Linear Baseline:
Under the exact same finger and sensor conditions, Ticket 65's linear contrast (`CLAMP(128 + residual * 1.0f, 0, 255)`):
- Generated probes with **16 to 22 minutiae**.
- Achieved **instant first-tap match** on Attempt 1 with Bozorth score **15/14** against `gallery[1]` and score **14/14** on natural taps.
- Maintained $0$ timeouts, $0$ invalid ACKs, and clean PAM integration.

---

## 2. Mathematical & Algorithmic Root Cause Analysis

### 2.1 The Double High-Pass Penalty ($\nabla^4$ Hyper-Laplacian)
1. **Sensor Scale**: The Goodix 5e0a raster is only $64 \times 80$ pixels. At human ridge frequency ($\sim 0.5\text{ mm}$ period), a ridge is only **2 to 3 pixels wide**.
2. **First High-Pass**: In Ticket 17, the driver subtracts the $3\times 3$ moving average from raw pixels:
   $$\text{residual} = P - M_{3\times 3}(P) \equiv (I - M) P$$
   This is already a discrete spatial Laplacian ($\nabla^2$) high-pass filter that removes DC capacitive baseline drift.
3. **Second High-Pass in Ticket 66**:
   $$\text{sharpened} = \text{residual} + 1.0 \times (I - M)(\text{residual}) = (I - M) P + (I - M)^2 P$$
   Applying an unsharp mask to an already high-passed signal computes a **4th-order spatial derivative ($\nabla^4$)** directly at the sensor Nyquist frequency.
4. **Impact**: Because the kernel matches ridge width, $\nabla^4$ exponentially magnifies pixel noise, causing intense edge ringing that slices continuous ridges into disconnected pixel islands.

### 2.2 Why NBIS `mindtct` Minutiae Yield Collapsed ($22 \to 7\text{--}14$)
* **DFT Orientation Scrambling**: `mindtct` calculates direction maps using 8x8 DFT blocks on the 2x upscaled raster ($4\times 4$ raw pixels). Noise ringing corrupts the dominant wave vectors.
* **Skeletonizer Fragmentation**: Morphological thinning of noisy ridges generates massive false branch points, loops, and micro-breaks.
* **Quality Pruning**: `mindtct`'s internal validation algorithm flags high-frequency curvature defects and removes them as unreliable noise, collapsing detected minutiae count.

### 2.3 Why Bozorth3 Matching Collapses Below Threshold 14
Bozorth3 compares pairwise minutiae graph edges with strict tolerances:
* Length stretch: $\le 10\%$ ($\text{TK} = 0.05$)
* Angle delta: $\le 11^\circ$ ($\text{TXS} = 121$)
* Match Threshold: 14 pairs (`bz3_threshold = 14`).

When probe minutiae drop to $N \le 13$ (e.g. 7 or 12), the maximum possible matching pairs is bounded by $N$. **It is mathematically impossible to reach threshold 14**. Scores of 0–6/14 are the inevitable graph-theoretic result.

### 2.4 The Fallacy of Dynamic Range "Clipping"
Ticket 66 assumed that clipping residuals below $-128$ to $0$ and above $+127$ to $255$ was degrading accuracy. 
In fingerprint biometrics, ridge/valley distinction is fundamentally binary (skin contact vs air gap). Clamping valley bottoms to 0 (deep black) and ridge crests to 255 (clean white) provides **optimal binarization contrast**. $\tanh$ soft-knee compression softened this transition into muddy mid-grays ($23 \dots 233$), reducing directional edge steepness.

### 2.5 Flaw in Previous Offline Fixtures
`experiments/fingerprint.pgm` is a legacy artifact containing zero-padded rows from old driver versions. Because it lacked dense continuous ridge structures, it produced 0 minutiae under linear contrast, misleading the developer into believing linear contrast was broken. Real hardware captures have `active=5120` and $h_{\text{corr}} \approx 0.95$.

---

## 3. The Controlled Dose-Response Plan

Rather than pushing speculative constants to hardware, Ticket 67 establishes an empirical dose-response study:

1. **Live Frame Extraction**:
   Extract a genuine 12-bit dense-contact live frame from system logs or saved capture buffers to serve as a reliable offline test vector (`experiments/live_dense_pad.pgm`).
2. **Offline Parameter Sweep**:
   Implement an offline benchmark (`experiments/benchmark_sharpen_dose.c` / Python script) testing:
   - Doses: $A \in \{0.00, 0.10, 0.20, 0.25, 0.50, 1.00\}$
   - Models: Linear `CLAMP(128 + res * 1.0f)` vs $\tanh(127 \times \text{soft})$
   - Metrics:
     1. Total detected minutiae ($M$).
     2. High-reliability minutiae ($M_{\ge 0.2}$).
     3. Bozorth self-match score ($B_{\text{self}}$).
     4. Bozorth perturbed-probe score ($B_{\text{pert}}$).
     5. Ridge-valley transition gradient steepness.
3. **Go / No-Go Decision Gate**:
   - **Proceed to Hardware Build**: ONLY IF a specific dose (e.g. $A = 0.25$ or $0.15$) demonstrably increases $M_{\ge 0.2}$ by $\ge 15\%$ and increases $B_{\text{pert}}$ over the Ticket 65 linear baseline without introducing spurious minutiae.
   - **Close Contrast Line**: If the linear baseline outperforms or equals all sharpening/tanh configurations on dense live frames, Ticket 67 immediately declares the contrast line closed and preserves Ticket 65 linear permanently.

---

## 4. Invariants & Guardrails (AGENTS.md)

- `0x32 FDT_DOWN` timeout remains 0 (blocking capacitive interrupt, never a timer).
- `0x34 FDT_UP` remains finite (2000ms guard / 5000ms normal) with re-issue on timeout.
- TLS park lifecycle and cross-claim TTL (guard 2s, park 30s, warm 60s) preserved on idle return.
- `CANCELLED` errors never re-issue.
- `bz3_threshold = 14` locked; no loosening of matcher criteria.
- Empty-air gates (`active < 64 || range < 8`, `residual_range < 1`) run before normalization; uniform air frames must strictly return NULL with 0 minutiae.
- Single variable per build: only `GOODIX_5E0A_SHARPEN_AMOUNT` (or decision to keep linear).

---

## 5. Acceptance Criteria

### Phase A: Offline Empirical Validation
- [ ] Offline benchmark script created and executed against dense-contact frame data.
- [ ] Minutiae yield and Bozorth score curves documented across doses $0.0 \le A \le 1.0$.
- [ ] Clear empirical proof that candidate configuration matches or exceeds linear baseline ($M \ge 20$).

### Phase B: Driver Implementation (Conditional on Phase A)
- [ ] `libfprint-driver/goodix5e0a.h`: `GOODIX_5E0A_SHARPEN_AMOUNT` set to calibrated value with full rationale comment, or linear baseline explicitly locked.
- [ ] Full test runner passes 100%: `bash tests/run_all_tests.sh` (459/459 green).
- [ ] Ninja driver build clean (0 warnings, 0 errors).
- [ ] Unified patch `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` regenerated and byte-synced to `/home/sastauser/NixOS-Hyprland/modules/goodix/`.

### Phase C: Hardware Verification Protocol (User-Only)
- [ ] **Phase 1 (Hands-off 60s)**: Sensor untouched for 60s; journal reports clean silence without 0x32 timeout cycles.
- [ ] **Phase 2 (Hold & Verify)**: 
  - Fresh enrollment with 10-stage pressure ladder.
  - Natural pad verification taps produce `probe_nrows >= 20` and Bozorth score $\ge 14/14$ (instant unlock).
  - Held-wrong-finger test produces exactly one `verify-no-match` with attempts withheld until lift (~18s FDT UP re-issue loop).
- [ ] **Rollback Criteria**: If hardware verification yields `probe_nrows < 20` or fails to match on Attempt 1, immediately revert to Ticket 65 linear baseline and mark Ticket 67 closed (verdict: falsified-dose-response).

---

## 6. Predicted Journal Signatures

### Confirm Branch (Dose 0.25 or Calibrated Optimum Succeeds):
```text
5e0a best frame 4/4: minutiae=22 score-proxy=22 (submitting)
5e0a bz3 match start: probe_nrows=22 gallery_len=10 (probe_len=168)
5e0a bz3 match: gallery[1]_nrows=24 score=16/14 (probe_nrows=22)
-> verify-match (done)
```

### Falsify Branch (Noise Still Dominates / Linear Baseline Superior):
```text
5e0a best frame 4/4: minutiae=14 score-proxy=14 (submitting)
5e0a bz3 match start: probe_nrows=14 gallery_len=10
5e0a bz3 match: gallery[0]_nrows=25 score=6/14
-> verify-no-match (done)
Action: Close contrast line permanently; restore Ticket 65 linear baseline byte-for-byte.
```

---

## 7. Verification Commands (For User)

```bash
# 1. Deploy updated driver
cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd

# 2. Reset gallery and enroll under test driver
fprintd-delete $USER
fprintd-enroll

# 3. Phase 1: Hands-off 60s check
logger "hands off start" && sleep 60 && logger "hands off end"

# 4. Phase 2: Natural tap verification
fprintd-verify

# 5. Inspect journal match metrics
journalctl -u fprintd -n 40 --no-pager | grep -E "5e0a frame|5e0a bz3 match|best frame|verify-"
```
