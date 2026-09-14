# 80: Fuller-Contact Live Burst — Range-Among-Matchable Retest (Offline, Then Enrollment-Side)

**What to build:** Nothing new at first — re-run the ticket-79 offline tools
(`probe79`, `enroll79 1.0 live`) against a fuller-contact live burst. Only if
live frames enroll (`add_res=0`, stitched>0) and match own template does the
narrower claim get tested: does `residual_range` order the burst winner
correctly intra-burst? If enrollment still rejects (`add_res=131`), pivot to
enrollment-side comparison (how the device flow succeeds on live data where
the offline single-burst 4-touch enroll fails: touch count across presses,
enroll-time shaping, stitching thresholds) — never minutiae-floor
relitigation without new data.

**Blocked by:** 79 (closed 2026-09-14 — falsified: live ranges span
702.7..935.0, with several exceeding matchable dense-A 727.4, yet enroll 0/8
and match 0/8; range = edge energy, not clarity; positive control healthy).

**Status:** closed (verdict: inconclusive-because-contact-ceiling; successor: 81)

## Acceptance Criteria

- [ ] Step 0 (user-only): fuller-contact burst via
  `legacy-experiments/capture_live_burst.py` — flatter finger, hold until
  per-frame `active(>30)` reads >2000 (vs 392..764 in ticket 79), same
  `live_burst_press2_*.pgm` naming; paste command + output. If contact stays
  <1000 active after two tries, stop and declare the contact ceiling.
