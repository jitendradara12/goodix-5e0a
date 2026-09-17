# 92: Make native tests reproducible

**What to build:** A software-test lane that builds the native harness before running it, instead of silently skipping when a temporary binary is missing. Keep the already-landed test-summary corrections.

**Blocked by:** None.
**Status:** closed (software-confirmed; hardware not exercised)
**Owns:** Native build script, CI configuration and runner integration.

- [x] A clean checkout can build and run the native tests with documented dependencies, without stale store paths or a prebuilt temporary binary.
- [x] The required native lane fails on build errors or missing harnesses. Optional local skips stay explicit.
- [x] Run the summary fixture and test suite; report software results without hardware-verification claims.

**Done:** Reproducible command and CI lane pass. No user hardware step.


## Implementation

- `scripts/native-harness.nix` reuses the existing driver derivation's fixed
  source/hash, patch, dependencies and build options. A Nix sandbox builds and
  runs the eight simulated C invariants, then installs a RUNPATH-linked binary.
- `scripts/build_native_harness.sh` returns that executable path. No external
  `/tmp` build, prebuilt harness or handwritten store pins are used.
- `tests/run_all_tests.sh` requires the build by default, discards inherited
  executable paths, and stops on build or missing-executable failures.
  `GOODIX_NATIVE_TESTS=skip` is an explicit local opt-out, counted as a skip.
- The existing lifecycle unittest uses the exported binary and fails if it is
  missing in required mode. The existing summary calculations are unchanged.
- `.github/workflows/software-tests.yml` runs fixtures and the required suite
  on a pinned nixpkgs revision. Dependencies and commands are documented in
  `scripts/README-native-tests.md`.

## Software validation

Run on 2026-09-17 in the shared working tree:

- `bash scripts/build_native_harness.sh`: passed. A fresh sandboxed Nix build
  compiled libfprint and the native binary and ran all eight C invariants.
- `TMPDIR=/tmp/opencode bash tests/fixtures/runner_summary/run_check.sh`:
  all ten assertions passed, preserving executed/passed/skip accounting.
- `TMPDIR=/tmp/opencode bash tests/fixtures/native_lane/run_check.sh`:
  all seven checks passed. Covered build error, missing executable, ignoring
  inherited paths, successful execution, nonzero native execution, explicit
  skip, invalid mode and the real unittest's required/skip gate.
- `bash tests/run_all_tests.sh`: 342 passed, zero skipped at that snapshot.
- `NIX_PATH=nixpkgs=https://github.com/NixOS/nixpkgs/archive/b1b875982b17dabde9b4a37f3e229e74913e6db3.tar.gz bash tests/run_all_tests.sh`:
  343 passed, zero skipped. The shared tree gained another test between runs.
- `GOODIX_NATIVE_TESTS=skip bash tests/run_all_tests.sh`: 342 passed, one
  explicitly skipped native test.
- Direct execution of the native unittest with the built path passed; with a
  missing required path it failed as expected.
- `bash -n` on the build script, runner and both fixtures, and
  `git diff --check`: passed.

Predicted software signatures were confirmed: build/missing/execution failures
exit nonzero; required success executes the native test without a skip; local
opt-out reports one skip. Journal signatures are not applicable to these
software-only checks. Native tests use a fake device; source assertions of
`goodix_receive_data_cb` passed, but do not exercise USB hardware callbacks.

Logs: `/tmp/opencode/ticket92-build.log`, `ticket92-ci-build.log`,
`ticket92-suite.log`, `ticket92-ci-suite.log`, `ticket92-optional-suite.log`.

## Limits and verdict

Software-confirmed. The build ran from fresh upstream source in the Nix
sandbox, but no separate clean Git checkout or empty Nix store was tested.
The pinned CI command passed locally; no hosted GitHub Actions run was
observed. Branch protection is external and must select the required job.
The shared tree contains other agents' changes and optional external developer
trees, so whole-suite counts can change and a clean checkout can report those
external-tree skips. No hardware, sudo, fprintd, suspend or deployment actions
were performed. Next check: observe the hosted required-native job after these
changes are published.
