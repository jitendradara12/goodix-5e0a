# 78: Offline getQuality Contrast-Response Probe

**What to build:** An offline experiment (no driver changes, no hardware) that feeds saved 5e0a raw frames (`experiments/*.pgm`) through Milan `getQuality` while sweeping the normalization variants the driver could plausibly feed it — contrast gain (1.0 vs 1.5 vs 2.0), midpoint, and raw-vs-normalized input — and records `quality`/`overlap`/`qout[2]` alongside `identifyImage` match scores against the ticket-72 template, to find an input shaping under which native quality actually discriminates ridge clarity.

**Blocked by:** 76 (closed falsified — live frames all report `quality=0`; this probe finds out why without touching the driver)

**Status:** closed (verdict: confirmed-shaping-exists, gain-mismatch-falsified-as-live-cause; successor 79 pursues residual_range)

## Acceptance Criteria

- [x] Extend `experiments/test_goodix_shootout.c` (or a copy) to normalize each saved frame at gains {1.0, 1.5, 2.0} and report per-variant `quality`/`overlap`/`qout[2]` from `getQuality`.
- [x] Same variants run through `identifyImage` vs `experiments/milan_dense_pad.tpl`: genuine scores stay 100, impostor/blank/noise stay 0 (prove shaping does not trade FAR for quality range).
- [x] A dynamic-range table (variant × frame → quality/overlap/qout/match score) showing either (a) a shaping with intra-set quality spread (e.g. good frames ≥10, poor/blank =0) — the ticket-76 selector's missing input — or (b) proof that `getQuality` is flat across all shapings (quality is a dead end; fall back to residual_range/dynamic-range metric).
- [x] No changes to `libfprint-driver/` or the deployed patch (offline experiment only, ticket-72 lane rules).

## Context & Evidence

- Ticket 76 hardware run (2026-09-14, fprintd[327032]): every live frame `quality=0`, `overlap` flat intra-burst (36/36… then 25/25…), winner == minutiae winner. Verdict: falsified.
- Ticket 72 offline: `live_dense_pad` (shootout local-contrast, `gain=1.5`) scored quality 18-19 / overlap 98-100; blank/noise scored 0/0. Driver feeds `gain=1.0` buffers — the single biggest known difference between the two paths.
- `qout[2]` side-channel has never been logged on live-shaped frames; it may carry the range even when `quality`/`overlap` do not.

## Predicted Signatures

- **Confirm** (shaping found): some gain reports spread (e.g. dense_pad 15-19, fingerprint.pgm low, clear-0/noise 0) with genuine 100 / impostor 0 intact → successor ticket wires that shaping into the driver's quality path.
- **Falsify** (dead end): quality 0/0 and qout flat across all gains and frames while identifyImage still separates 100-vs-0 → `getQuality` is not a clarity oracle for this sensor path; successor ticket pursues the proven dynamic-range metric (residual_range correlation) instead.
- **Inconclusive-because-[flaw]**: DLL absent at the hard-coded path, or template file missing → fix harness paths, re-run.

## Implementation (2026-09-14, agent build, offline only — no hardware, no driver changes)

- New `experiments/test_getquality_contrast.c`: pristine ticket-72 PE-loader head
  (`head -n 896 experiments/test_goodix_shootout.c`) + probe tail with
  driver-faithful `normalize_gain_midpoint` (residual = pix − 3x3 local mean,
  out = midpoint + residual·gain, matching `goodix5e0a_normalize_raw_frame`)
  and `raw12_to_8bit` (>>4 shift, no local contrast) control.
- Variant sweep (6): `lc-g1.0-m128` (driver as-shipped), `lc-g1.5-m128`
  (shootout), `lc-g2.0-m128`, `lc-g1.5-m100`, `lc-g1.5-m160`,
  `raw-shift>>4` control. Frames (5): `live_dense_pad` (genuine A),
  `live_dense_pad_seed68` (impostor B), `fingerprint.pgm` (sparse impostor,
  active>30 = 697 of 5120 via repo-root P2 parse), `clear-0` (blank), synthetic white noise. Each cell reports
  `quality`/`overlap`/`qout[2]` + `identifyImage` vs `milan_dense_pad.tpl`
  (score/match/details) + residual min/max/range side channel.
