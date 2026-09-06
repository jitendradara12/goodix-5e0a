# 41 — Operating-point tuning with FAR/FRR data (threshold + pressure ladder)

**What to build:** NOTHING in code until the diag-dump distributions exist.
This ticket owns the decision: threshold value + documented enrollment
pressure ladder, set from measured genuine and impostor score
distributions — never from a single passing run. When data lands, the
expected change is small and explicit (e.g. threshold 12 → 10/11 with
impostor ceiling evidence, and/or pressure-ladder enrollment docs). One
variable: the operating point.

**Blocked by:** E4 diag data (`diag-5e0a-dump` branch: stratified enroll +
6 varied-pressure genuines + 3 impostor attempts with PGM dumps and score
lines). No threshold discussion without both distributions. No exceptions —
ticket 35's 13/12 was a max-of-gallery event, not a distribution.

**Status:** ready-for-agent

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
