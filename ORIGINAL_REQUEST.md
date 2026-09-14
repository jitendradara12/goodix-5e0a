# Original User Request

## Initial Request — 2026-09-03T01:45:52+05:30

# Teamwork Project: Goodix 27c6:5e0a Fingerprint Sensor Driver for Linux / NixOS

Requested team: Full team (comprehensive multi-agent swarm for root-cause reverse engineering, architecture refactoring, and daemon integration)

Build a production-grade, modular, and reliable Linux driver for the Goodix 27c6:5e0a fingerprint sensor in libfprint and NixOS that eliminates all loops, hangs, and false-triggers, solving the root cause of hardware finger detection and state lifecycle management from first principles under the Ponytail architecture standard.

Working directory: /home/sastauser/code/temp/goodix
Integrity mode: development

## Verification Resources
- Working Python prototype scripts that successfully communicate with and capture from the hardware MCU:
  - `/home/sastauser/code/temp/goodix/test_touch_sensor.py` (proven hardware FDT touch interrupt test)
  - `/home/sastauser/code/temp/goodix/scan_finger.py` (proven TLS PSK handshake and frame decryption)
  - `/home/sastauser/code/temp/goodix/test_press_and_capture.py` (sensor register configuration `0x022c`)
- Reference driver trees:
  - `/tmp/libfprint-goodix` (active driver build tree with Meson/Ninja)
  - Base class reference: `libfprint/drivers/goodixtls/goodix5xx.c`, `goodix5xx.h`
  - Peer driver reference: `libfprint/drivers/goodixtls/goodix511.c`
- Local hardware: Goodix USB device `27c6:5e0a` on Realme Book / Slim.

## Requirements

### R1. Root-Cause Finger Touch & Release Detection (Hardware FDT)
Replace all flawed software noise polling and arbitrary threshold heuristics with the sensor MCU's native hardware FDT (Finger Detection Threshold) interrupts (`0x32` FDT DOWN and `0x34` FDT UP). The driver must strictly block until a real physical touch occurs before capturing an image, and strictly block until physical finger release occurs before transitioning states.

### R2. Modular Base-Class Architecture (Ponytail Standard)
Adhere strictly to the Ponytail philosophy: delete ad-hoc abstractions, redundant state machines, and polling timers. Refactor `goodix5e0a` so that it purely derives from the `FpiDeviceGoodixTls5xx` base class, supplying only hardware-specific configuration payloads, endpoints, and pixel conversion routines, while the base class drives the session lifecycle.

### R3. Flawless Multi-Run Session Lifecycle & USB Recovery
The driver must handle device activation and deactivation cleanly. Every verification or PAM authentication attempt must execute without packet collisions, protocol desync, or `Command timed out: 0xa2` failures. USB read loops must be cancelled and reset reliably between consecutive invocations.

### R4. NixOS Flake & System Integration
Deliver the final tested driver as a clean, minimal patch (`0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`) that integrates into the user's NixOS flake configuration at `/home/sastauser/NixOS-Hyprland/modules/goodix/`.

## Acceptance Criteria

### Sensor Authentication & Behavior
- [ ] `fprintd-enroll` does NOT progress on empty air; it advances only when a real physical finger is placed and lifted across all stages.
- [ ] `fprintd-verify` succeeds with a genuine match against enrolled fingers and fails against non-matching fingers or air.
- [ ] Back-to-back verification calls (`fprintd-verify` run multiple times consecutively) execute reliably without timeouts, hangs, or requiring daemon restarts.

### Build & Architectural Integrity
- [ ] Meson / Ninja build compiles with 0 errors and 0 warnings.
- [ ] Clean hermetic package build under Nix (`nix-build` / flake evaluation).
- [ ] No ad-hoc polling sleep loops or synthetic background noise thresholds in the driver.

## Follow-up — 2026-09-04T21:22:13Z

Harden the Goodix 27c6:5e0a Linux fingerprint driver so it works reliably for everyday use on NixOS, delivering consistent first-touch biometric verification and robust PAM/sudo authentication without D-Bus claim lockups or daemon hangs.

Working directory: /home/sastauser/code/temp/goodix
Integrity mode: development

## Requirements

### R1. Biometric Verification Consistency
Elevate verification matching consistency so that genuine finger touches match reliably on the first or second attempt across varied finger positions and contact pressures, eliminating minutiae starvation and false rejections.

### R2. Robust PAM & Sudo Lifecycle
Eliminate D-Bus device claim deadlocks (`Device was already claimed`), ensure instant responsiveness to authentication requests (e.g. `sudo`, `hyprlock`, login), and ensure that cancelled or interrupted verification operations release the device cleanly without requiring daemon restarts.

