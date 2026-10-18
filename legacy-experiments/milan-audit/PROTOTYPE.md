# Vendor preprocessing prototype

This is an offline experiment. It does not install a driver, restart fprintd,
read the sensor, or change firmware/keys. Production normalization remains
unchanged. The native backend uses the existing Linux PE loader and shims.

## Owner's Linux check

From the repository root or the extracted prototype bundle:

```sh
bash legacy-experiments/milan-audit/check-linux.sh
```

Send `probe-output/linux-selfcheck.json` and `probe-output/check.log` back.
On NixOS, missing development dependencies are supplied in a temporary
`nix-shell`. Elsewhere the check stops and names missing dependencies.
No root privileges are required. This is a software check, not the repository's
deployed-driver hardware protocol.

The library is built from `native_probe.c`, which includes the unchanged
`libfprint-driver/goodix_milan.c`. It exposes only an experimental in-process
call interface for this standalone Python process. It is not linked into the
installed libfprint driver.

The native check passed on the owner's x86-64 Linux laptop `sastapc` on
2026-10-18. Its complete result is identical to the emulated result except
for the backend label. All three methods complete 12-stage enrollment, match
the synthetic positive, reject the three negative controls, and pass buffer
and malformed-input checks. See `linux-results.json`. A second run from a fresh
extraction of the corrected bundle also passed. This is software validation,
not a deployed-driver hardware run or measured human accuracy.

## Completed local check

The real DLL executed under the existing emulator. All three processing
methods completed 12-stage enrollment and matched a held-out shifted/noisy
version of the generated pattern. Each rejected an unrelated generated
pattern, a flat frame, and a noise frame. Guard checks and malformed-input
checks passed. These controls establish basic correctness, **not an improvement
in human matching accuracy**. See `prototype-results.json`.

The generator for these controls uses a 10-pixel ridge period. Calibration is
an explicitly synthetic flat frame, not a recovered calibration from a user.
No percentages of real-world reliability are inferred from these controls.

## Bundle packaging

The first handoff archive accidentally omitted `native_probe.c`, causing a
missing-file compiler error. The source was copied directly to the owner's
test directory, and the native check then passed. The corrected packager
explicitly requires that C source and verifies every required archive member
and content hash. A regression check removes `native_probe.c` from a test
archive and confirms that verification rejects it.

Build a complete handoff archive from the repository root:

```sh
python3 legacy-experiments/milan-audit/make_bundle.py /tmp/goodix-milan-prototype.tar.gz
```

## Calling contract and correction to the initial audit

Windows `CheckCaptureDataRequest` sets context +0x1f0 to 1 for capture purpose 4
(enrollment), otherwise 0. Its image-processing caller passes a pointer to this
scalar as preprocessor argument two. The third argument is an optional feature
output at context +0x1f8, ending at +0x4e90: **0x4c98 bytes**, not 4096.
The vendor dispatcher explicitly supports NULL for that third argument.

The initial audit used 4096-byte placeholders for both arguments. The third
could be overwritten past its allocation in the emulated heap. That smoke
call was therefore insufficient as a buffer-safety check. It has been replaced
with the recovered purpose flag and NULL optional output. The corrected call
produces the same sine-image bytes/statistics and now checks guarded buffers.
Production code never contained the placeholder call.

The prototype checks guards around calibration, source/destination pixels,
records, flag and metrics; verifies source pixels remain unchanged; and validates
64x80 integer 12-bit input. A calibration proxy is not a measured per-unit
background; later exploratory proxy results are explicitly labeled below.
Windows callers pass zero for the final option. The prototype does the same;
it does not claim a general contract for other options or sensor profiles.

## Real-capture comparison

Run `replay.py` once a labeled dataset is available. A manifest names exactly
12 enrollment touch groups and probe
groups labeled `genuine`, `wrong`, `blank`, `noise`, or `unknown`. Each touch
group contains 1–4 **raw** P2/P5 PGMs with dimensions 64x80 and maximum 4095.
Paths are relative to the manifest. No frame path may cross touch groups or
be reused between enrollment, probes, and calibration.
The vendor method additionally requires a separate raw calibration image;
`--methods current bandpass` can run without one.