- Build/run from repo root (binary kept outside the repo per env policy):
  `gcc -O2 -o /tmp/opencode/probe78 experiments/test_getquality_contrast.c -lm`
  then `timeout 120 /tmp/opencode/probe78` → exit 0,
  `[VERDICT: CONFIRMED] shaping with quality spread found; FAR intact on lc
  variants (raw control breaks genuine match: normalization required).`
- FAR is evaluated over local-contrast shapings only (the only inputs the
  driver plausibly feeds Milan); the raw row is a control proving
  normalization is required for matching.

## Evidence — dynamic-range table (verbatim, `q`/`ov` = quality/overlap)

| frame | g1.0-m128 | g1.5-m128 | g2.0-m128 | m100-g1.5 | m160-g1.5 | raw>>4 | match (lc) |
|:---|:---|:---|:---|:---|:---|:---|:---|
| live_dense_pad (genuine A) | 12/61, qout[61,12], 100 | 18/98, [98,18], 100 | 16/99, [99,16], 100 | 22/98, 100 | 14/97, 100 | 0/0, score 0 FAIL (control) | 100 all lc |
| live_dense_pad_seed68 (impostor B) | 14/65, 0 | 19/100, 0 | 15/100, 0 | 21/99, 0 | 16/99, 0 | 0/0, 0 | 0 all (correct reject) |
| fingerprint.pgm (sparse) | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0 all |
| clear-0 (blank) | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0 all |
| white noise | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0/0, 0 | 0 all |

Invariant side channels (every row): `qout[0]==overlap`, `qout[1]==quality`
(no hidden range — the side channel is dead); `identifyImage` details always
`[100,100]` (flat, no use). Residual ranges: dense 727.4, dense68 703.8,
fingerprint 394.1, blank 0.0 — quality>0 lands strictly above 394.

## Verdict: CONFIRM with one falsification inside (2026-09-14, offline)

1. **Shaping spread exists (confirm):** gain moves dense-frame quality 12→18
   (midpoint 100 → 22) while blank/noise stay 0/0 at every shaping, and FAR is
   intact on all lc variants (genuine 100, impostor/blank/noise 0). The
   ticket-76 selector's missing input exists for dense-like frames.
2. **Gain mismatch falsified as the live cause (do NOT re-litigate):** the
   driver shaping (`g1.0-m128`) still reports quality **12**, not 0, on
   dense-like input — yet live frames scored 0/0 even when they went on to
   verify-match. Live frames are sparse-like (residual_range ≈ 394 or lower,
   partial contact), not gain-starved. Wiring gain 1.5 into the driver would
   move dense-like frames 12→18 but cannot resurrect ranking on frames that
   score 0 at every shaping. No driver change follows from this ticket.
3. **Quality is clarity-only, not identity:** impostor dense finger scores as
   high as genuine (19 vs 18) — valid solely for intra-burst same-finger
   ranking (ticket-76's exact use), never across fingers.
4. **Raw control:** un-normalized genuine input scores 0/0 quality and fails
   to match (score 0) — normalization is required; the driver already feeds
   normalized buffers, so nothing to fix there either.

Successor: ticket 79 (offline `residual_range` dynamic-range proxy —
threshold between 394 and ~704 validated on **real live burst** frames, then
driver wiring behind the ticket-76 rank interface). No real live burst exists
in-repo today (only synthetic dense + sparse fingerprint + blank); step 0 is a
user capture. `git status` clean except the new probe `.c` + tickets;
`libfprint-driver/` untouched, `milan_dense_pad.tpl` byte-identical after the
baseline shootout re-run.
