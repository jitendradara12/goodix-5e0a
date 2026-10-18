# Jet-Soup issue #12 archive audit, 2026-10-18

The raw frames reproduce the five published non-FPN match counts. This is a
historical frame-level replay, not a 12-touch enrollment benchmark. The archive
has useful capture settings, but its processed images, average-image file and
score description contain independently reproducible inconsistencies. Nothing
here justifies changing the installed driver or its default capture settings.

Source: [Jet-Soup's comment](https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6250208075),
[ZIP](https://github.com/user-attachments/files/33628140/5e0a-dataset-jet.zip).
ZIP SHA-256: `693d54803145987315da04bb6f6e35deb07b21243a930c5c2296d24abf25c7a8`.
The 52-file archive contains 24 raw PGMs, 24 normalized PGMs, an estimated
average PGM, two patches and README. No journal, pre-change frames, USB capture,
explicit finger labels, or measured calibration is included.

## Reproduction

The two patches apply to the declared base `5bfb69d` in a standalone temporary
directory. The supplied normalizer's unchanged function body was extracted into
[normalization-reference.c](../legacy-experiments/milan-audit/jet-results/normalization-reference.c).
Only static linkage is removed; its scalar typedef and constants come from the
declared base. Compilation does not include activation or device code.

An independent NumPy transcription agrees with this compiled C function for
every pixel of all 24 frames at target 80. The runner aborts on disagreement.
Each experiment runs in a fresh process through the unchanged production PE
loader and reviewed engine DLL. Enrollment errors, accepted count, progress,
identify return code, matched index and signed score are preserved. The engine
DLL SHA-256 is `9990ab24af01b8c5c575c73cf7a95a7d675655adfb4183b6c030de2912ec23de`.

Run from the repository on x86-64 Linux with a compiler, GLib development files,
Python and NumPy (the existing Nix environment supplies these):

```sh
bash legacy-experiments/milan-audit/build-native.sh /tmp/libgoodix-milan-probe.so
cc -shared -fPIC -O2 \
  legacy-experiments/milan-audit/jet-results/normalization-reference.c \
  -o /tmp/jet-normalization.so $(pkg-config --cflags --libs glib-2.0) -lm
python3 legacy-experiments/milan-audit/jet_soup_replay.py \
  /path/to/extracted-jet-archive \
  --native-library /tmp/libgoodix-milan-probe.so \
  --reference-library /tmp/jet-normalization.so \
  --out /tmp/jet-replay-results
```

[Summary and input hashes](../legacy-experiments/milan-audit/jet-results/summary.json).
No pixels, packed templates, keys or raw archives are included in these results.
Raw files remain under the locally excluded datasets directory on `sastapc`.

An independent direct-call check of the production C enrollment/verify wrappers
at target 100, with no quality calls interleaved, agrees exactly with the export
runner's enrollment codes/counts/progress, packed size, decisions and clamped
scores: [direct-wrapper-std100.json](../legacy-experiments/milan-audit/jet-results/direct-wrapper-std100.json).
The native synthetic controls still pass for current, band-pass and vendor paths.

## What the files establish

1. All 24 saved normalized PGMs match `roundf(128 + residual * gain)` with a
   clipped-edge 9x9 mean and `gain = 127 / max(abs(residual_min), abs(residual_max))`,
   byte for byte. They do **not** match the supplied patch's target-SD-80 output:
   5,063–5,099 of 5,120 pixels differ per frame. The raw frames remain usable;
   they can be reprocessed without new captures. This is a packaging/settings
   mismatch, not evidence that the sensor data is fabricated.
2. The estimated average's first sample is `4095`, the PGM maximum. Its remaining
   5,119 samples exactly equal the truncated mean of the first 5,119 pixel
   positions of the 24 raw frames. This proves a one-sample shift with a header
   value inserted and the last mean pixel lost. The likely cause is a PGM-header
   parsing mistake. A correctly computed mean is still a finger-contaminated
   estimate, not measured calibration. The replay harness computes its own
   average and does not read this supplied file.
3. The supplied patch still calls `goodix_milan_verify_image`, whose negative
   scores are clamped to zero. The claimed unclamped diagnostic change is absent.
   Our target-100 replay exposes scores 96/100/100/96 for frames 13–16, -4 for
   17–20, and -7/-7/-7/-4 for 21–24. The production wrapper displays the latter
   eight scores as zero. A displayed zero cannot distinguish these engine results.
4. Enrollment uses frames 1–12, which represent only three reported touches.
   Probes 13–24 represent three more. Four matching frames belong to one burst,
   not four independent successful verification touches. Finger identities are
   unspecified, so no genuine/wrong-finger error rate can be calculated.

## Historical replay results

Each row submits the first 12 individual frames and probes the remaining 12.
The optional FPN mode exactly follows the supplied patch: average **all 24
already normalized images**, subtract mean minus 128, round and clip. It uses
probe data and is retained solely to reproduce their experiment.

| Target SD | Accepted / progress | Matches / 12 frames | FPN accepted / progress | FPN matches |
|---|---|---|---|---|
| 60 | 8 / 66% | 0 | 7 / 58% | 0 |
| 80 | 12 / 100% | 4 | 8 / 66% | 0 |
| 100 | 12 / 100% | 4 | 8 / 66% | 4 |
| 140 | 12 / 100% | 0 | 10 / 83% | 4 |
| 180 | 12 / 100% | 0 | 12 / 100% | 4 |
| 220 | 12 / 100% | 4 | 12 / 100% | 4 |

The non-FPN rows 60/100/140/180/220 reproduce all five published counts.
However, the claim that enrollment always accepted all 12 is false for target
60: frames 5–8 return `0x83`; packing still succeeds with an incomplete context.
The claim that FPN changes none of the results is also not reproduced: targets
140 and 180 change from 0 to 4 matches. Neither result is a valid generalization
test because only three enrollment touches and no finger labels are available.

At targets 80 and 100, the matching probes are frames 13–16 (burst 4). At 220,
the matching probes are frames 17–20 (burst 5). Bursts 2 and 5 are comparatively
featureless and their four-frame mean rasters correlate at approximately 0.9995.
This warrants asking what the bursts represent, including contact state. It
does **not** establish that they are no-finger captures or false accepts.

Using the saved older normalized images instead gives 0 accepted submissions,
0% progress and an empty 1,443-byte packed template. Thus those files cannot
stand in for the successfully enrolled target-100 experiment.

## Capture patch and vendor input

Patch 0001 changes five config bytes (including two trailing checksum bytes)
and the image-request payload from `05 00 b0 00 b2 00 b0 00 b1 00` to
`01 00 ad 00 ae 00 ac 00 ad 00`. Keep these settings with Jet-Soup's unit in
future candidates. The archive cannot independently establish the reported
before/after improvement because the pre-change data and wire capture are not
included. Do not globally replace settings already working on other units.
The patch comment's categorical claim that the old payload belongs to a
different sensor family is not established by the reviewed vendor code, which
derives request flags and DAC values from per-device state.

The supplied raw PGMs have the 64x80, 12-bit convention accepted by the offline
vendor preprocessor. No different bit depth or arbitrary rotation is needed
for this replay contract. Correct input geometry alone does not supply the
missing same-unit calibration, or prove equivalence to their live Windows path.
Use the existing [Windows-cache exporter](../tools/CALIBRATION.md) if that unit's
cache is available; the archived driver establishes this file route. A reliable
live no-finger acquisition procedure has not yet been hardware-verified. Do not
give contributors an invented capture command or use this average as calibration.

The supplied replay hook also runs during device activation after earlier USB
operations. Our standalone replay avoids that hook entirely; installing the
patch just to replay these files is unnecessary.

## Next contributor requests

- **Jet-Soup:** identify the finger and contact state for each four-frame burst,
  especially bursts 2 and 5. Confirm the processed PGMs are from the earlier
  max-absolute-residual scaling and correct the average generator's header
  handling. Explain the absent unclamping change if a different diagnostic
  revision was used. Existing information/files are enough for this request;
  a new parameter sweep is not needed.
- **ptrip7:** export the existing Windows calibration cache using the helper,
  if present on the sensor's Windows installation. Their already labeled
  12-touch dataset is ready for the calibrated comparison. Jet-Soup can supply
  the same export if their own Windows cache is available; do not interchange
  calibration between units.

Verdict: **confirmed** published non-FPN frame counts, saved-normalization
mismatch, shifted average, and retained negative-score clamp. Calibrated vendor
performance is **inconclusive-because-missing-same-unit-calibration**; Jet-Soup
generalization is additionally limited by missing labels and touch count.

The single next experiment is to replay ptrip7's existing labeled dataset with
their validated same-unit Windows calibration export. Predict confirmation if
the guarded vendor path completes enrollment and improves held-out genuine
touches while retaining wrong-finger rejection; falsification if valid calibrated
processing fails to improve those final decisions. Missing/invalid/mismatched
cache provenance makes that experiment inconclusive. Hardware installation
would require a separate run under the repository's hands-off/holding protocol.

Audit correction: an initial temporary compilation accidentally used the base
normalizer because a patch operation inside the repository subdirectory skipped
its paths. That exploratory all-rejected result was withdrawn. Patches were
then applied outside the repository, radius/target code asserted present, and
all results here rerun with zero C/Python byte differences. The runner now aborts
on that mismatch. No sensor, installed driver, public comment, push or PR update
was involved.