### R3. Verification Latency & Touch Pacing
Optimize the polling and image processing loop so that verification completes with low latency (< 300ms from physical finger touch to authentication signal) without command collisions or timeouts.

### R4. Automated Verification Harness & Documentation
Provide an automated test suite and clear verification instructions that allow regression-testing biometric match scores, D-Bus state transitions, and packaging on NixOS.

## Acceptance Criteria

### Biometric Matching
- [ ] At least 5 consecutive `fprintd-verify` attempts with the enrolled finger succeed with `Verify result: verify-match (done)`.
- [ ] Bozorth3 match scores consistently clear the match threshold without tripping floor aborts on weak prints.

### PAM & Sudo Usability
- [ ] `sudo` authentication via fingerprint succeeds repeatedly in terminal sessions without hanging or reporting `Device was already claimed`.
- [ ] Interrupting a verification request (`Ctrl+C` or prompt timeout) releases the device cleanly, allowing immediate subsequent claims.

### System Stability
- [ ] Driver builds cleanly via Ninja and passes full Nix package build (`callPackage ./libfprint-goodix.nix {}`).
- [ ] `fprintd.service` stays cleanly active and responsive without entering `stop-sigterm` or hung deactivation states.

## Follow-up — 2026-09-05T17:25:17Z

Prepare the Goodix 27c6:5e0a fingerprint driver for upstream merge into freedesktop.org/libfprint/libfprint master, implementing umockdev replay tests and suspend/resume power management while preserving downstream stability.

Working directory: /home/sastauser/code/temp/goodix
Integrity mode: development

References:
- docs/UPSTREAM.md (upstream requirements & submission checklist)
- .scratch/goodix-5e0a/issues/36-ready-for-agent-upstream-rebase-and-umockdev-capture.md (active workfront ticket)

## Requirements

### R1. Upstream Master Tree Placement & Build Cleanliness
Rebase and integrate the Goodix 5e0a driver sources directly into an upstream libfprint master tree checkout (under libfprint/drivers/goodixtls/), properly registering the driver in top-level and library meson.build. The build must succeed with meson setup --werror under the upstream warning profile, and pass formatting validation via scripts/uncrustify.sh.

### R2. Automated umockdev Replay Harness (FP_DEVICE_EMULATION=1)
Implement the standard upstream test directory (tests/goodixtls5e0a/) containing device attributes, a recorded capture.ioctl replay trace, and a reference capture.png. Wire it into tests/meson.build so that meson test executes the complete emulation test under FP_DEVICE_EMULATION=1 without physical hardware access.

### R3. Power Management Lifecycle (.suspend / .resume)
Implement device class .suspend and .resume vfunctions in the driver. Ensure that entering system suspend cleanly terminates active USB transfers and teardown state, and resuming successfully re-primes the chip and resets the TLS session state machine without wedging PAM or authorization claims.

### R4. Downstream Preservation & Regression Guard
Ensure all changes remain 100% backward-compatible with the downstream NixOS flake packaging (libfprint-goodix.nix), and ensure the existing 400-test master test suite (tests/run_all_tests.sh) remains completely passing.

## Acceptance Criteria

### Upstream Tree Compilation & Style
- [ ] Upstream checkout with driver patch configures and builds cleanly with meson setup build -Ddrivers=default,goodixtls5e0a --werror and ninja -C build.
- [ ] scripts/uncrustify.sh produces zero diff on all modified and newly created driver files.
- [ ] Driver implements FpImageDevice vfunctions conforming to upstream libfprint/fpi-image-device.h.

### Replay & Emulation Verification
- [ ] tests/goodixtls5e0a/ contains valid device, capture.ioctl, and capture.png test fixtures.
- [ ] Running meson test -C build under FP_DEVICE_EMULATION=1 executes the goodixtls5e0a test suite to completion with an exit code of 0.

### Power Management & Lifecycle Hooks
- [ ] Driver class exposes .suspend and .resume function pointers.
- [ ] Suspend callback cancels in-flight transfers and frees pending state machines without memory leaks.
- [ ] Resume callback cleanly transitions through device re-activation without requiring daemon restart.

### Regression Prevention
- [ ] Downstream test suite runner (tests/run_all_tests.sh) passes 400/400 tests across Tiers 1–5 with zero errors.
- [ ] nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}' completes successfully.

## Follow-up — 2026-09-11T08:20:27Z

