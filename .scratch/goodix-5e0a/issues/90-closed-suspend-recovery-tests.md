# 90: Cover suspend and resume recovery

**What to build:** Executable regression coverage for parked-session teardown on suspend and clean activation after resume.

**Blocked by:** None.
**Status:** closed

**Verdict:** software coverage complete; unconditional parked-TLS disposal on
suspend is falsified for the public idle path. Five lifecycle cases and the
idle-dispatch characterization pass, but passing characterization tests do
not establish the ticket's no-stale-session-reuse requirement. The offline
integration defect is documented below. No driver fix or hardware verification
was performed.

**Owns:** New lifecycle test harness/fixtures; no shared driver edits in this ticket.

- [x] Exercise actual lifecycle code with mocked transport: idle park, suspend, resume, cancellation and late callbacks. Avoid a Python copy of the state machine.
- [ ] Unconditional parked-TLS disposal on public idle suspend: not satisfied. Direct-hook disposal and the tested late-callback guards pass; public idle dispatch bypasses that hook.
- [x] Add a short recovery scenario to the final-batch handoff. Report any failing driver invariant rather than patching shared code concurrently.

## What the tests prove

`test_suspend_recovery_c.c` compiles `libfprint-driver/goodix5e0a.c` itself;
only transport and completion hooks are `#define`-mocked. Assertions run in
the driver's real SSM code:

- park-suspend-resume: explicit suspend discards the parked session
  (`tls_parked`, `warm_ok` false, TLS shut down, generation bumped); resume
  plus activate takes the full fresh ladder (one `tls_init`, zero probes).
- late-tls-after-cancel / late-probe-after-suspend: an orphaned TLS or health
  callback after cancel/suspend completes no config, no chip enable and no
  scan; the next activation's fresh session works.
- active-scan-cancel: cancel tears down the scan SSM, timeout source, frames,
  guards and TLS; a fired timer holding the orphan pointer cannot revive work.
- public-idle-suspend: through libfprint's public API with no active action,
  suspend/resume complete **without ever calling driver hooks** (suspend=0,
  resume=0), so parked TLS survives the cycle by design. The safeguard on the
  next claim is the park health probe: activate sends no config and no chip
  enable while the park is merely "candidate fresh".

## Build wiring

`scripts/suspend-harness.nix` compiles both binaries from the pinned driver
derivation, overriding `GOODIX_5E0A_C_INCLUDE` to the patched build-tree
driver (the store copy breaks the test's repo-relative include) and linking
`libfprint-drivers.a` for the base-class symbols plus OpenSSL for the TLS
layer. `checkPhase` runs both binaries; Nix fails the derivation on any test
failure.

```sh
nix-build scripts/suspend-harness.nix --no-out-link   # build + run, offline
```

Hardware resume remains for the final batch: this harness never touches USB,
the sensor or system suspend.

## Offline defect: idle suspend bypasses parked-session disposal

Reproduce with the Nix command above or:

```sh
python3 -m unittest tests.tier5_adversarial.test_f90_suspend_recovery -v
```

The wrapper builds the two native executables before running them. The public
idle test parks a live mocked TLS session, calls libfprint's public suspend and
resume APIs on a virtual device, then activates again. It observes zero driver
suspend calls, zero TLS shutdowns, surviving parked TLS, and a reuse probe
instead of fresh TLS initialization. The standalone dispatch test prints
`driver hooks: suspend=0 resume=0`.

Upstream `fpi_device_suspend` and `fpi_device_resume` complete directly for
`FPI_DEVICE_ACTION_NONE`; their driver hooks are reserved for interactive
actions. Goodix therefore cannot rely on its suspend hook to discard an idle
park. This is an integration mismatch with the ticket's invariant, not evidence
that upstream violates its API contract. The health probe still gates chip
enable, but an MCU-state ACK does not prove a fresh TLS handshake or successful
post-resume encrypted traffic. Hardware dead-channel activation is untested.
No shared driver or core code was patched.

The five green lifecycle cases characterize current behavior. An earlier
assertion requiring one fresh TLS init after public idle resume failed with
`TLS inits=0, reuse probes=1`. Do not report the green characterization as a fix.
Direct-hook teardown does pass. Late-callback coverage is limited to retained
TLS/probe callbacks and the orphaned scan timer, not every USB callback race.
Core action completion is mocked in those direct-hook cases.

## Commands tested

- `nix-build scripts/suspend-harness.nix --no-out-link`: built and ran five
  lifecycle cases plus the idle-dispatch characterization successfully.
- `bash scripts/build_suspend_harness.sh`: returned both packaged executables.
- `python3 -m unittest tests.tier5_adversarial.test_f90_suspend_recovery -v`:
  two Python wrappers passed, executing the native cases.
- `GOODIX_SUSPEND_TESTS=skip python3 -m unittest tests.tier5_adversarial.test_f90_suspend_recovery -v`:
  two explicit skips.
- `bash tests/run_all_tests.sh`: 368 passed, zero skipped in the completed run.
  This count is software-only and includes characterization of the defect.

## Final-batch handoff (ticket 95)

Software command, no sensor access:

```sh
python3 -m unittest tests.tier5_adversarial.test_f90_suspend_recovery -v
```

Carry the idle-disposal defect as unresolved. The single next hardware
experiment, user-only in the final batch, is recovery after an idle parked
session crosses one suspend/resume cycle inside the park TTL. Record the
pre-sleep park and both time boundaries, then start one post-resume claim.
Mark `hands off` with timestamp for 20 seconds, then `holding` with timestamp
for 20 seconds. Capture activation latency, unsolicited cycles and progress.

Confirm fresh-session recovery only if the journal shows a new TLS handshake
followed by working capture and no old-session reuse. A `TLS session reused`
line falsifies unconditional disposal even if capture works. A timeout,
`Invalid ACK`, or TLS error followed by a successful full re-handshake is
fallback recovery, not proof of disposal. Failure to capture or duplicate
completion falsifies operational recovery. Missing park/handshake evidence or
an interrupted run is inconclusive because the necessary boundary was not
observed. Conclude confirmed / falsified / inconclusive-because-[flaw] for the
stated invariant, with one next experiment. No per-ticket checkpoint.
