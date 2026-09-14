# 78: Offline getQuality Contrast-Response Probe

**What to build:** An offline experiment (no driver changes, no hardware) that feeds saved 5e0a raw frames (`experiments/*.pgm`) through Milan `getQuality` while sweeping the normalization variants the driver could plausibly feed it — contrast gain (1.0 vs 1.5 vs 2.0), midpoint, and raw-vs-normalized input — and records `quality`/`overlap`/`qout[2]` alongside `identifyImage` match scores against the ticket-72 template, to find an input shaping under which native quality actually discriminates ridge clarity.

**Blocked by:** 76 (closed falsified — live frames all report `quality=0`; this probe finds out why without touching the driver)

**Status:** ready-for-agent

## Acceptance Criteria

- [ ] Extend `experiments/test_goodix_shootout.c` (or a copy) to normalize each saved frame at gains {1.0, 1.5, 2.0} and report per-variant `quality`/`overlap`/`qout[2]` from `getQuality`.
- [ ] Same variants run through `identifyImage` vs `experiments/milan_dense_pad.tpl`: genuine scores stay 100, impostor/blank/noise stay 0 (prove shaping does not trade FAR for quality range).
- [ ] A dynamic-range table (variant × frame → quality/overlap/qout/match score) showing either (a) a shaping with intra-set quality spread (e.g. good frames ≥10, poor/blank =0) — the ticket-76 selector's missing input — or (b) proof that `getQuality` is flat across all shapings (quality is a dead end; fall back to residual_range/dynamic-range metric).
- [ ] No changes to `libfprint-driver/` or the deployed patch (offline experiment only, ticket-72 lane rules).

## Context & Evidence

- Ticket 76 hardware run (2026-09-14, fprintd[327032]): every live frame `quality=0`, `overlap` flat intra-burst (36/36… then 25/25…), winner == minutiae winner. Verdict: falsified.
- Ticket 72 offline: `live_dense_pad` (shootout local-contrast, `gain=1.5`) scored quality 18-19 / overlap 98-100; blank/noise scored 0/0. Driver feeds `gain=1.0` buffers — the single biggest known difference between the two paths.
- `qout[2]` side-channel has never been logged on live-shaped frames; it may carry the range even when `quality`/`overlap` do not.

## Predicted Signatures

- **Confirm** (shaping found): some gain reports spread (e.g. dense_pad 15-19, fingerprint.pgm low, clear-0/noise 0) with genuine 100 / impostor 0 intact → successor ticket wires that shaping into the driver's quality path.
- **Falsify** (dead end): quality 0/0 and qout flat across all gains and frames while identifyImage still separates 100-vs-0 → `getQuality` is not a clarity oracle for this sensor path; successor ticket pursues the proven dynamic-range metric (residual_range correlation) instead.
- **Inconclusive-because-[flaw]**: DLL absent at the hard-coded path, or template file missing → fix harness paths, re-run.
