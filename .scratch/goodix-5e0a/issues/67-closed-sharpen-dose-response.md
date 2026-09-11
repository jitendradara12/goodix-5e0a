# 67 — Sharpen Dose-Response and Live Frame Preprocessing Calibration

**What to build:**
Empirically calibrate the pre-upscale residual sharpening dose (`GOODIX_5E0A_SHARPEN_AMOUNT` from 1.0 down to 0.25) and evaluate soft-knee contrast compression on genuine dense-contact capacitive frames. Establish an offline benchmark against real sensor captures to measure minutiae yield and Bozorth scores across candidate doses before hardware deployment. If reduced sharpening restores high minutiae yield ($\ge 20$) and achieves first-tap verification ($\ge 14/14$), lock in the optimal dose. If any sharpening or soft-knee compression degrades minutiae compared to the Ticket 65 linear baseline, permanently close the image filtering line and lock the proven linear contrast formula.

**Blocked by:** 66 (superseded — hardware-falsified on 2026-09-11 23:53 UTC).

**Status:** closed (verdict: falsified-dose-response — no stable sharpen dose on synthetic dense evidence; ticket-65 linear locked with reopen condition, see section 8)

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
- [x] Offline benchmark script created and executed against dense-contact frame data.
- [x] Minutiae yield and Bozorth score curves documented across doses $0.0 \le A \le 1.0$.
- [x] Clear empirical proof that candidate configuration matches or exceeds linear baseline ($M \ge 20$).
  - Outcome: NO candidate passes the section-3 gate stably (see section 8). Linear baseline holds the line; contrast line goes dormant with reopen condition, not to hardware.

### Phase B: Driver Implementation (Conditional on Phase A)
- [ ] NOT APPLICABLE — Phase A gate failed (section 8). Zero driver change: tree is committed ticket-65 linear byte-for-byte (`grep -rn SHARPEN_AMOUNT\|SOFT_KNEE\|tanhf libfprint-driver/` empty; `git diff HEAD -- libfprint-driver/` empty; HEAD is `ba4c164 ticket 65`). No `GOODIX_5E0A_SHARPEN_AMOUNT` introduced, no test updates, no patch regen, no suite re-run (new files under `experiments/` only; suite pins `experiments/fingerprint.pgm`, untouched — `grep -rn live_dense_pad\|benchmark_sharpen tests/` empty).
- [ ] Full test runner passes 100%: `bash tests/run_all_tests.sh` (459/459 green). — NOT RE-RUN: no driver/test file changed at closure, so prior 459/459 stands uninvalidated and a fresh run would prove nothing about this ticket.
- [ ] Ninja driver build clean (0 warnings, 0 errors). — NOT RE-RUN, same reason.
- [ ] Unified patch `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` regenerated and byte-synced to `/home/sastauser/NixOS-Hyprland/modules/goodix/`. — SKIPPED: patch regen rule triggers on driver change (AGENTS.md); a no-op regen is churn.

### Phase C: Hardware Verification Protocol (User-Only)
- NOT APPLICABLE — no driver change, nothing to deploy. Phase C was conditional on a Phase A pass. The section-6 journal signatures below are retained for the record only; no hardware run is requested or required for this closure (`closed` needs no hardware run per AGENTS.md; only `verified` does).

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

---

## 8. Agent implementation (2026-09-12 — Phase A complete, gate FAILED, contrast line dormant)

### 8.1 Provenance (commands + outputs, repo root)

No genuine dense live capture exists in-repo (`/dev/shm/live_frame.raw` gone;
`fingerprint.pgm` is sparse striped rows, `windows_unpacked.pgm` a
partial-contact band). Built a calibrated synthetic dense proxy instead —
disclosed as proxy, not genuine (see 8.5 disqualifiers):