Resolve open tickets #62, #63, and #64 in the Goodix repository by implementing the exact two-hash Goodix WhiteBox algorithm, hardening decrypt error paths, and designing modular test hooks to make verification and regression testing hermetic and robust.

Working directory: /home/sastauser/code/temp/goodix
Integrity mode: development

## Reference Material
- Algorithm specification & known test vectors: /tmp/libfprint/RE_WHITEBOX_EXACT.md
- Reference implementations: /tmp/libfprint/whitebox_encrypt.py and /tmp/libfprint/whitebox_crack.py
- Open ticket specs:
  - .scratch/goodix-5e0a/issues/62-ready-for-agent-whitebox-decrypt-guards.md
  - .scratch/goodix-5e0a/issues/63-ready-for-agent-whitebox-intermediate-vectors.md
  - .scratch/goodix-5e0a/issues/64-ready-for-agent-whitebox-multisize-roundtrip.md

## Requirements

### R1. WhiteBox Decrypt Hardening & Input Guards (Ticket 62)
Harden `sec_white_decrypt` in `experiments/goodix_whitebox.py`:
- Reject ciphertext whose length is not a multiple of 16 (`len(ct) % 16 != 0`) with a `ValueError` before decryption.
- Remove redundant dead check that compares prefix to its own slice source.
- Provide actionable hex-formatted mismatch messages on prefix verification failures (`expected {hex}, got {hex}`).

### R2. Intermediate Vector Pinning & Exact Two-Hash Derivation (Ticket 63)
Align `experiments/goodix_whitebox.py` with the authoritative two-hash key derivation specification in `RE_WHITEBOX_EXACT.md`. Pin intermediate vectors (`hash1`, `prefix`, `hash2`, `aes_key`, `iv`) in tests to ensure single-hash regressions cannot pass undetected.

### R3. Multi-Size Round-Trip Test Coverage (Ticket 64)
Expand round-trip encryption/decryption validation in `experiments/goodix_whitebox.py` and `tests/tier1_feature/test_f28_whitebox.py` to cover inputs of sizes 16, 48, and 64 bytes in addition to canonical 32-byte PSKs, explicitly verifying PKCS#7 padding boundaries and total wire lengths (80, 112, 128 bytes).

### R4. Modular Crypto Test Hooks for Ease of Testing
Structure the WhiteBox crypto derivation into inspectable, modular sub-steps (or dedicated helper functions) so that each stage—hash1 computation, byte-15 mutation, hash2 key derivation, CBC encryption, and HMAC authentication—can be individually unit-tested and verified in isolation.

### R5. Ticket Status Tracking
Update the filenames and headers of the three tickets in `.scratch/goodix-5e0a/issues/` following repo ticket rules (moving from `ready-for-agent` to the appropriate verified/closed status once verified).

## Acceptance Criteria

### Correctness & Vector Verification
- [x] 32-byte all-zero KAT produces exact intermediate and final values specified in `RE_WHITEBOX_EXACT.md` (hash1 `ec35ae3a...`, prefix `...cc0`, hash2 `b7e7f234...`, ciphertext, HMAC, and 96-byte output).
- [x] Canonical PSK round-trip succeeds across all tested sizes (16B, 32B, 48B, 64B) with correct wire lengths (80B, 96B, 112B, 128B).

### Error Path Hardening
- [x] Truncated payloads (<96B for 32B input) raise `ValueError`.
- [x] Ciphertext with invalid block size (`len(ct) % 16 != 0`) raises `ValueError` before invoking cipher decryption.
- [x] Bit-flipped ciphertext or tampered HMAC raises `ValueError` ("HMAC verification failed").
- [x] Corrupted prefix raises `ValueError` with format containing expected and actual hex strings.

### Test Suites & Hermeticity
- [x] `python3 -m unittest tests.tier1_feature.test_f28_whitebox` passes cleanly with all new test cases.
- [x] `python3 experiments/goodix_whitebox.py` runs standalone validation and passes all assertions.
- [ ] No regressions introduced into existing unit tests in `tests.tier1_feature`.

## Follow-up — 2026-09-11T11:16:09Z

Comprehensive C driver audit and architectural review of the Goodix 5e0a fingerprint driver under ponytail principles, focusing on eliminating accidental complexity and solving the biometric enrollment coverage/verification retry gap compared to Windows without breaking existing hardware invariants.

Working directory: /home/sastauser/code/temp/goodix
Integrity mode: development

## Background & Invariants

