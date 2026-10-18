# 113: Vendor calibration and preprocessing prototype

**Status:** superseded (successor: 114, opt-in native-raster/band-pass hardware verification)

**What to build:** An offline prototype for the Milan vendor preprocessor,
using the recovered Windows call contract, explicit per-device calibration,
bounded buffers, and final enrollment/identify checks. Keep the shipped driver
and its canonical normalization unchanged until real-capture evidence supports
a candidate.

**Current workfront:** ptrip7's updated archive now supplies real labeled
captures and replay code. Their results have been reproduced; enrollment-only
FPN correction improves the labeled baseline from 5/10 to 7/10, with 0/10
wrong-finger matches for both. A measured same-unit vendor background is still
missing. The vendor path with an explicitly estimated proxy matches 0/10;
its generated-image controls alone did not predict a real-finger fix.

## Predicted signatures

- **Confirm software contract:** calibration and preprocessing return expected
  statuses, input/output guards remain intact, genuine synthetic controls can
  enroll and match through the real engine, and unrelated/blank/noise controls
  do not match. Synthetic results establish call correctness only.
- **Falsify software contract:** guard corruption, unsupported inputs silently
  accepted, engine failures, or failure of a positive control.
- **Confirm candidate on real inputs:** held-out genuine-touch matching improves
  on affected-unit captures without a wrong-finger regression; the owner's
  already-working unit remains a regression control.
- **Inconclusive-because-missing-real-inputs:** synthetic correctness alone
  cannot establish a fix or justify replacing the production pipeline.

For any later deployed-driver run: save `hands off` plus timestamp for 20s
(predicted silence), then `holding` plus timestamp for 20s (predicted capture,
progress, and final matching outcome). Conclude confirmed / falsified /
inconclusive-because-[flaw], with one next experiment.

## Prototype result, 2026-10-18

- Implemented guarded vendor preprocessing with the recovered purpose flag
  and NULL optional feature output. Corrected the audit's earlier undersized
  placeholder buffer; documented the error and reran the corrected call.
- Added native Linux execution through the unchanged production PE loader;
  the standalone library is not installed into libfprint.
- Added labeled P2/P5 replay with exactly 12 enrollment touches and the running
  best-frame verify fast path. Engine return/score/index remain visible.
- Emulated full checks: all three processing methods complete 12-stage
  enrollment, match the held-out synthetic positive, and reject the unrelated
  generated pattern, blank, and noise controls. Buffer guards and input
  validation checks pass. This does not establish real-finger improvement.
- The owner will run the native Linux software check. Native compilation and
  results are pending; no hardware access or driver installation is needed.

[Prototype instructions](../../../legacy-experiments/milan-audit/PROTOTYPE.md)
and [saved synthetic results](../../../legacy-experiments/milan-audit/prototype-results.json).

## Native result and packaging repair, 2026-10-18

- First handoff failed because the archive omitted `native_probe.c`. Copied
  that source to the extracted prototype directory over the owner's authorized
  SSH connection. No installed-driver files or services were changed.
- Native compilation and full software checks passed through the production
  Linux PE loader on `sastapc`. The native JSON matches the emulator's complete
  JSON exactly, apart from the backend label. Saved as
  [linux-results.json](../../../legacy-experiments/milan-audit/linux-results.json).
- Added a packager with explicit required-file checks and archive checksums.
  A deliberately incomplete archive is rejected. A fresh corrected-bundle
  extraction on Linux builds and passes the full check.
- Read-only search of saved laptop captures found the known old sparse/striped
  burst files and the known generated dense fixtures. No labeled 12-touch
  affected-unit dataset was found. The two `/tmp/test_*.pgm` files have no
  established capture provenance and are not promoted to real-finger evidence.
- No hardware run occurred; this is confirmed software behavior only. Status
  stays in-progress pending real affected-unit input.
