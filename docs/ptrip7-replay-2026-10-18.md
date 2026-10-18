# Issue #12: ptrip7 capture replay, 2026-10-18

**Decision:** keep the installed/default driver unchanged. Enrollment-only
fixed-pattern correction plus band-pass is a provisional candidate worth
preserving. The vendor preprocessor is executable but has not demonstrated a
fix with a valid calibration source. Do not change matching thresholds, touch
count, or enable learning on the strength of these results.

All results below are offline on the owner's x86-64 Linux laptop, through the
production PE loader and the actual Milan engine. No USB access, service
restart, installation, or new hardware run occurred. Nothing was posted.

## Inputs and version tracking

Source: [ptrip7's updated comment and archive](https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6249714294).

| Archive | SHA-256 |
| --- | --- |
| Initial attachment, file 33627563 | `55a0d0345c60dfb9d6c33375e8baa52f8e8c474c335abad474f2cb7130c83c16` |
| Updated attachment with `replay/`, file 33627601 | `328c3c7a79bf8338b52e565ec743c713ab7d55c66a805cd300583c696c4f55c0` |

The update adds `replay/README.md`, `replay/twofold_replay.c`, and
`replay/fpn.py`, and changes the top-level README. All existing captures,
labels, patch, journal, and FPN image are byte-identical between the archives.
Both source archives and intermediate runs are retained in the local excluded
dataset directory, outside the publishable audit results.

- 213 raw P2 images, each 64x80 with maximum 4095.
- Session 1: 96 frames, 24 consecutive four-frame touches, left little finger,
  stock normalization; enrollment was aborted.
- Session 2: 52 enrollment frames, 25 genuine-probe frames, 40 wrong-finger
  frames, using ptrip7's band-pass patch with the repo capture configuration.
- Enrollment uses `enroll/touch_02` through `touch_13`. The journal's first
  touch precedes enrollment activation and has no enrollment quality check.
- Five successful genuine touches have only frame 1, because the live driver
  stopped the burst after a fast-path success. Uncaptured later frames cannot
  be invented for another preprocessing method.
- No measured no-finger background or vendor calibration artifact is present.
  The supplied FPN estimate averages **all 213 frames**, including probes. It
  is excluded from candidate evaluation to avoid train/test leakage.

Our normalizer reproduces **all 213 saved normalized images byte for byte**:
96 stock and 117 band-pass. Input hashes are saved in
[inventory.json](../legacy-experiments/milan-audit/ptrip7-results/inventory.json).
The engine SHA-256 is
`9990ab24af01b8c5c575c73cf7a95a7d675655adfb4183b6c030de2912ec23de`.

## Exact reproduction of the supplied replay

The first 980 lines of the supplied C program are identical to the repository's
existing loader. Its new main and preprocessing code were read before running.
Built with its documented `gcc -O1 ... -lm` command on Linux, it reproduces
every published count and score histogram:

| Contributor harness method | Genuine frame matches / 96 |
| --- | ---: |
| Stock 3x3, gain 1.5 | 0 |
| Band-pass, smooth radius 1, target 80 | 61 |
| Enrollment FPN + stock 3x3 | 0 |
| Enrollment FPN + band-pass, smooth radius 0, target 40 | 0 |
| Enrollment FPN + band-pass, smooth radius 0, target 60 | 75 |
| Enrollment FPN + band-pass, smooth radius 0, target 80 | 73 |
| Enrollment FPN + band-pass, smooth radius 1, target 80 | 71 |

These are 96 correlated **frame probes**, from two folds of 12 held-out
touches. They are not 96 independent verification attempts or a wrong-finger
test. See [the exact output](../legacy-experiments/milan-audit/ptrip7-results/ptrip7-original-replay.log).

Two implementation differences matter when comparing to the live driver:

1. The contributor chooses enrollment frames by quality alone. The driver
   breaks ties using overlap, raw range, and active area. Changing only the C
   harness's ranking to the driver policy changes band-pass from **61/96 to
   62/96**. FPN plus the radius-0/target-60 band-pass remains **75/96**.
2. The C harness ignores `enrolAddImage` errors and does not check accepted
   count/progress. Instrumentation shows that **all 24 stock submissions return
   131 (0x83), with zero accepted images and zero progress**. Its `templates
   2/2` therefore means serialization succeeded, not that two valid 12-touch
   enrollments completed. Our runner reports enrollment failure rather than
   attributing those results solely to verification.

Diagnostic patches and outputs are preserved:
[enrollment instrumentation](../legacy-experiments/milan-audit/ptrip7-instrumentation.patch),
[instrumented log](../legacy-experiments/milan-audit/ptrip7-results/ptrip7-instrumented.log),
[driver-ranking patch](../legacy-experiments/milan-audit/ptrip7-driver-ties.patch),
[ranking output](../legacy-experiments/milan-audit/ptrip7-results/ptrip7-driver-ties.log).
The original supplied source remains unmodified.

## Labeled session: match the actual driver policy

The replay keeps 12 enrollment stages, 64x80 geometry, the same DLL, the same
engine decision rule, and the production frame-selection policy. Verification
tries the strong-contact first frame, then the final best frame. Each identify
call unpacks and deletes a fresh copy of the packed template, as the production
wrapper does. Return code, signed score and matched index are saved separately.

| Method | Genuine touches matched / 10 | Wrong-finger touches matched / 10 |
| --- | ---: | ---: |
| Stock normalization | Enrollment rejected on first submission | Not evaluated |
| ptrip7's band-pass patch | **5** | **0** |
| Enrollment-only FPN + radius-0, target-60 band-pass | **7** | **0** |
| Vendor preprocessing with enrollment-only FPN proxy + 2048 | **0** | **0** |

The band-pass baseline reproduces the exact journal winners and decisions:
genuine touches **02, 03, 04, 05, 07**, with scores **74, 80, 77, 96, 90**.
All five baseline genuine misses have signed score **-7** in this dataset.
This is a measured result for these captures; public `pts=0` still does not
imply -7 for every other input.

The fixed-pattern method retains all five successes and additionally matches
touches **06 and 08**. Its three remaining misses all have four saved frames,
so missing later frames do not explain those three failures. The two recovered
touches score **54 and 74** at the final decision. Its FPN is the mean 3x3
residual over the 48 enrollment frames only, frozen before any probe is read.
No parameter sweep on the ten labeled probes was performed: radius 0 and
target 60 were taken from ptrip7's already-published comparison.

All three methods that complete enrollment also reject the three separate
generated processing controls: a constant 2048 frame, independent Gaussian
noise, and estimated fixed pattern plus that noise. These supplement the ten
real wrong-finger attempts; they are not additional human samples.

**The vendor row uses an explicitly exploratory proxy, not real calibration.**
Every tested preprocessor call returns zero and passes guards, and enrollment
reaches 12 accepted images / 100%. Nevertheless, it matches zero of the ten
available genuine touches and only 10/96 session-1 frame probes. The five
one-frame captures also limit the vendor comparison. This rejects that proxy
as a demonstrated fix; it does not falsify the properly calibrated Windows
path or establish that our recovered integration contract is complete.

Full per-touch/per-frame results and provenance:
[summary.json](../legacy-experiments/milan-audit/ptrip7-results/summary.json),
[band-pass](../legacy-experiments/milan-audit/ptrip7-results/labeled-bandpass.json),
[FPN candidate](../legacy-experiments/milan-audit/ptrip7-results/labeled-fpn-bandpass-s0-std60.json),
[vendor proxy](../legacy-experiments/milan-audit/ptrip7-results/labeled-vendor-enrollment-estimate.json).

## Reproduce the comparison

Extract the updated archive to its own directory. Build the existing offline
native library as described in [PROTOTYPE.md](../legacy-experiments/milan-audit/PROTOTYPE.md),
then run on x86-64 Linux with Python and NumPy:

```sh
python3 legacy-experiments/milan-audit/ptrip7_replay.py \
  --dataset /path/to/extracted-dataset \
  --native-library /path/to/libgoodix-milan-probe.so \
  --out-dir /path/to/results
```

Each experiment runs in a fresh process. The runner checks geometry, sample
range, exact saved normalization, disjoint train/test files and hashes, and
12 accepted enrollment touches / 100% progress. Nonzero preprocessing or
enrollment results remain failures, not presumed valid images/templates.
Calibration estimation never reads test frames. Generated controls are
identified separately in each labeled output.

For the exact contributor replay, follow its `replay/README.md`. The two
diagnostic patches can each be applied to a separate copy of
`twofold_replay.c`; neither is needed for the original result.

The earlier prototype runner tried identify after every running-best update,
which was broader than the driver's first-frame/final-best behavior. This
was corrected **before** producing the labeled baseline reported here.
The native synthetic controls were rerun after that correction and still
pass; see [saved controls](../legacy-experiments/milan-audit/ptrip7-results/linux-selfcheck-after-replay-fix.json).

## Verdict and single next experiment

**Confirmed:** the contributor's preprocessing results reproduce; stock
normalization fails on these real inputs; enrollment-only FPN correction
recovers two additional labeled genuine touches with no observed loss in the
small wrong-finger set.

**Inconclusive-because-unverified-calibration:** vendor preprocessing as the
remaining fix. Its generated-image software checks did not predict real-input
matching. This dataset is one person/two fingers and does not establish safety
or generalization across devices. No production/default change is justified.

**Single next experiment:** establish the vendor initialization background's
actual acquisition/settings for ptrip7's unit, then rerun the same saved
enrollment/probe comparison using that background. Trace the Windows
initialization path before asking the contributor for another capture; do not
ask them again for calibration files they have already said they lack.

- Confirm that candidate only if it improves final genuine matching over the
  fixed band-pass baseline, preserves all observed baseline successes, and
  rejects wrong-finger/processing controls.
- Falsify that candidate if valid calibration and the checked call contract
  still fail to improve matching or introduce negative-control matches.
- An unverified background acquisition makes the result inconclusive; a higher
  quality score or successful preprocessing return is insufficient.

Any later driver deployment additionally needs the owner's working-unit
regression test and the repository's timestamped 20-second hands-off / steady
hold protocol, with explicit journal outcomes. Neither has happened here.
