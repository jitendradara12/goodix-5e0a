# 79: Residual-Range Dynamic-Range Frame Proxy (Offline, Then Hardware)

**What to build:** An offline threshold analysis (no driver changes at first)
that replaces Milan `getQuality` with the `residual_range` metric
(`residual_max − residual_min` from the driver's 3x3 local-contrast path) as
the best-of-N burst rank, validated on **real live burst** frames — then, only
if the offline separation holds with FAR intact, wire it behind the ticket-76
rank interface (`quality` → `residual_range`, same journal shape) for a
hardware verify.

**Blocked by:** 78 (closed 2026-09-14 — gain shaping confirmed on synthetic
dense but falsified as the live quality=0 cause; `qout` side-channel dead;
`residual_range` correlates: 727/704 → quality>0, 394/0 → 0).

**Status:** ready-for-agent

## Acceptance Criteria

- [ ] Step 0 (user-only, agent has no fingers): user saves one real 4-frame
  live burst (deliberate press + one casual tap) to `experiments/live_burst_*.pgm`
  (64x80 P2 12-bit, same layout as `fingerprint.pgm`) and pastes the capture
  command + output. No real live burst exists in-repo today (only synthetic
  dense + sparse fingerprint + blank) — do NOT invent live data or tune the
  threshold on synthetic frames alone.
- [ ] Offline probe (copy of the ticket-78 harness): per-frame
  `residual_range` + Milan `identifyImage` score vs `milan_dense_pad.tpl`
  (and, once enrolled on live data, vs a live template) showing a threshold
  between ~394 and ~704 that keeps matchable frames and drops blanks
  (e.g. live settled ≥ threshold > sparse/blank) with genuine-100 /
  impostor-0 intact.
- [ ] Only then: driver wiring reusing the ticket-76 rank/journals (one
  variable: burst-winner ranking only; enrollment floor unchanged), ninja
  drivers-only build + full test suite green, patch synced.
- [ ] Hardware verify per AGENTS.md two-phase protocol with pre-registered
  journal signatures; conclude only confirmed / falsified /
  inconclusive-because-[flaw] + the single next experiment.

## Context & Evidence

- Ticket 78 probe (`experiments/test_getquality_contrast.c`, exit 0 CONFIRMED):
  driver shaping `g1.0-m128` still reports quality 12 on dense-like input, so
  live 0/0 frames are sparse-like, not gain-starved. `qout[0]==overlap`,
  `qout[1]==quality` every row (no side-channel); identify details flat
  `[100,100]`. Quality is clarity-only (impostor dense scores 19 vs genuine
  18) — valid solely for intra-burst same-finger ranking.
- Ticket 76 hardware: every live frame `quality=0`, `overlap` flat intra-burst;
  winner == minutiae winner. Ticket-39 minutiae order remains the fallback.

## Predicted Signatures

- **Confirm** (range separates live): settled live frames sit clearly above the
  threshold, blanks/sparse below, genuine 100 / impostor 0 intact, and the
  hardware burst winner differs from the minutiae winner on ramp frames with
  casual taps matching first touch → keep the wiring.
- **Falsify** (range overlaps): live matchable frames and blanks interleave
  across the threshold, or winners == minutiae winners line-for-line again →
  revert the wiring; next experiment pursues multi-frame fusion or enrollment
 -side changes, never minutiae-floor relitigation without new data.
- **Inconclusive-because-[flaw]**: no real live burst provided (synthetic-only
  tuning), DLL/template path missing, or dirty-TLS-park noise in the journal
  (re-run after `sudo systemctl restart fprintd`).