Example structure (abbreviated enrollment list; supply all 12 touches):

```json
{
  "kind": "operator-labeled-real-captures",
  "calibration": "background_raw.pgm",
  "calibration_state": "calibration_state.bin",
  "enrollment": [
    ["touch01_frame1_raw.pgm", "touch01_frame2_raw.pgm"],
    ["touch02_frame1_raw.pgm"]
  ],
  "probes": [
    {"id": "normal01", "label": "genuine", "frames": ["verify01_raw.pgm"]},
    {"id": "wrong01", "label": "wrong", "frames": ["other01_raw.pgm"]}
  ]
}
```

The calibration file must have a known acquisition source from the same unit.
`calibration_state` is optional serialized vendor state, not an image. If
provided, its length/version/CRC must be accepted by the reviewed engine;
replay does not silently discard incompatible state. Windows initializes
from its cached image base after the optional state load.
Do not relabel an average of finger captures as a no-finger calibration or use
another laptop's calibration. The existing driver's touch-gated dumps do not
by themselves establish a valid no-finger acquisition method. If calibration
is unavailable, obtain the Windows calibration artifact/acquisition details
before calling a real-unit vendor result valid.

Native Linux comparison after building the library:

```sh
python3 legacy-experiments/milan-audit/replay.py /path/to/manifest.json \
  --native-library probe-output/libgoodix-milan-probe.so --out comparison.json
```

On this Mac, omit `--native-library` to use the existing emulator. That requires
the packages in `requirements.txt`. Native replay requires only NumPy plus the
compiled probe library; it does not require Unicorn or pefile.

Replay records input hashes, engine return codes, signed scores, matched
indices, quality/overlap, selected frame attempts, template size, preprocessing
errors, and counts per operator label. It uses 12 enrollment stages and the
driver's first-frame fast path followed by the final best-frame decision.
Each identify call unpacks/deletes a fresh template, as production does.
Nonzero preprocessing returns
are recorded and excluded, including warning codes whose production handling
has not yet been validated. It does not model USB/FDT timing or prove native
hardware behavior.

## First real-capture result

ptrip7's updated archive was downloaded and compared to the earlier version;
all captures/labels are unchanged and the update adds `replay/`. The supplied
C replay reproduces all seven published rows exactly. Our corrected driver-
policy replay matches the exact labeled journal baseline, then improves from
5/10 to 7/10 genuine touches with enrollment-only FPN correction. Both reject
all ten real wrong-finger touches and the separate generated controls.

The vendor path with an enrollment-only residual estimate + 2048 completes
enrollment but matches 0/10 available genuine touches. No valid measured
background was supplied, so this is an unsuccessful proxy experiment, not a
verdict against properly calibrated vendor preprocessing. The all-data FPN
provided in the ZIP is excluded from held-out evaluation.

See [the report](../../docs/ptrip7-replay-2026-10-18.md) and
[saved native results](ptrip7-results/summary.json). `ptrip7_replay.py` reproduces
the comparison without sensor access. Production normalization is unchanged.

## Windows cache recovery

The next input can be an existing `ProgramData/Goodix/goodix.dat` from the
affected laptop's Windows installation. The standalone exporter checks the
reviewed cache format and exports only `ImageBase`, optional `CaliData`, and
metadata. No new scan or driver installation is needed. See
[helper instructions](../../tools/CALIBRATION.md) and
[the recovered contract](../../docs/windows-calibration-2026-10-18.md).

The native state save/load and manifest replay round trip pass; damaged state
is rejected. Those checks use generated inputs and do not replace the pending
affected-unit calibration comparison.

## Before changing the shipped pipeline

1. Native Linux controls using the production loader: passed on `sastapc`.
2. Establish a valid per-unit calibration source and compare actual held-out
   touches from an affected unit, with wrong-finger/blank/noise controls.
3. Check the owner's working unit for a matching regression.
4. Only then prepare a driver candidate and update the canonical normalization
   instructions if justified. Follow the timestamped hands-off/holding hardware
   protocol for that deployed candidate.
