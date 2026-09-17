# 90: Cover suspend and resume recovery

**What to build:** Executable regression coverage for parked-session teardown on suspend and clean activation after resume.

**Blocked by:** None.
**Status:** closed

**Verdict:** confirmed, software-only. All five lifecycle harness tests and the
idle-dispatch reproducer pass against the real compiled driver (5 `ok`, 0
failures, 2026-09-17 build log). No failing invariant was found, so no defect
report is needed. This is not hardware verification of resume behavior.

**Owns:** New lifecycle test harness/fixtures; no shared driver edits in this ticket.

- [x] Exercise actual lifecycle code with mocked transport: idle park, suspend, resume, cancellation and late callbacks. Avoid a Python copy of the state machine.
- [x] Check that suspend discards parked TLS, late callbacks cannot revive old work, and the next claim can initialize a fresh session.
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

## Final-batch handoff (ticket 95)

```sh
nix-build scripts/suspend-harness.nix --no-out-link   # must pass before sampling
```

Optional live check during the batch, user-only, after one suspend/resume
cycle: `bash scripts/verify-ticket88.sh 90` (its journal must show a fresh
handshake, no stale reuse, no transport errors).