```bash
python3 experiments/gen_dense_live.py --seed 67 --out experiments/live_dense_pad.pgm
# seed=67 active=5120 min=554 max=2560 range=2006 nonzero=5120
# wrote experiments/live_dense_pad.pgm sha256=d9f411180017c91a131eee16b80fc1473e7cc54fb09c3e8bd7dd171c8ae8fc58
python3 experiments/gen_dense_live.py --seed 68 --out experiments/live_dense_pad_seed68.pgm
# seed=68 active=5120 min=527 max=2597 range=2070 nonzero=5120
# wrote experiments/live_dense_pad_seed68.pgm sha256=e7346cfa9761348c274d65d6444b194200eceffa6229cd12092b973c19004359
gcc -O2 -Wall -I/tmp/libfprint-goodix/libfprint/nbis/include \
  -I/tmp/libfprint-goodix/libfprint/nbis/libfprint-include -I/tmp/libfprint-goodix/libfprint \
  -I<nix-glib-dev>/glib-2.0 -I<nix-glib-dev> -I<nix-glib-lib>/include \
  experiments/benchmark_sharpen_dose.c /tmp/libfprint-goodix/build/libfprint/libnbis.a \
  <nix-glib-lib>/libglib-2.0.so -lm -o /tmp/opencode/benchmark_sharpen_dose  # BUILD-OK, 0 warnings
/tmp/opencode/benchmark_sharpen_dose experiments/live_dense_pad.pgm \
  experiments/live_dense_pad_seed68.pgm experiments/fingerprint.pgm experiments/clear-0.pgm
# deterministic: two runs md5-identical (082f7bf0deb61f57968f6bc5f9b52317)
```

(`*.pgm` is gitignored; both frames force-added for provenance like the
existing tracked `fingerprint.pgm`. The generator is deterministic — either
frame regenerates byte-identically from `gen_dense_live.py --seed`.)

### 8.2 Proxy calibration vs live journal windows

| stat | live window (tickets 17/35/18/66) | seed67 | seed68 |
|---|---|---|---|
| active | 5120 | 5120 | 5120 |
| min_v / max_v | 416..631 / 2500..2763 | 554 / 2560 | 527 / 2597 |
| raw range | 2056..2276 | 2006 | 2070 |
| h_corr | 0.944..0.958 | 0.950 | 0.948 |
| v_corr | 0.815..0.841 | 0.762 | 0.759 |
| h_lag4 | 0.563..0.695 | 0.693 | 0.693 |
| residual range | 677..713 | 727.4 | 703.8 |
| linear-baseline M | 16..22 (ticket 65) | 23 | 20 |

Fit note: ridge period 5 px (not 2.6) — at ~0.1 mm/px raw pitch a 0.5 mm
ridge period spans 5 px, and lag-1 correlations stay positive on both axes
only if cos(2*pi/lambda) > 0, i.e. lambda > 4 px. Honest deltas: v_corr
0.76 sits just below the live 0.815 floor, residual max (+359/+330) just
above the live +286..+323 ceiling. Proxy is adjacent to live, not inside it
on every axis — one of three disqualifiers in 8.5.

### 8.3 Dose-response tables (M = total minutiae, M>=.2 = reliability >= 0.20)

Seed67 dense (`live_dense_pad.pgm`, baseline M>=.2=22 Bpert=136):

```text
config            M  M>=.2  Bself   Bpert   clip%    grad
linear A=0.00    23     22    180     136  31.76%   72.59 <- t65 baseline
linear A=0.10    25     23    213     144  35.04%   74.16
linear A=0.20    27     24    254     167  37.81%   75.52
linear A=0.25    27     24    254     168  39.32%   76.14
linear A=0.50    23     21    169     122  45.74%   78.70
linear A=1.00    21     19    126     105  54.96%   82.27
tanh   A=0.00    24     22    194     159   0.00%   63.24
tanh   A=0.10    22     22    156     120   0.02%   65.27
tanh   A=0.20    23     22    175     136   0.08%   67.10
tanh   A=0.25    22     22    156     143   0.21%   67.95
tanh   A=0.50    23     21    162     115   1.19%   71.61
tanh   A=1.00    20     19    105     105   3.71%   76.87 <- t66 shipped
```

Seed68 dense (`live_dense_pad_seed68.pgm`, baseline M>=.2=16 Bpert=56):

```text
config            M  M>=.2  Bself   Bpert   clip%    grad
linear A=0.00    20     16    113      56  32.85%   72.70 <- t65 baseline
linear A=0.10    20     16    113      93  35.68%   74.29
linear A=0.20    19     15    102      74  38.96%   75.69
linear A=0.25    19     15    102      73  39.86%   76.32
linear A=0.50    23     19    137     109  46.52%   78.97
linear A=1.00    20     14    103      84  56.05%   82.62
tanh   A=0.00    19     15     95      58   0.00%   63.54
tanh   A=0.10    20     16    113      81   0.00%   65.60
tanh   A=0.20    20     16    113      81   0.04%   67.45
tanh   A=0.25    20     16    113      78   0.18%   68.31
tanh   A=0.50    21     17    124      71   1.04%   71.99
tanh   A=1.00    20     15    104      84   4.32%   77.28 <- t66 shipped
```