- [ ] Offline: `enroll79 1.0 live` pointed at the new burst (or argv-extended
  harness) shows `add_res=0` stitching and own-template genuine matches with
  impostor/blank/noise rejects intact; then `residual_range` vs winner
  correlation judged intra-burst (same finger only, ticket-78 #3).
- [ ] Only then: any driver wiring behind the ticket-76 rank interface (one
  variable, enrollment floor unchanged), ninja drivers-only build + full
  suite green, patch synced.
- [ ] Hardware verify per AGENTS.md two-phase protocol with pre-registered
  signatures; conclude only confirmed / falsified /
  inconclusive-because-[flaw] + the single next experiment.

## Context & Evidence

- Ticket-79 live data (gitignored `*.pgm`, sha256 in `/tmp/opencode/f_live.log`):
  press active 392..474 ranges 702.7..770.3; tap active 703..764 ranges
  908..935; `getQuality` 0/0 all 8 (pre-enroll); own-enroll `add_res=131` ×8
  at g1.0/g1.5 × live/live8; degenerate 1443B template; control dense 8/8
  stitched 22822B self-match 100.
- Live residual asymmetry (+485..+658 max vs −216..−276 min) vs dense ±360:
  partial-contact edges dominate the metric. Fuller contact should collapse
  the asymmetry toward dense-like if the frame becomes ridge-dominated.

## Agent prep (2026-09-14, offline — blocked on Step-0 user capture)

- `test_enroll_live_burst.c` argv-extended (backward compatible): optional
  4th arg `prefix` (default `legacy-experiments/live_burst_press`), so the
  ticket-80 burst enrolls via `enroll79 1.0 live
  legacy-experiments/live_burst_press2` with no re-edit. Score matrix now =
  prefix frames + fixed list (press, press2, tap, dense/seed68/sparse/blank;
  missing files warn+skip), and live/dense-self classification is name-based
  (`live_burst_` substring / exact dense-pad match) instead of row-index, so
  prepended rows and missing-file gaps can't shift populations.
- `test_residual_range_proxy.c` no-argv candidates now include zero-padded
  `press_01..04`, `tap_01..04`, and `press2_01..04` (old list only had
  unpadded names absent from disk).
- Re-baselined on ticket-79 data (builds exit 0; reviewer subagent: no new
  warnings, bounds CLASSIFICATION/COMPAT PASS): default `enroll79 1.0 live`
  reproduces 79 exactly (`add_res=131` x4, 1443B, 0/8, ranges
  702.7/728.1/765.8/770.3 + 935.0/923.0/915.0/908.0); `densectrl` CONTROL-OK
  (22822B, dense self-match 100); probe79 no-argv now auto-finds all 8 live
  frames with identical ref ranges (727.4/703.8/394.1/0.0). Missing prefix
  fails loud (`[INCONCLUSIVE-because-live-missing] ...press2_04.pgm unreadable`).
- No driver changes, no patch regen. Next: user Step 0 below, then agent runs
  `enroll79 1.0 live legacy-experiments/live_burst_press2` (+ `1.5` variant)
  and judges confirm/falsify per Predicted Signatures.

## Try 1 (2026-09-14, user capture + offline agent analysis — contact gate NOT met)

- Capture output pasted (4/4 saved, `decrypted=7684` clean): active
  379/372/377/372, max 660/663/667/659, avg ~19.2-19.5 — at/below
  ticket-79 press (392..474), 5.3x below the >2000 gate. SHA-256 prefixes
  `7b9ba9d2/96bb9a45/6a4efc1a/6efff713` (`live_burst_press2_01..04.pgm`).
- probe79 on press2: res_min −191..−193 / res_max +470..+476 (ratio ~2.5x,
  same positive skew as 79-live +485..+658 / −216..−276 vs dense ±360 —
  edge-energy signature repeats, no collapse toward ridge-symmetric);
  ranges 660.0/663.0/667.0/666.7, `getQuality` 0/0 ×4, FAR intact.
- `enroll79 1.0` AND `1.5 live legacy-experiments/live_burst_press2`:
  `add_res=131` ×4, stitched=0, 1443B degenerate, 0/12 match incl. self,
  non-live reject 5/5.
- Independent review (`ses_f5eda3d67ffefPDGp2ilxS1rfe`): neither Confirm
  (contact 19% of gate) nor Falsify (rejection without >2000 contact carries
  no force). One try remaining per the two-try rule — ceiling declaration now
  would be premature.

## Predicted Signatures

- **Confirm** (contact was the flaw): new burst active>2000, enroll stitches,
  own-template genuine 100 / impostor 0 intact, and intra-burst winner by
  range == most-settled frame → wire range behind ticket-76 interface.
- **Falsify** (metric dead at any contact): still `add_res=131` / 0 matches
  despite active>2000 → range is not a matchability rank, period; next
  experiment goes enrollment-side (device-vs-offline enroll comparison).
- **Inconclusive-because-[flaw]**: contact ceiling <1000 after two tries
  (sensor/placement limit, not signal), DLL/template path missing, or
  post-enroll quality column cited as signal (known state pollution).

## Try 2 (2026-09-15, user capture — two-try ceiling gate met)

The user repeated the exact capture command after the first failed try:

```text
PYTHONPATH=/home/sastauser/code/temp/goodix nix-shell -p python3Packages.pyusb openssl --run "python3 legacy-experiments/capture_live_burst.py --out-prefix legacy-experiments/live_burst_press2"
```

All four reads were complete (`decrypted=7684`) and saved, but the contact
remained below the ticket's `<1000` ceiling and far below the `>2000` confirm
gate:

```text
frame 1: pixels=5120 min=0 max=687 avg=22.3 active(>30)=432
frame 2: pixels=5120 min=0 max=676 avg=22.4 active(>30)=427
frame 3: pixels=5120 min=0 max=671 avg=21.5 active(>30)=417
frame 4: pixels=5120 min=0 max=668 avg=21.3 active(>30)=410
```

The user then made a third, explicitly well-settled/pressed attempt. It was
also complete but weaker:

```text
frame 1: pixels=5120 min=0 max=487 avg=9.7 active(>30)=272
frame 2: pixels=5120 min=0 max=496 avg=10.2 active(>30)=283
frame 3: pixels=5120 min=0 max=491 avg=9.7 active(>30)=276
frame 4: pixels=5120 min=0 max=492 avg=9.4 active(>30)=265
```

The current (third-attempt) ignored PGM bytes are recorded for provenance:

```text
5da72b166b6cc3a06c5912a76a16929c80f8de068ec1823ef072b15782c5f1fb  legacy-experiments/live_burst_press2_01.pgm
70c163a9c78f5dc5d53a43827f7d957a4e7b772e793e67d613ddf205615f53a4  legacy-experiments/live_burst_press2_02.pgm
fd9ec8c64d62b4b15dbed9eebbced49f564f1a2a4d6174b02fedddfbe728d137  legacy-experiments/live_burst_press2_03.pgm
acd6ee3f03ac032f80a7592be5c86d425fdfef36edbe735941d713a769ee16e5  legacy-experiments/live_burst_press2_04.pgm
```

The second-attempt PGM files were overwritten by the third attempt; its
console output is preserved above, but no byte/hash claim is made for that
attempt.

## Offline result (2026-09-15, no driver changes)

- `probe79` on the third attempt reported ranges `490.9/500.3/495.3/495.0`,
  residuals approximately `-140..-143 / +351..+357`, `getQuality=0/0`, and
  preserved the synthetic FAR control (`dense-A=100`, dense-impostor,
  sparse, and blank rejected). The positive residual skew remains an
  edge-energy observation, not a matchability result.
- `enroll79 1.0 live legacy-experiments/live_burst_press2` and the `1.5`
  repeat both reported `add_res=131` for all four enrollment inputs,
  `stitched=0`, `progress=0%`, a `1443B` degenerate template, and `0/12`
  live matches including self. Non-live rejection remained `5/5`.
- These failures do **not** falsify the metric: neither the original ticket-79
  bursts nor either ticket-80 fuller-contact attempt reached `active >2000`.
  The best live frame observed anywhere was ticket-79 tap `active=764`.

## Verdict and closure

**Inconclusive-because-contact-ceiling.** The ticket's own stop rule — contact
remaining `<1000 active(>30)` after two attempts — was met by try 2 (`432` max);
try 3 (`283` max) corroborates it. Confirm was not reached (`>2000`, stitching,
and own-template matches all failed), while falsify was not reached because
its required `>2000` contact condition was absent. This is a ceiling for this
sensor/placement/capture setup, not proof that the metric is dead at fuller
contact.

No range wiring, driver change, build, patch regeneration, or hardware-verify
claim is warranted. The single next experiment is the enrollment-side
device-vs-offline comparison in ticket 81; do not relitigate the minutiae
floor or residual-range rank without new data.
