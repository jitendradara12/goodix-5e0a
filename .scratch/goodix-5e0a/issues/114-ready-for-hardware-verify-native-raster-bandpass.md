# 114: Opt-in native-raster/band-pass hardware verification

**Status:** ready-for-hardware-verify

**Predecessor:** [113](113-superseded-vendor-preprocessing-prototype.md).

**Evidence:** [Calibration/raster report](../../../docs/calibration-raster-2026-10-19.md)
and [actual C candidate](../../../legacy-experiments/milan-audit/native-raster-candidate.patch).

Confirmed offline: 10/10 genuine touches, 0/10 wrong-finger matches, all three
synthetic negative controls rejected, and 82/96 held-out frame matches.
The actual C normalization/quality/enroll/verify/gallery path reproduces the
diagnostic runner. The public raster/default path remains 64x80, 3x3 gain1.5.
The full isolated libfprint build passes; [build record](../../../legacy-experiments/milan-audit/calibration-results-2026-10-19/build.json).
GOODIX_5E0A_NATIVE_RASTER=1 opts into band-pass normalization and an 80x64
engine-facing transpose. Capture settings and target 12 are unchanged.

## Single next experiment

Fresh 12-touch enrollment and labeled verify on ptrip7's affected unit using
the opt-in candidate; follow with the owner's working unit as the regression
control. Preserve existing working templates with a separate test account or
unused test enrollment. Do not mix old/new processing templates. Confirm the
environment flag is present in the actual driver process, not just its client.

1. Record **hands off + timestamp**, active for 20s. Predict silence: no
   spurious captures/advances or repeated activation cycles.
2. Record **holding + timestamp**, steady for 20s. Predict prompt capture and
   quality/overlap, then a positive genuine decision or one enrollment advance
   followed by waiting for release. Record latency and any repeated cycles.
3. Finish 12 distinct enrollment placements; record labeled genuine and wrong
   attempts with the journal. This is the first deployed check, not a replay.

**Confirm journal signatures:** expected phases above, normal enrollment
completion, Milan match=1 with positive pts on genuine touches, match=0 for
wrong-finger attempts, and no regression on the owner's unit.

**Falsify signatures:** valid fresh enrollment still repeatedly no-matches,
wrong-finger matches, spurious hands-off activity, repeated hold cycles, or
regression on the previously working unit.

**Inconclusive-because-[flaw]:** wrong build, missing flag, mixed old/new
templates, unlabeled probes, or absent hands-off/holding phases. Conclude only
confirmed / falsified / inconclusive-because-[flaw], plus one next experiment.

No hardware fingerprint run, installation, fprintd restart or public message
has occurred. No additional calibration export is needed for this experiment.

## Packaged contributor session

[Hardware-test instructions](../../../docs/HARDWARE_TEST.md): one normal-user
entry point builds privately, asks for sudo only for the runtime session, binds
private storage over the daemon's print directory, verifies the loaded library
and live mount, guides both protocol phases plus fresh enrollment and labeled
verification, and returns one sanitized ZIP. It restores the prior service
state and removes its own override. An independent 30-minute recovery timer
and explicit --restore handle interrupted sessions.

Ten failure-injection tests and seven calibration tests pass. The actual
storage namespace probe passes without using fprintd or USB; normal fprintd
PID, start time and state remain unchanged. The owner explicitly authorized
one workbench commit/push to PR #13. Status stays ready-for-hardware-verify;
neither simulated cleanup tests nor a successful build count as verification.