Anti-drift check (`fingerprint.pgm`): linear A=0.00 M=0 clip 4.39%;
tanh A=1.00 M=18 Bself=95 Bpert=36 clip 0.57% — exactly ticket 66's reported
18/95/36. This proves the harness shares the ticket-66 implementation with no
transcription drift; it does NOT validate sensor fidelity (same degenerate
fixture both times — the fixture ticket section 2.5 already discredits).
Air check (`clear-0.pgm`): AIR GATE, 0 minutiae, driver-faithful.

### 8.4 Gate evaluation (section 3: some dose raises M>=.2 by >=15% AND raises B_pert)

- Seed67 best M>=.2: 24 vs 22 = +9.1% — FAILS the 15% bar (B_pert +23.5% passes, conjunction fails).
- Seed68 linear A=0.50: 19 vs 16 = +18.75%, B_pert 109 vs 56 — literal pass on this seed alone.
- But the optimum dose flips across seeds (0.25 vs 0.50) and the SIGN of A>=0.5 flips with it (seed67: A=0.50 loses on both metrics; seed68: wins). Cross-seed baseline swing (B_pert 136->56, M>=.2 22->16) dwarfs the largest claimed gain (+3 minutiae < live 16..22 band width). Best-of-12-configs on n=1 frame each is seed noise + selection, not "a specific dose" that "demonstrably" wins. Gate: FAILED.

### 8.5 Why this closes the line instead of shipping A=0.25 (three disqualifiers)

1. The fixture cannot reproduce the one known hardware ground-truth point: ticket-66 hardware falsified tanh+sharpen A=1.0 (probes 7-14, scores 0-6/14), yet seed67 yields M=20 at that exact config. A fixture blind to the known harm mechanism cannot rank doses by benefit either.
2. B_pert is same-impression (1px shift + +-1 checker, applied post-upscale): it rewards edge crispness — precisely what sharpening does — while hardware cross-impression matching punished it 22->7..14. B_pert >> 14 throughout is expected same-impression behavior, NOT headroom over bz3_threshold=14. B_self is circular (identical sets, ~quadratic in M) and was excluded from the gate for that reason.
3. The gate's third conjunct ("without introducing spurious minutiae") is unmeasurable here: the generator's ground-truth minutia count is unknown (14 explicit endings + uncounted phase-distortion births vs extracted M=23), so no M-gain can be separated from section-2.2 fragmentation inflation.

Directionally the data still support the ticket's Nabla-4 analysis: gradient steepness rises monotonically with dose in both models (seed67 linear 72.6->82.3, tanh 63.2->76.9), and A>=0.5 degrades or flattens on seed67. But directional support is not a shippable dose.

### 8.6 Verdict and scope

- NO-GO to hardware. Ticket-65 linear (`CLAMP(128 + residual * 1.0f)`) stays locked; zero driver change at closure.
- The contrast line goes DORMANT, not permanently proven-dead: this study falsifies stable dose-response on synthetic dense evidence only. Scoped ban: pre-upscale unsharp-on-residual (any A>0) + tanh soft-knee, for the current envelope (residuals -375..+293, active=5120, h_corr~0.95).
- Reopen condition (all required, no re-litigation without them): a genuine dense 12-bit live capture with archived provenance; the gate re-run across >=2 frames with a STABLE winning dose; positional precision/recall against known ground truth for the spurious-minutiae conjunct.
- Phase B/C: not applicable (conditional on a Phase A pass). No deploy, no hardware run requested. Section-6 signatures retained for the record only.
- No code changes at closure; prior suite 459/0/1 and ninja-clean stand uninvalidated (no driver/test file touched).
- Independent reviews (user-gated): two general subagents — `ses_f6e3121defferc8woZ95ssz3bm` (harness fidelity: PASS line-by-line vs `process_raw_frame`/`count_minutiae`; Bozorth use sound for relative comparison; demanded scoped closure + seed68 provenance + frame-stats + M/M>=.2 labels — all applied) and `ses_f6e3121cdffezcdRJnkG7GjRzk` (process: closing without hardware run is rule-compliant; demanded filename/status atomicity + no overclaim of suite/build + narrowed verdict — all applied).
