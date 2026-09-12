# 69 — Genuine-Pair Yield Shortfall (Rich Probe + Rich Gallery, Score < 14)

**What to build:** TBD by experiment below — either enrollment-coverage change or image-pipeline change. This ticket starts as a discriminating hardware experiment, not a code change.

**Blocked by:** 68 (floor verified at 16; unlock-consistency falsified — this is the prescribed falsify-branch successor).

**Status:** ready-for-agent

---

## 1. Problem & Evidence

Across tickets 65/68 hardware runs, probes with 15–23 minutiae against galleries with all templates 16–25 minutiae repeatedly score 3–11/14 (two probe>=20 misses: 20->11, 21->8). Genuine success ≈ 2/9 attempts. Pairing yield (~30–50%) sits far below the ≥87.5% needed for a 16-minutiae probe to clear 14. The floor is exonerated (no dead templates remain); the shortfall is pairing failure or image quality.

Two candidate causes:
- (a) Coverage/placement: natural taps land on pad regions/angles/pressures the 10-stage ladder did not capture (Bozorth tolerates ≤10% stretch, ≤11°).
- (b) Image quality: 3×3 residual contrast or bilinear 2× upscale blurs/clips ridges so minutiae pair poorly even on overlapping skin.

## 2. Discriminating experiment (user only, no code change)

1. `fprintd-delete`, re-enroll the 10-stage ladder, noting which stage is the firm-center pad press.
2. Attempt A (position duplicate): place the finger as exactly as possible like the firm-center enroll press, 3 taps. Paste `5e0a bz3 match` blocks.
3. Attempt B (natural): 3 casual taps at varied angles. Paste blocks.
- If A matches (≥14) but B misses → cause (a): enrollment coverage. Next lane: ladder/position guidance or stage-count revisit (within FAR budget, ticket 65 math).
- If even A misses despite probe>=20 → cause (b): image quality. Next lane: offline contrast/upscale analysis on captublack frames (no driver change until a dose wins on hardware pairs).
- Conclude only: (a) / (b) / inconclusive-because-[flaw] + the single next lane.

## 3. Invariants & Guardrails (AGENTS.md)

- Floor stays 16, threshold stays 14, stages stay 10. No driver change in this ticket until the experiment discriminates.
- Verify protocol (Phase 1 silence already proven; only Phase-2 taps needed per run) and rule-7 smoke greps apply to every hardware run.

## 4. Predicted journal signatures

- Cause (a): `probe 20+ -> gallery[N] 15+/14 verify-match` on duplicated position; `probe 20+ -> max 8-11/14` on casual angles.
- Cause (b): `probe 20+ -> max < 14` on ALL attempts including careful duplicates.
