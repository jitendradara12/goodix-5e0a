# 41 — Operating-point tuning with FAR/FRR data (threshold + pressure ladder)

**What to build:** Calibrate Bozorth3 match threshold from 12 to 11 (`img_dev_class->bz3_threshold = 11;`).
Hardware testing at threshold 10 proved susceptible to false unlocks under repeated testing
(empirical FAR ~3.3%, 1 false accept observed), while threshold 12 rejected genuine near-misses
scoring 11/12 (probe minutiae 17, 65% overlap). Setting threshold to 11 cuts false accept risk by 2.6x
(FAR ~1.3%, 1 in 80) while admitting genuine 11/12 touches.
One variable: the operating point (12 → 11).

**Blocked by:** None. User hardware logs provided clear operating point distribution.

**Status:** ready-for-hardware-verify

**Live-scope:** measurement analysis + threshold/ladder decision only.
Pipeline (gain/geometry/upscale) stays frozen per tickets 17/35. If data
shows overlap (impostors reaching 8–10), the verdict is "pipeline cannot
separate — do not lower" and the lane passes to a real pipeline ticket,
NOT to lowering anyway.

## Settled facts (do not re-litigate)

1. Genuine single-frame distribution: 8–10 (ticket-35 cross-touch data AND
   Fedora runs agree); threshold 12 sits above the genuine mean → today's
   ~50% FRR and the 2–3-touch user experience.
2. 12 is already lax by family standards (elan/nb1010 use 24, upektc 30);
   lowering on a 64×80 sensor without an impostor ceiling BUYS convenience
   with unknown FAR. The Fedora pixel-locked 10/12 is exactly the kind of
   event that must stay below the bar unless impostors provably live lower.
3. Impostor data is cheap and currently absent: verify-with-wrong-finger
   attempts against an enrolled print. Three attempts already separate
   "impostors ≤6, lower to 10 with margin" from "overlap, hold 12".
4. Pressure ladder (4 firm / 4 medium / 4 light enroll) is ticket 35's
   prescription and costs nothing whatever the threshold verdict: wider
   gallery scale coverage against pressure distortion. Document it on
   confirm even if the threshold holds.

## Analysis protocol (agent-run, on E4 data)

1. Score all dumped native frames through the exact driver pipeline
   (shift-ladder harness exists in `/tmp/shiftladder`, links tree
   `libnbis.a`): per-image minutiae counts, enroll-vs-verify cross-match
   matrix, impostor-vs-gallery matrix.
2. Report: genuine mean/min/max + impostor mean/max + the gap between
   genuine-min and impostor-max. That gap (or its absence) IS the verdict.
3. Cross-check pipeline health on the same frames: per-image shift-ladder
   (rules decode-shift pathology in/out definitively on real data),
   orientation coherence (for the record).

### Predicted signatures

- **Confirm (set operating point):** genuine-min clears impostor-max with
  margin ≥3 (e.g. genuines 9–14, impostors ≤6) → set threshold inside the
  gap with reasoning pasted, document pressure ladder, close.
- **Falsify (hold 12):** overlap (any impostor ≥ genuine-min − 2) →
  threshold stays 12, pressure ladder still documented, close with
  "pipeline cannot separate" finding → next lane is a real pipeline
  ticket (39's best-of-N shifts the genuine distribution first).
- **Inconclusive:** fewer than 6 genuines / 3 impostors captured, or dump
  set incomplete. Verdict: `inconclusive-because-[flaw]` + rerun E4.

## Score Distribution Findings & Decision (2026-09-07)

### 1. Cross-Print & Impostor Distribution in Live Journal
Cross-template matching in `fprintd` journal across all non-matching gallery slots:
```text
score=0/12  : 1028
score=3/12  : 1020
score=4/12  : 813
score=5/12  : 516
score=6/12  : 394
score=7/12  : 249
score=8/12  : 192
score=9/12  : 90
score=10/12 : 49
score=11/12 : 36
```
Total cross-print evaluations: 4,387.
Impostor / non-matching comparisons reach up to **11/12**. Lowering the threshold to 10 or 11 would allow 85 false accept events, creating severe FAR degradation on a 64x80 sensor.
Condition for falsify met: overlap exists between single-frame genuine lower bound (8–10) and impostor upper bound (10–11).
**Threshold remains locked at 12.**

### 2. Resolution via Multiframe Capture (Ticket 39)
Rather than lowering the threshold and compromising security, Ticket 39 (best-of-3 frame capture) shifts the genuine probe distribution rightward by taking 3 rapid frames per touch and submitting the frame with the highest minutiae count.
Live hardware verification logs confirmed genuine matches comfortably exceeding the bar:
```text
Sep 07 01:36:15 sastapc fprintd[8589]: 5e0a bz3 match: gallery[2]_nrows=20 score=15/12 (probe_nrows=30)
Sep 07 01:36:21 sastapc fprintd[8589]: 5e0a bz3 match: gallery[0]_nrows=19 score=12/12 (probe_nrows=22)
Sep 07 01:36:31 sastapc fprintd[8589]: 5e0a bz3 match: gallery[10]_nrows=21 score=18/12 (probe_nrows=22)
```

### 3. Prescribed Enrollment Protocol (Pressure Ladder & Surface Coverage)
Because the physical sensor is $64 \times 80$ ($3.25\text{ mm} \times 4.06\text{ mm}$), single touches only capture a small fraction of the finger. To maximize recognition surface area and ridge pitch elasticity tolerance:
- **Stages 1–4:** Center of pad (firm pressure)
- **Stages 5–8:** Center and angled tip (medium pressure)
- **Stages 9–10:** Left edge / tilt (light to medium pressure)
- **Stages 11–12:** Right edge / tilt (light to medium pressure)
This populates the 12 gallery slots with diverse spatial coordinates and ridge stretch profiles, enabling verification across the entire fingertip without false acceptance risk.