- Posted the owner's authorized request for existing raw touch groups, labels,
  capture settings/patches, and same-unit calibration on
  [issue #12](https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6249543881).
  Verified the comment was published as `jitendradara12` through the owner's
  authenticated laptop account. No new scans were requested.

Single next experiment: replay the contributor's actual labeled touch groups
with same-unit calibration through the three fixed pipelines. Confirm with
improved held-out genuine matching and negative-control rejection; falsify if
the valid vendor path fails to improve final matching; missing calibration or
ambiguous touch labels makes the comparison inconclusive.

## Real-capture replay and updated archive, 2026-10-18

- Downloaded and retained both attachment versions. The update adds `replay/`
  and edits the README; captures, patch, labels and journal are byte-identical.
- Reproduced all 213 saved normalized frames byte for byte and all seven
  published C replay rows, including band-pass 61/96 and FPN candidate 75/96.
- Driver enrollment tiebreakers explain the separate runner's band-pass
  62/96 result. The supplied harness ignores stock enrollment errors; all 24
  stock submissions return 0x83, accepted=0, progress=0. Packing a template
  alone is not proof of a completed enrollment.
- Corrected the prototype's overly broad verify-at-each-running-best behavior
  to production's first-frame / final-best decisions before the labeled run.
  It now unpacks/deletes a fresh template per identify. Native synthetic
  controls still pass after the correction.
- Exact labeled baseline: same genuine touches 02/03/04/05/07 match, same
  scores 74/80/77/96/90, same enrollment winners, and 0/10 wrong-finger matches.
- FPN estimated from the 48 enrollment frames only, followed by the already
  published radius-0 / target-60 band-pass, retains those five successes and
  recovers genuine touches 06 and 08: 7/10 genuine, 0/10 wrong-finger. Flat,
  independent-noise and estimated-pattern-plus-noise controls do not match.
- Vendor proxy: initialization/process returns succeed and guards remain
  intact, enrollment accepts 12 touches / 100%, but only 0/10 available labeled
  genuine touches and 10/96 session-1 frame probes match. This proxy is not
  real calibration. Five labeled successful baseline touches have only one
  saved frame, limiting some alternative-method comparisons.
- The supplied all-213-frame FPN is excluded from candidate evaluation because
  it incorporates held-out probes. Raw inputs/archives are locally excluded;
  hashes, scores, return codes and diagnostic patches are preserved.

[Real-capture report](../../../docs/ptrip7-replay-2026-10-18.md) and
[saved results](../../../legacy-experiments/milan-audit/ptrip7-results/summary.json).

Verdict: confirmed offline preprocessing sensitivity and a reproducible FPN
improvement; vendor fix inconclusive-because-unverified-calibration. No
hardware run, driver installation, or public message occurred. Status remains
in-progress. The single next experiment superseding the earlier missing-data
step is to establish the actual Windows initialization background acquisition
and rerun these fixed captures with valid same-unit calibration. Confirm/falsify
predictions are in the report; do not request the absent files again without
first establishing a specific acquisition method.

## Windows cache acquisition resolved, 2026-10-18

- Traced `_UpdateImageBase` -> `AlgPreprocessInit`: the initialization pixel
  buffer is an accepted sensor image base, not an average of finger captures.
- The archived driver reads named `ImageBase` and `CaliData` records from
  the Windows system drive's `ProgramData/Goodix/goodix.dat`. The cache format
  has NLVF magic, UTF-16 names, bounded lengths and CRC-32/MPEG-2 checksums.
- Added a standard-library-only exporter that outputs only the background,
  optional serialized state and metadata. It preserves the source and refuses
  to overwrite an export. Seven tests cover format/data damage, bounds, endian
  conversion, duplicate keys, selected payloads and file preservation.
- Executed the actual archived reader/CRC against an in-memory synthetic
  cache. It agrees with the exporter and rejects damaged/truncated records.
- Added guarded saved-state load/save to the offline prototype and optional
  Windows-calibration input to replay. Native save/load and full synthetic
  replay round trips pass; wrong-size, CRC-damaged and version-damaged state
  are rejected rather than silently treated as calibrated.

[Acquisition report and next request](../../../docs/windows-calibration-2026-10-18.md).
Next input is ptrip7's same-laptop cached calibration export, if that cache is
present. This is a specific file-recovery request, not a repeat request for an
unspecified calibration file or new touches. Cache presence/format and same-unit
provenance remain unverified. No public request, PR, push, sensor operation or
driver installation occurred. Status remains in-progress pending that input.


## Jet-Soup archive audit, 2026-10-18

- Reproduced all five published non-FPN frame match counts through the native
  engine. Target 100 completes 12 submissions / 100% and matches frames 13-16;
  target 220 instead matches 17-20. Each four-frame group is one reported touch,
  and the first 12 submissions come from only three touches, with no finger labels.
- All 24 saved normalized PGMs instead exactly match older 9x9 max-absolute
  residual scaling, not the stated target-SD-80 patch. The supplied average has
  PGM maximum 4095 inserted as its first sample; the remaining 5,119 exactly match
  the truncated mean shifted by one position. Neither mean is real calibration.
- Supplied patch retains the negative-score clamp. The corrected standalone
  runner exposes the actual signed scores; the target-100 direct C wrapper
  cross-check agrees on all decisions and displayed scores.
- Enrollment at target 60 only accepts eight frames / 66%; packing succeeds
  anyway. Exact all-frame normalized-FPN replay changes targets 140/180 from zero
  to four matches, contrary to the claim of no effect. That mode leaks probe data
  and is historical reproduction only.
- An initial temporary reference build accidentally used the base normalizer;
  that all-rejected result was withdrawn. Actual patches were applied outside
  the checkout and the final compiled function agrees with an independent
  transcription for every pixel. The runner now aborts on that mismatch.
- Keep Jet-Soup's wire profile with their unit; no before-change frames or wire
  capture were supplied to establish a universal config fix. Bursts 2 and 5
  are featureless and highly correlated; ask their actual contact/finger labels
  before assigning genuine, wrong-finger or no-finger meaning.

[Report, reproduction and contributor requests](../../../docs/jet-soup-replay-2026-10-18.md).
Verdict: confirmed replay counts and package inconsistencies; vendor improvement
inconclusive-because-missing-same-unit-calibration. The single next experiment
remains ptrip7's labeled replay using a validated same-unit Windows cache export,
with confirm/falsify predictions in the report. Jet-Soup can clarify existing
burst labels and packaging in parallel. No new scans are needed for those
clarifications. No public comment, push, PR update, hardware operation or driver
installation occurred. Status remains in-progress.

## Superseded by 114, 2026-10-19

ptrip7 supplied the same-unit Windows cache. Alignment reproduces their
transpose finding, including against enrollment-only data. The engine accepts
the saved state. Calibrated vendor processing alone did not improve canonical
matching, but a controlled engine-raster comparison changed the outcome:
band-pass plus transposed 80x64 engine input gives 10/10 labeled genuine and
0/10 wrong-finger matches, and 82/96 held-out session frame matches (previously
5/10 and 62/96). Vendor preprocessing with aligned native input and matching
also gives 10/10 labeled and 78/96 frame matches. Band-pass reaches the stronger
frame result without calibration, so no further cache request is needed.

An opt-in patch preserves the public canonical raster, default normalization,
capture settings and 12-touch target; the experimental band-pass/engine
transpose is enabled only by GOODIX_5E0A_NATIVE_RASTER=1. Actual candidate C
wrappers reproduce all decisive results, C normalization matches the reference
on all 213 frames in both modes, gallery rejection paths and guarded software
controls pass. No deployed-driver run has occurred. This supersedes the old
missing-calibration workfront; it does not mark a hardware fix verified.

[Report and next experiment](../../../docs/calibration-raster-2026-10-19.md).
Successor: [114](114-ready-for-hardware-verify-native-raster-bandpass.md).