- **Current Status**: The C driver (`libfprint-driver/`) is stable and functional on hardware, passing all 448 hermetic tests.
- **Accuracy Gap**: Windows captures a large composite fingertip representation via proprietary spatial stitching (`MergeFeature` / `enrolAddImage`), whereas Linux/fprintd enrolls a smaller single-touch patch across 5 stages, leading to verification retries (1–2 extra taps needed when finger placement varies).
- **Hard Invariants (DO NOT BREAK)**:
  1. `0x32 FDT_DOWN` must maintain timeout 0 (blocking capacitive interrupt, never a timer).
  2. `0x34 FDT_UP` must remain finite (2000ms guard / 5000ms normal) with re-issue on timeout.
  3. Deactivation and TLS park lifecycle must preserve cross-claim TTL state (guard, park, warm) on idle return; reset only on destroy.
  4. `CANCELLED` errors must never re-issue or resurrect SSMs.
  5. Host matching relies on in-tree NBIS/Bozorth3; no speculative external matcher replacements.
  6. All existing 448 unit tests must remain 100% passing.

## Requirements

### R1. C Driver Audit & Ponytail Simplification
Audit all C source files in `libfprint-driver/` (`goodix5e0a.c`, `goodix5xx.c`, `goodix.c`, `goodix_proto.c`, `goodixtls.c`, `goodix511.c`):
- Apply the Ponytail ladder: identify dead code, redundant allocations, speculative abstractions, and unused helpers.
- Propose surgical simplifications and deletions over additions.
- Ensure all critical rationale comments and hardware invariants are strictly preserved.

### R2. Biometric Accuracy Architecture & Windows Gap Analysis
Analyze and evaluate architectural solutions to resolve the enrollment coverage and verification retry problem:
- **Best-of-N during Enrollment**: Investigate removing the enrollment exclusion (`goodix5e0a.c:1036`) so enrollment touches also bank 3 frames and pick the highest minutiae frame.
- **Stage Count vs FAR Calibration**: Re-evaluate `nr_enroll_stages` (reduced from 12 to 5 in Ticket 43 when threshold was 11) now that Bozorth threshold is pinned to 14. Calculate cumulative FAR impact across typical galleries ($K = \text{fingers} \times \text{stages}$) to identify if stages can safely increase to improve finger coverage.
- **Multi-Frame Canvas Stitching Feasibility**: Investigate whether successive enrollment touches can be registered/stitched into an expanded 2D canvas prior to NBIS feature extraction (emulating Windows `enrolAddImage`), or whether multi-stage gallery matching is the preferred libfprint paradigm.
- **Image Preprocessing & Normalization**: Review `process_raw_frame` (3x3 local-mean residual, contrast gain, bilinear 2x upscale, ppmm calculation) for signal-to-noise ratio and minutiae extraction yield improvements on real raw captures.

### R3. Offline Benchmark & Empirical Validation
- Evaluate proposed accuracy changes against real frame captures in `experiments/` (e.g. `experiments/fingerprint.pgm`, `benchmark_minutiae_matrix.c`, etc.).
- Measure genuine match scores, minutiae yield, and impostor rejection margins under the candidate configurations.
- Verify that no proposed change induces PAM deadlocks or latency spikes.

### R4. Actionable Audit Report & Minimal PoC Patches
- Deliver a structured audit report detailing code simplification opportunities, biometric accuracy findings, and mathematical FAR/FRR tradeoffs.
- Provide non-breaking, surgical proof-of-concept diffs ready for review, accompanied by corresponding unit tests.

## Acceptance Criteria

### Invariants & Safety
- [ ] Zero regression on the test suite: `python3 -m unittest tests.tier1_feature.test_f47_verify_retry_release_guard` and related tests pass.
- [ ] No changes to the `0x32` timeout 0, `0x34` guard loop, or TLS park/warm lifecycle.
- [ ] Any simplified code retains clear explanatory comments documenting hardware-enforced behavior.

### Accuracy Analysis & Feasibility
- [ ] Concrete mathematical analysis of gallery size $K$ vs FAR at `bz3_threshold = 14`, detailing the optimal enrollment stage count.
- [ ] Benchmarked minutiae count and Bozorth score comparison demonstrating the effect of Best-of-N enrollment and/or image preprocessing adjustments.
- [ ] Clear technical assessment on the feasibility and complexity of driver-level frame stitching vs multi-template expansion within libfprint.

### Ponytail Review Quality
- [ ] Specific list of safe code deletions and simplifications across `libfprint-driver/`.
- [ ] Shortest working diffs provided with zero unrequested abstractions or scaffolding.

## Follow-up — 2026-09-14T14:32:52Z

Requested team: Full team (comprehensive multi-agent swarm for root-cause reverse engineering, architecture refactoring, and daemon integration)

