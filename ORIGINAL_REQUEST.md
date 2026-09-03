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
