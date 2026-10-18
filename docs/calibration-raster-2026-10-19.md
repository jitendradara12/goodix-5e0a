# Calibration and engine raster experiment, 2026-10-19

**Confirmed offline:** ptrip7's calibration export is usable, and the engine's
raster boundary accounts for a substantial part of the matching failure.
Keeping band-pass processing fixed and transposing the matcher input from the
driver's canonical 64x80 into 80x64 raises labeled genuine matching from **5/10
to 10/10**, with **0/10 wrong-finger matches** in both cases. The two held-out
session folds improve from **62/96 to 82/96 frame matches**. These are separate
evaluations; 96 correlated frames are not 96 independent attempts.

The actual C candidate reproduces these results. It is an **opt-in diagnostic
patch**, not a deployed fix. Production sources/defaults, sensor capture
settings, enrollment target and matching decision rule remain unchanged.

## Input and alignment

Source: [ptrip7's new comment](https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6251730042)
and [calibration ZIP](https://github.com/user-attachments/files/33631298/goodix-calibration.zip).

- ZIP SHA-256: `c800c443b6bacbf4ba8f028c1bd7669e96ffa890ff400d07f0cbdbcf22de75a7`.
- Source cache SHA-256 from export metadata:
  `fd5a01890d58f44f932d797e4360b64b0c44a8adad191be15c851fad0f19098b`.
- The archive contains only background PGM, 140,464-byte opaque calibration
  state, and metadata. Both exported-file hashes match. The reviewed engine
  accepts the state; guarded loads leave source data unchanged.
- Contributor confirms this cache is from the same laptop's Windows install,
  last written 2026-10-17 at 02:32. This is contributor provenance, not an
  independently authenticated hardware identity.

The helper preserves cache sample order. Its PGM header describes a container,
not an established match to Linux frame order. Interpret this cache as 64 rows
of 80 samples and transpose to the driver's 80 rows of 64:
`canonical[y*64+x] = cache[x*80+y]`. Do not modify the opaque state blob.

The cache's 3x3 residual correlates with the **enrollment-only** fixed-pattern
estimate at -0.060 as exported and +0.800 after transposition. Against all 213
frames, the corresponding figures are -0.059 and +0.803, reproducing ptrip7.
Thus alignment is supported without using held-out probe scores. Background
range is 1135–3160; residual SD is 124.78 in the exported reshaping and 80.03
after alignment. This differs from claiming the aligned SD is 124.8.

## Why the engine boundary was examined

In the reviewed engine `9990ab24…ec23de`, `ppp_param_init(10)` reads the profile
table at RVA `0xfb460`: entry 10 is
`[10, 1, 0, 4, 800, 64, 80, 10]`. Preprocessor globals identify `SENSOR_ROW=64`,
`SENSOR_COL=80`. The `preprocessor` export at RVA `0x7a3b0` uses these packed
globals and source byte count, rather than source image width/height, when
calling the internal routine at `0xc77b0`. After return, the wrapper copies
the resulting pixels to its output buffer.

A one-frame execution hook at `0x7a4e1` observed the returned internal raster's
first six uint32 fields as `[80,64,80,5120,1,0]`. This, the cache alignment and
the profile table motivated a bounded matcher-layout comparison. The decisive
evidence is the controlled replay: same raw touches, normalization, enrollment
count, first-frame/final-best policy and >0 decision; only engine image pixel
order/dimensions change. No angle/gain/threshold search selected the outcome.

The experiment keeps public driver and replay inputs canonical 64x80. For the
profile-10 preprocessor diagnostic, raw/calibration buffers are transposed into
the vendor layout and its output is converted back. For the matcher diagnostic,
the canonical image is transposed into a contiguous 80x64 image and those
dimensions are placed in the Goodix image record. Legacy layout modes remain
explicitly available to reproduce earlier reports.

## Results

All rows use the same labeled 12-touch enrollment and 10 genuine / 10
wrong-finger probes. Blank, independent-noise, and estimated-pattern-plus-noise
controls reject throughout. No new scans were used.

| Processing | Engine raster | Genuine | Wrong-finger matches |
|---|---|---|---|
| Existing band-pass baseline | 64x80 | 5/10 | 0/10 |
| Enrollment-only FPN + band-pass | 64x80 | 7/10 | 0/10 |
| Aligned cache residual + band-pass | 64x80 | 5/10 | 0/10 |
| Same, one gain fitted on enrollment only (0.80536) | 64x80 | 6/10 | 0/10 |
| Vendor, unaligned cache and saved state, legacy input layout | 64x80 | 0/10 | 0/10 |
| Vendor, aligned cache, legacy input layout, with/without state | 64x80 | 2/10 | 0/10 |
| Vendor, aligned cache, profile-10 input layout, saved state | 64x80 | 1/10 | 0/10 |
| Same, background only | 64x80 | 2/10 | 0/10 |
| Vendor, aligned cache, profile-10 input, with/without state | **80x64** | **10/10** | **0/10** |
| Band-pass, no calibration | **80x64** | **10/10** | **0/10** |
| Enrollment-only FPN + band-pass | 80x64 | 9/10 | 0/10 |

Original 3x3/gain-1.5 processing still fails enrollment at the first touch even
with the native matcher raster. Geometry alone does not rescue that filter.
For the no-calibration band-pass/native result, genuine scores are
40/77/61/90/30/67/38/37/54/38. The decision remains the existing matched-index
and positive-score rule; a threshold of 50 would be a different experiment.

The independent session has 24 reported touches of one finger. Each fold
enrolls one half's 12 complete touches, selecting one frame per touch, and
probes the other half's 48 individual frames:

| Pipeline | Fold 1 | Fold 2 | Total frame matches |
|---|---|---|---|
| Band-pass, 64x80 engine input | 34/48 | 28/48 | 62/96 |
| Band-pass, 80x64 engine input | 46/48 | 36/48 | 82/96 |
| Calibrated vendor, profile-10 input and 80x64 matcher | 41/48 | 37/48 | 78/96 |

[Saved scores, enrollment statuses, provenance and input hashes](../legacy-experiments/milan-audit/calibration-results-2026-10-19/summary.json).
These results do not include raw images, templates or calibration payloads.
The candidate does not need the Windows cache for the band-pass path.

## Prepared hardware candidate

[native-raster-candidate.patch](../legacy-experiments/milan-audit/native-raster-candidate.patch)
combines ptrip7's published band-pass implementation with an engine-boundary
transpose. It changes behavior only with `GOODIX_5E0A_NATIVE_RASTER=1` in the
driver process. Without that exact value, normalization and engine records
retain the existing path. This flag must be set on the actual driver process;
setting it only in a client shell does not change a running fprintd service.

Public capture buffers remain 64x80; only engine-facing image records become
80x64. Quality, enrollment, verify and gallery identify use the same conversion.
The temporary pixel buffer lives through each engine call and is freed after
it. Gallery failure paths initialize ownership before any forward jump.
The patch does not integrate the vendor preprocessor or require new cache files.

The isolated source directory is prepared by
[prepare_native_candidate.py](../legacy-experiments/milan-audit/prepare_native_candidate.py).
It refuses an output directory inside the checkout, applies the contributor's
patch outside Git, and emits the combined patch. It does not install anything.
The unchanged checkout and installed driver are preserved.

Validation completed on `sastapc`:

- Candidate PE-loader/C-wrapper build passes `-Wall -Wextra -Werror`.
- Extracted actual C normalization agrees byte for byte with the reference on
  all 213 raw frames, both with the flag off (original) and on (band-pass).
- [Actual C wrapper replay](../legacy-experiments/milan-audit/native_candidate_check.py)
  reproduces the 10/10 genuine, 0/10 wrong, all negative-control rejections,
  and 46/48 + 36/48 fold results. No Python image-record conversion substitutes
  for the candidate C adapter in this check.
- Actual gallery identify accepts a genuine probe, rejects a wrong-finger
  probe, and rejects an invalid template without a cleanup crash.
- Profile-10 guarded synthetic preprocessing, state save/load, CRC/version
  rejection and positive/negative controls pass; seven exporter tests pass.
- Full driver build status is recorded in `build.json` beside the results.

Example offline C-wrapper reproduction after compiling the isolated candidate
loader and its extracted `normalization.c`:

```sh
python3 legacy-experiments/milan-audit/native_candidate_check.py \
  /path/to/ptrip7-dataset \
  --library /path/to/libgoodix-native-raster-candidate.so \
  --normalization-library /path/to/native-raster-normalization.so \
  --enabled 1 --scenario labeled --out /tmp/candidate-results.json
```

## Next experiment and contributor coordination

Ticket 113 is superseded by **114: opt-in native-raster/band-pass hardware
verification**. This is ready for a deployed-driver check, not verified.

The single next experiment is a fresh 12-touch enrollment and labeled verify
run on ptrip7's affected machine using the opt-in candidate, followed by the
owner's working machine as the regression control. Use a separate test account
or an unused test enrollment so existing working templates are preserved.
Do not evaluate this processing change against templates enrolled under the
old image convention. Keep capture settings appropriate to each unit; a later
Jet-Soup trial would additionally retain their wire-only patch.

For each deployed run, first record **hands off + timestamp** for 20 seconds
while active: predict no spurious captures or enrollment advances. Then record
**holding + timestamp** for a steady 20-second press: predict prompt capture,
quality/overlap, and a positive known-finger decision or a single enrollment
advance followed by waiting for release, rather than repeated cycles. Finish
enrollment with 12 separate placements and record genuine/wrong-finger results
with the journal. Report observed latency, advances and outcomes.

**Confirm:** the candidate gives valid live enrollment, known-finger matches,
wrong-finger rejection and stable hands-off/hold behavior, while the owner's
working unit does not regress. **Falsify:** valid fresh enrollment still gives
no-match, wrong-finger matches appear, or the owner regresses. **Inconclusive:**
flag absent from the driver process, wrong build, mixed old/new templates,
missing labels or missing protocol phases. Conclude only confirmed / falsified /
inconclusive-because-[flaw], plus one next experiment.

No additional input is needed from ptrip7 to finish these offline tests. The
remaining contributor help is the hardware run. Jet-Soup's pending burst labels
remain useful but do not block this candidate. No fingerprint session,
installed-driver change or fprintd restart was performed during this investigation.

## Disposable hardware-test packaging

The owner authorized one workbench commit/push to PR #13. The contributor entry
point is now [HARDWARE_TEST.md](HARDWARE_TEST.md), using
`bash tools/test-native-raster.sh`. A production fix still belongs in a separate
small PR after hardware verification; this workbench is disposable.

The runner builds from a clean revision, applies the candidate only to a
temporary source copy, and uses an isolated runtime fprintd storage mount.
An independent recovery timer and explicit restore command protect interrupted
sessions. Numerical candidate diagnostics are emitted without enabling the
driver's raw-byte debug logs; the ZIP contains only allowlisted status and
numerical summaries. The original installed library and enrollments are not
replaced. Existing build-only and namespace probes do not access the scanner.

Ten failure-injection tests cover cleanup, interruptions, changed overrides,
invalid live storage and report filtering. A real transient-systemd namespace
probe passed on `sastapc`; normal fprintd PID, start time and active state stayed
unchanged. See [packaging checks](../legacy-experiments/milan-audit/calibration-results-2026-10-19/packaging-checks.json).
The first actual fingerprint run remains ticket 114. No issue comment is sent
by the runner or by the maintainer's agent.

Limits: one person's two labeled fingers, a small saved dataset, correlated
burst frames, and five successful baseline touches with only their first frame
available. An offline 10/10 is not a population accuracy estimate. The broader
session still has 14 unmatched frames, so a universal matching fix is unproven.
