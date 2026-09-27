# 101: Verify FRR — Contrast Lane 1.5 + Per-Touch Enrollment Burst (Ticket 101)

**What to build:** Two driver fixes for the live verify-no-match regression
reported 2026-09-27 (`5e0a Milan verify: match=0 pts=0` on 5 consecutive
verifies across restarts and fingers, template unpack clean, transport
healthy):

1. `GOODIX_5E0A_CONTRAST_GAIN` 1.0 → **1.5** — the ticket-72 shootout's
   validated lane. At 1.0 the Milan engine's minutiae extraction sits only
   ~20-40% above its contrast floor; a light/sloppy press falls below it and
   the engine extracts nothing (`pts=0` = zero matching minutiae = impostor-
   level no-match against ANY template).
2. Per-touch burst reset on the enroll-continue path of
   `goodix5e0a_on_read_img` — `goodix5e0a_reset_touch_frames(self)` before
   `fpi_ssm_next_state(ssm)`, so each of the 12 enrollment touches banks its
   own 4-frame burst. Pre-fix live journal showed frame numbering
   `4/4 -> 5/4 -> ... -> 11/4` with the SAME stale `best frame 3/4`
   (identical range/overlap stats) re-submitted at every touch: one
   impression stitched 12 times instead of 12 distinct impressions.
   `reset_touch_frames` already ran at claim entry, `scan_start` (once per
   operation), SSM completion, deactivate, suspend and both enroll rejection
   paths — the enroll-continue branch was the one missing site.

**Blocked by:** none. (Root-cause analysis on top of ec5723d; PR #4 / ticket
100 audited and exonerated first — see below.)

**Status:** ready-for-hardware-verify

## Root-cause evidence (offline, real GoodixEngineAdapter.dll via the PE loader)

Method: `legacy-experiments/tune_gain_frr.c` — enroll 5 synthetic masters
(`gen_dense_live.py` seeds 67/68/101/102/103) through the driver's exact
normalization (3x3 residual, midpoint 128, gain G), then run a 20-probe
"sloppy touch" battery (residual contrast attenuation 0.9..0.3, ±2/±4px
shifts, ±4°/±6° rotations, 3x3 blur, ±15 noise, 1.3x/1.6x sharpening) plus
18 impostor/garbage probes and a 4-finger identify gallery. Match rule is
the driver's own: score > 0.

| gain | genuine accepted | impostor accepts | max impostor | identify FA |
|------|------------------|------------------|--------------|-------------|
| 1.0  | 14/20 (30% FRR)  | 0                | 0            | 0           |
| 1.5  | **18/20**        | 0                | 0            | 0           |
| 2.0  | 18/20            | 0                | 0            | 0           |
| 2.5  | 18/20            | 0                | 0            | 0           |
| 3.0  | 18/20            | 0                | 0            | 0           |

At gain 1.0 the cliff is exact: soft0.7 passes (67), soft0.6 scores 0. At
1.5 every probe down to soft0.3 passes (38). The two remaining rejects at
every gain are the 3x3-blur probes — information-destroyed frames no
front-end gain can recover; on hardware the best-of-4 burst selection
exists precisely to discard those. 1.5 chosen over 2.0+: identical battery
result, less clipping, and it is the lane the ticket-72 shootout already
validated for 100-vs-0 genuine/impostor separation.

Second-order effect (ticket 76 diagnosis): live `getQuality` reads 0/0
because the driver fed gain-1.0 buffers while the shootout's 18-19/98-100
readings came from gain-1.5 buffers. At 1.5 the ticket-76 quality proxy
should start ranking live frames by real quality instead of collapsing to
overlap/range.

Engine-build A/B (pre-ec5723d shims vs current, real DLL): byte-identical
decisions and scores on every battery — ticket 100 is not a confounder.

## Compatibility

- **Templates are contrast-lane dependent: re-enroll all fingers after
  deploying.** Existing templates were also single-impression (bug 2), so
  re-enrollment is required on both counts.
- `goodix5e0a.c` stays at 1999/2000 non-blank lines (ticket-73/76/77 budget,
  `test_f13`).

## Acceptance Criteria

- [x] Driver: `GOODIX_5E0A_CONTRAST_GAIN (1.5f)` with ticket-101 rationale
      at the definition (`goodix5e0a.h`).
- [x] Driver: `goodix5e0a_reset_touch_frames (self)` in the enroll-continue
      branch, after the deliver tail, before `fpi_ssm_next_state` (+1 line).
- [x] Docs: AGENTS.md normalization line updated (gain 1.5 + re-enroll note).
- [x] Tests: `tests/tier1_feature/test_f101_frr_contrast_and_burst_reset.py`
      (4 guards: gain lane, single calibration point, per-touch reset
      placement, hygiene sites preserved). `test_m1_c1` gain pin updated with
      rationale.
- [x] Suite: 375 executed / 375 passed / 8 skipped (was 371/371/8).
- [x] Offline battery: table above (0 impostor accepts at every gain).

## Hardware verify protocol (deploy, then)

1. `nixos-rebuild switch` (or reinstall), restart fprintd, **delete all
   enrolled fingers, re-enroll two** (e.g. left-index, right-index) with
   normal 12-touch flow.
2. Phase 1 — deliberate sloppy verifies (light, quick, off-angle presses),
   10 per finger: expect `verify-match` (or at minimum
   `5e0a Milan verify: match=1 pts>0`) on most; journal should show
   `5e0a Milan verify: match=1 pts=...` instead of `pts=0`.
3. Phase 2 — wrong-finger cross-checks, 5 per enrolled finger: expect
   `verify-no-match` with `match=0 pts=0`.
4. Confirm enrollment journal now shows per-touch bursts: every touch logs
   `5e0a frame 1/4 .. 4/4` then a fresh `best frame N/4` (N varies per
   touch) — no more `5/4..11/4` carry-over.
5. Confirm live `quality=` in `5e0a frame` lines is non-zero at least on
   settled frames (ticket-76 proxy activation); `overlap` near 98-100.
6. Verdict: confirmed / falsified / inconclusive-because-[flaw] + single
   next experiment. If genuine matches still fail with `pts=0`, capture one
   probe frame (`5e0a scan_on_read_img: declen=...` wire dump) for
   offline replay at gains 2.0/2.5 before touching anything else.
