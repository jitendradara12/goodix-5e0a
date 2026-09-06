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
