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

At initial packaging, no hardware fingerprint run, installation, fprintd restart
or public message had occurred. Subsequent hardware evidence is recorded below.
No additional calibration export is needed for this experiment.

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

## Owner regression run, 2026-10-19

- **Hardware run:** verified on owner's x86-64 Linux laptop via `tools/test-native-raster.sh`.
- **Bundle:** `/var/tmp/goodix-5e0a-reports/goodix-test-e68e08c4aed3cc40.zip` (SHA-256 in report).
- **Phase 1 (hands-off 20s):** silent, `hands_off_activity: false`.
- **Phase 2 (holding 20s):** `holding_advances: 1`, prompt capture, clean advance.
- **Enrollment:** 12 touches completed normally.
- **Verification:** 5/5 genuine matches (`pts=61`, `pts=74`, optimistic fast-path on frame 1), 0/5 wrong-finger matches (`pts=0` rejection on all 5). Total 10/10 correct decisions.
- **Cleanup:** isolated storage unmounted, normal service restored cleanly.
- **Verdict:** confirmed (owner regression control passed with zero regressions). Single next experiment remains ptrip7's hardware verification on the affected unit.

The [saved session report](../../../legacy-experiments/milan-audit/calibration-results-2026-10-19/owner-hardware-session.json)
was independently read from the ZIP over SSH. It confirms isolation, restoration,
all ten labeled decisions, no hands-off activity and one holding advance.
The five genuine scores in the projected journal were 41, 45, 61, 74 and 74;
all five wrong-finger decisions were match=0, pts=0.

## ptrip7 setup failure and runner correction, 2026-10-19

[ptrip7's report](https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6255286093)
describes the same patch/revision, but Mint's `/run` is mounted `noexec`.
The daemon exited 127 while mapping the staged libfprint, before isolation
verification or sensor testing. Normal service restoration succeeded.

**Verdict:** inconclusive-because-noexec-before-sensor-test. This result does not
confirm or falsify the image-processing experiment.

The corrected runner stages only the driver under a root-only, per-session
`/var/lib/goodix-5e0a-experiment-<id>` directory. Runtime recovery state and
private prints remain under `/run`. Before changing the service, it tests an
executable mapping without running library code. Restoration removes the
external driver directory, checking its recorded path and ownership marker.
Recovery of older `/run`-only manifests remains supported. The candidate patch
and its processing parameters are unchanged.

Thirteen failure-injection tests pass on macOS and Linux. An actual isolated
Linux mount-namespace test reproduced denial on a `noexec` tmpfs and successful
mapping of the identical candidate library under `/var/lib`. Normal fprintd PID,
active state and start timestamp were unchanged; no sensor code was executed.
[Mapping proof](../../../legacy-experiments/milan-audit/calibration-results-2026-10-19/runner-noexec-proof.json).

**Single next experiment:** ptrip7 reruns the guided hardware session with this
runner correction. Predict the daemon starts and isolation verifies, then the
existing confirm/falsify signatures above apply. If executable mapping remains
blocked, setup must abort before any service change: inconclusive-because-host-execution-policy.
Owner regression is complete; no repeat is requested from the owner or Jet-Soup.
