# 73 — Libfprint FpDevice Driver Integration with Milan Engine

**What to build:**
Refactor `libfprint-driver/goodix5e0a.c` to integrate the in-process Milan engine loader verified in Tickets 71 and 72.
Transition the driver class hierarchy from `FP_TYPE_IMAGE_DEVICE` to `FP_TYPE_DEVICE` (matching the architecture used by `ft9201.c` and vendor Match-on-Chip drivers), replacing Bozorth3 minutiae matching with Milan template stitching and verification.

**Blocked by:** 72 (closed).

**Status:** closed (verdict: confirmed)

---

## 1. Architecture Transition

1. **`FP_TYPE_DEVICE` Transition**:
   - Switched `FpiDeviceGoodixTls` base class from `FP_TYPE_IMAGE_DEVICE` to `FP_TYPE_DEVICE`.
   - Replaced host Bozorth3 minutiae matching (`fpi_print_bz3_match`) with direct calls into Goodix Milan biometric engine (`GoodixEngineAdapter.dll`).
   - Defined `dev_class->open`, `dev_class->close`, `dev_class->enroll`, `dev_class->verify`, and `dev_class->cancel` on `FpDeviceClass`.
2. **In-Process Milan PE Loader (`libfprint-driver/goodix_milan.c`)**:
   - `memfd_create` W^X anonymous mappings for PE sections.
   - Minimal Windows `%gs` TEB emulation via `arch_prctl(ARCH_SET_GS)`.
   - Comprehensive Win32/UCRT shim runtime (191 API symbols including synchronization, memory, CRT strings/math, and networking).
   - Direct export resolution for: `ppp_param_init`, `enrolStartEx`, `enrolAddImage`, `enrolGetTemplate`, `templatePack`, `templateUnPack`, `identifyImage`, `templateDelete`, and `enrolFinish`.
3. **Multi-Impression Enrollment Pipeline**:
   - Configured `dev_class->nr_enroll_stages = 8`.
   - Each touch normalizes raw $64 \times 80$ frames with 3x3 local contrast filtering.
   - Impressions passed to `goodix_milan_enroll_add_image`.
   - Upon completing all 8 stages, `goodix_milan_enroll_commit` serializes the composite template (~23 KB) via `templatePack`.
   - Stored in `FpPrint` as `FPI_PRINT_RAW`.
4. **Verification Pipeline**:
   - Captured probe frame normalized and passed to `goodix_milan_verify_image` against stored `FPI_PRINT_RAW` composite template.
   - Engine evaluates dynamic stitch score (threshold 50); reports `FPI_MATCH_SUCCESS` or `FPI_MATCH_FAIL` directly to `fpi_device_verify_report`.

---

## 2. Invariants & Guardrails (AGENTS.md)

- `0x32` FDT_DOWN timeout is strictly 0 (blocking wait).
- `0x34` FDT_UP finite timeout (2000ms guard / 5000ms normal) with re-issue loop preserved.
- Park cross-claim TTLs (guard 2s, park 30s, warm 60s) survive idle park.
- `CANCELLED` never re-issues.
- Zero W^X violations.

---

## 3. Acceptance Criteria & Verification

- [x] Driver compiles cleanly with ninja in `/tmp/libfprint-goodix/build`:
  ```
  [1/8] Compiling C object libfprint/libfprint-drivers.a.p/drivers_goodixtls_goodixtls.c.o
  ...
  [6/8] Compiling C object libfprint/libfprint-drivers.a.p/drivers_goodixtls_goodix_milan.c.o
  [7/8] Linking static target libfprint/libfprint-drivers.a
  [8/8] Linking target libfprint/libfprint-2.so.2.0.0
  ```
- [x] Master E2E Test Suite (Tiers 1-5, all 459 tests) passes 100%:
  ```
  Total Tests Passed: 459
  Total Tests Failed: 0
  Total Tests Skipped (env-gated): 1
  Total Execution Time: 7s
  ALL TEST TIERS PASSED PERFECTLY!
  ```
- [x] Unified patch `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` regenerated and byte-for-byte synchronized with `/home/sastauser/NixOS-Hyprland/modules/goodix/`:
  - SHA256: `fc86167bfb2a6ac7f4db88e9e998d5579b1da62054a35b5a6633c1c2e40e7265`
- [x] Full hermetic package build succeeds via `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'`:
  - Produced output: `/nix/store/2h7a4sav1y9i3yhcs08c5i2afm7fyykg-libfprint-goodix-1.94.5-goodixtls-5e0a`

---

## 4. Next Step

Proceed to Ticket 74 (`74-ready-for-agent-hardware-deployment.md`) for NixOS package integration of the DLL asset and deployed hardware enrollment & verification protocol.