Execute a comprehensive full-stack refactoring and cleanup of the Goodix 27c6:5e0a Linux fingerprint driver repository, stripping obsolete legacy NBIS minutiae code in favor of the vendor Milan matching engine, streamlining the test suite, reorganizing experimental clutter into legacy-experiments/, and regenerating the unified NixOS driver patch.

Working directory: /home/sastauser/code/temp/goodix
Integrity mode: development

## Verification Resources
- Working driver build tree: `/tmp/libfprint-goodix/build`
- Ninja compiler binary: `/nix/store/6ji6bq0si2j8ibdrxqgcmh1cw0wmdiyk-ninja-1.13.2/bin/ninja -C /tmp/libfprint-goodix/build libfprint/libfprint-drivers.a libfprint/libfprint-2.so.2.0.0`
- Hermetic Nix package build: `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'`
- Hardware invariants & rules: `AGENTS.md` (0x32 FDT_DOWN timeout 0, 0x34 FDT_UP finite timeout with retry guard, CANCELLED never re-issues, cross-claim TTLs preserved)
- Active ticket and history: `.scratch/goodix-5e0a/issues/` (retained intact)
- Vendor matching DLL: `windows_driver/GoodixEngineAdapter.dll` (already positioned)

## Requirements

### R1. Commit Fully to Milan Biometric Engine & Strip Minutiae Slop
Refactor `libfprint-driver/goodix5e0a.c` and `libfprint-driver/goodix5e0a.h` to rely exclusively on the Milan engine (`goodix_milan.c` + `GoodixEngineAdapter.dll`). Strip out all legacy NBIS minutiae extraction (`goodix5e0a_count_minutiae`), `#include "nbis/include/lfs.h"`, minutiae quality floors (`GOODIX_5E0A_ENROLL_MIN_MINUTIAE`), and minutiae tiebreakers. Simplify burst banking so frames are judged directly by Milan quality and contrast range without intermediate 128x160 `FpImage` allocations. Maintain all AGENTS.md hardware invariants (0x32 timeout 0, 0x34 guard/timeout, cross-claim TTLs).

### R2. Reorganize Repository Clutter & Archive Non-Essential Binaries
Consolidate peripheral clutter:
- Move `experiments/` to `legacy-experiments/` and ensure all scripts and dumps remain tracked in git.
- Keep `windows_driver/GoodixEngineAdapter.dll` for driver packaging; archive all other unused Windows binaries/EXEs/INFs (6.5 MB) into `legacy-experiments/windows_driver/`.
- Preserve `.scratch/goodix-5e0a/issues/` intact for historical and hardware verification context.

### R3. Streamline Automated Test Suite
Clean up `tests/` by removing obsolete Bozorth tests (e.g. `test_f24_biometric_bozorth.py`), rigid ticket filename assertions (`test_f26_ticket_filename_status.py`), and redundant synthetic boundary permutation tiers. Consolidate and maintain high-signal tests covering protocol packet encoding/decoding (`CMD_NOP`, `0x32`, `0x34`), TLS handshake, Milan template management, and state machine lifecycle. Ensure `bash tests/run_all_tests.sh` runs cleanly.

### R4. Patch Synchronization & Driver Compilation
Sync all refactored C source files from `libfprint-driver/` into the `/tmp/libfprint-goodix` build tree, compile cleanly via Ninja with 0 errors, and regenerate `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` to match the cleaned driver source. Verify that `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'` succeeds.

## Acceptance Criteria

### Build & Driver Cleanliness
- [ ] Ninja build succeeds cleanly: `/nix/store/6ji6bq0si2j8ibdrxqgcmh1cw0wmdiyk-ninja-1.13.2/bin/ninja -C /tmp/libfprint-goodix/build libfprint/libfprint-drivers.a libfprint/libfprint-2.so.2.0.0` exits 0 with no compiler warnings.
- [ ] Zero references to `nbis/include/lfs.h` or `goodix5e0a_count_minutiae` in `libfprint-driver/goodix5e0a.c`.
- [ ] Unified patch `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` accurately reflects the refactored code and applies cleanly.
- [ ] Nix package builds successfully: `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'`.

### Repository Structure
- [ ] `legacy-experiments/` contains the moved experiments and archives; git status shows clean renames with no untracked dumps.
- [ ] `windows_driver/` contains only `GoodixEngineAdapter.dll`.
- [ ] `.scratch/goodix-5e0a/issues/` is preserved.

### Test Suite Execution
- [ ] Streamlined test suite passes via `bash tests/run_all_tests.sh` with 0 failures and 0 errors.

