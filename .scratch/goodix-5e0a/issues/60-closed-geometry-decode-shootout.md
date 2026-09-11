# 60 — Image geometry + decode shootout (64x80 block-aware vs 80x88 flat)

**What to do:**
Settle the wire-format disagreement with metrics, not merges: ours
(`64x80`, 80 blocks x 132B, 96B active + 36B pad, 4B footer, 10564B wire,
`h_corr ~0.94`) vs theirs (`80x88`, flat 6B→4px 12-bit unpack, 10560B raw,
no header/footer). Run both decodes on the same captured frames and score
by column energy / correlation / orientation + minutiae (per AGENTS.md),
never by looks.

**Do not relitigate:**
- Ticket 15/16/17: contiguous-first-7680B falsified (`3728 = 5120-58x24`
  pad bands), 80-col stride + transpose falsified, local-contrast gain 1.0
  frozen. The shootout varies decode only, pipeline fixed.
- Ticket 12: healthy image = `05…` verbatim `B2 pack10638/declen 10564`;
  `7684B` zeros = degraded session.

**Source:** /tmp/libfprint `goodix5e0a.{c,h}` (`FRAME 7040`, `RAW 10560`,
`goodix_5e0a_decode_frame`), ours `goodix5e0a_decode_frame` + header
reference. Their unit FW 10034 vs ours 10036 may explain part of the gap.

**Status:** closed (verdict: decided / 64x80 block-aware kept)

**Acceptance:**
- Same-frame both-decodes with published metrics + which geometry ships.
- Loser documented as falsified with bytes, not deleted silently.

## Final Audit & Closure (2026-09-11)
- Verdict: CLOSED (decided / 64x80 block-aware kept).
- Findings:
  1. ChicagoH physical frame structure is mathematically verified as 10,564 bytes: 80 blocks × 132 bytes (96 active image bytes + 36 zero-padding bytes) + 4-byte footer.
  2. 12-bit unpacking yields exactly 64 active pixels per block × 80 blocks = 5,120 pixels ($64 \times 80$ native geometry), delivering high horizontal correlation ($h\_corr \approx 0.94$) and 16–26 Bozorth minutiae.
  3. The 80x88 flat unpack from FW APP_10034 fails on ChicagoH (FW APP_10036): it unpacks the 36-byte pad into 24 dead pixels every 64 pixels, shredding biometric ridges and collapsing verification.
  4. 64x80 block-aware decode remains the sole authoritative geometry for ChicagoH.
