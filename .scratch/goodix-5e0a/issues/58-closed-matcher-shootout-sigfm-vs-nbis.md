# 58 — Matcher shootout: SIGFM vs NBIS/Bozorth on 5e0a images

**What to do:**
A/B the /tmp/libfprint SIGFM matcher (`libfprint/sigfm/`, SIFT-based,
`FPI_DEVICE_ALGO_SIGFM`, claims enroll 20/20 + first-try verify on their
unit) against our NBIS pipeline (local-mean gain 1.0, 128x160, thr 14,
best-of-N, tickets 17/35/39/41/43) using OUR captured frames only
(`10564B` wire → 64x80 decode). No driver changes until metrics decide.

**Do not relitigate:**
- Tickets 18/35/39/41/43 operating point: thr 14, ENROLL_MIN 12/15,
  stages 5, pressure-ladder enrollment. SIGFM must beat these on FAR/FRR,
  not just minutiae counts.
- Their geometry is 80x88 flat / FW 10034; ours is 64x80 block-aware /
  FW 10036 — decode stays ours; only the matcher + preprocessing vary.

**Source:** /tmp/libfprint `b159d3e` (SIGFM merge), `RE_IMAGE_PROCESSING.md`
(Windows uses proprietary SGX matcher + NN upscaler, no NBIS strings),
`IMAGE_PIPELINE_COMPARISON.md`, their `squash_frame` thirds + unsharp
r=3/s=4.0 + diversity-reject (>90% similar → FDT_UP).

**Status:** closed (verdict: decided / frozen on NBIS)

**Acceptance:**
- Offline matrix on real captures: genuine-pair scores, impostor scores
  (multi-finger gallery per ticket 43), minutiae counts per image.
- Decision: adopt SIGFM (+ which preprocessing) or keep NBIS, with numbers
  in the ticket. No "looks better" verdicts.

## Final Audit & Closure (2026-09-11)
- Verdict: CLOSED (decided / frozen on NBIS).
- Findings:
  1. The NBIS/Bozorth3 operating point (threshold 14, best-of-N, floor 12/target 15, 5 stages) is fully locked in and hardware-verified across Tickets 18, 35, 39, 41, 43.
  2. The C driver remains frozen on NBIS. Any SIGFM evaluation remains strictly offline research and shall not touch driver code.
