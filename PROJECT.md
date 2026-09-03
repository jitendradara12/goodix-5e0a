# Project: Goodix 27c6:5e0a Fingerprint Sensor Driver

## Architecture
- **Layered Architecture**:
  - `fprintd` / PAM Services (`sudo`, `hyprlock`, `swaylock`, `login`, `sddm`) -> D-Bus IPC
  - `libfprint` C core (`FpImageDevice` / `FpiDeviceGoodixTls5xx` base class)
  - `goodix5e0a` driver: Pure subclass of `FpiDeviceGoodixTls5xx` (Ponytail standard: minimal C code ~290 LOC, no custom polling loops or redundant state machines)
  - Hardware transport: USB Bulk (EP 0x01 OUT, EP 0x83 IN) to Goodix 27c6:5e0a MCU (ChicagoH / GF5288 / 52xD)
- **Key Protocol Mechanics**:
  - Hardware FDT interrupts (`0x32` FDT DOWN, `0x34` FDT UP) with `timeout_ms = 0` (blocking capacitive interrupt)
  - TLS 1.2 PSK (`PSK-AES128-CBC-SHA256`) encryption of raw 12-bit sensor frames
  - 12-bit pixel unpacking (7,680 bytes -> 5,120 pixels, 80x64 raw) and bilinear demosaicing to 160x128 8-bit grayscale
  - Non-blocking socket teardown (`SHUT_RDWR`) and cancellable USB read loops (`g_cancellable_cancel`) to guarantee multi-run PAM stability and eliminate `0xa2` timeouts.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | USB Interface & Endpoint Configuration | Claim interface 0, EP 0x01 OUT (64B chunked), EP 0x83 IN (64KB buffer) | M2 | explorer_hardware_1, explorer_libfprint_1 |
| 2 | NOP Buffer Flush & Reset | Send CMD 0x00 and CMD 0xa2 to drain stale USB replies | M3 | explorer_hardware_1, explorer_nixos_1 |
| 3 | Read Register & Chip ID | Read register 0x0000 (returns 4 bytes chip identifier) | M1 | explorer_hardware_1 |
| 4 | Read OTP & Firmware Query | Query CMD 0xa6 OTP and CMD 0xa8 ASCII FW string (`GFUSB_GM168SEC_APP_10036`) | M2 | explorer_hardware_1, explorer_libfprint_1 |
| 5 | Preset PSK Status Read | Verify PSK flags (`0xbb020001`) via CMD 0xe4 | M2 | explorer_hardware_1, explorer_libfprint_1 |
| 6 | TLS 1.2 PSK Handshake | Establish PSK-AES128-CBC-SHA256 session using 32-byte key via CMD 0xd0/0xd4 | M2 | explorer_hardware_1, explorer_libfprint_1 |
| 7 | MCU Config Upload (256B) | Upload 256-byte `CONFIG_52XD` payload via CMD 0x90 | M2 | explorer_hardware_1, explorer_libfprint_1 |
| 8 | Sensor Register 0x022c Config | Configure analog frontend gain/exposure (`\x05\x03`) | M1 | explorer_hardware_1 |
| 9 | Chip Enable & Driver State | Enable analog frontend via CMD 0x96 and set driver state via CMD 0xc4 | M2 | explorer_hardware_1, explorer_libfprint_1 |
| 10 | Hardware FDT Mode Configuration | Configure FDT operating mode via CMD 0x36 (27-byte payload) | M1 | explorer_hardware_1, explorer_libfprint_1 |
| 11 | Hardware FDT DOWN Touch Detection | Asynchronous blocking capacitive touch interrupt via CMD 0x32 (39-byte payload, byte 26=0x01) | M1 | explorer_hardware_1, explorer_libfprint_1 |
| 12 | Hardware FDT UP Release Detection | Asynchronous blocking capacitive release interrupt via CMD 0x34 (39-byte payload, byte 26=0x00) | M1 | explorer_hardware_1, explorer_libfprint_1 |
| 13 | Elimination of Software Polling Loops | Remove all `g_timeout_add` timers, synthetic noise thresholds, and ad-hoc scan loops | M2 | explorer_libfprint_1 |
| 14 | Frame Acquisition & TLS Decryption | Request frame via CMD 0x20, decrypt 7,684-byte payload to 7,680 raw bytes | M2 | explorer_hardware_1, explorer_libfprint_1 |
| 15 | 12-bit Pixel Unpacking & Normalization | Unpack 6-byte blocks to 4 12-bit pixels (80x64), normalize to 8-bit grayscale | M2 | explorer_hardware_1, explorer_libfprint_1 |
| 16 | Bilinear Demosaicing & Process Frame | Bilinear interpolation to 160x128 FpImage with `FPI_IMAGE_PARTIAL \| FPI_IMAGE_COLORS_INVERTED` | M2 | explorer_libfprint_1 |
| 17 | Deterministic USB Read Loop Cancellation | Use `g_cancellable_cancel` and `g_cancellable_reset` to prevent uncancelled transfers | M3 | explorer_hardware_1, explorer_nixos_1 |
| 18 | Non-blocking TLS Socket Teardown | `shutdown(fd, SHUT_RDWR)` before thread join to prevent PAM hangs | M3 | explorer_hardware_1, explorer_nixos_1 |
| 19 | Protocol State Reset on Deactivation | Clear `priv->cmd`, `priv->ack`, `priv->reply`, timers, and data buffers in `dev_deactivate` | M3 | explorer_libfprint_1, explorer_nixos_1 |
| 20 | Meson / Ninja Build System Wiring | Wire `goodixtls5e0a` into `meson.build` and `libfprint/meson.build` | M4 | explorer_libfprint_1, explorer_nixos_1 |
| 21 | NixOS Flake & Derivation Patch | Create clean unified patch and integrate into `/home/sastauser/NixOS-Hyprland/modules/goodix/` | M4 | explorer_nixos_1 |
| 22 | Hermetic nix-build & Flake Evaluation | Verify clean compilation of `libfprint-goodix` and `fprintd` override under Nix | M4 | explorer_nixos_1 |
| 23 | Multi-Run PAM Verification & Enrollment | Pass 100% of multi-stage enroll and consecutive verification tests on hardware | M5 | explorer_nixos_1 |
| 24 | Adversarial Edge-Case Hardening | Verify empty air rejection, rapid cancellation, USB disconnect/reconnect handling | M5 | explorer_hardware_1, explorer_libfprint_1 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Hardware FDT Touch/Release & Sensor Config | Verify and format exact FDT mode (0x36), FDT DOWN (0x32), FDT UP (0x34), and register 0x022c payload tables | none | DONE |
| 2 | Modular Base-Class Driver Refactoring | Refactor `goodix5e0a.c` as a pure subclass of `FpiDeviceGoodixTls5xx` under Ponytail standard, eliminating all polling loops | M1 | DONE |
| 3 | Multi-Run Session Lifecycle & USB Recovery | Implement robust deactivation cleanup, socket shutdown, and cancellable read loops to eliminate 0xa2 timeouts | M2 | DONE |
| 4 | NixOS Flake & System Integration Patch | Package driver into `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` and verify Meson/Ninja + nix-build | M3 | DONE |
| 5 | E2E Test Suite & Adversarial Hardening | Execute comprehensive test suite (Tiers 1-4) and adversarial stress tests (Tier 5) on hardware | M4 | DONE |

## Interface Contracts
### `goodix5e0a` Subclass ↔ `FpiDeviceGoodixTls5xx` Base Class
- `xx_cls->get_mcu_cfg`: Returns 27-byte FDT mode configuration (`goodix_5e0a_fdt_mode`).
- `xx_cls->get_fdt_down_cfg`: Returns 39-byte FDT DOWN configuration (`goodix_5e0a_fdt_down`, byte 26 = `0x01`).
- `xx_cls->get_fdt_up_cfg`: Returns 39-byte FDT UP configuration (`goodix_5e0a_fdt_up`, byte 26 = `0x00`).
- `xx_cls->process_frame`: Unpacks raw 12-bit sensor array (80x64), performs bilinear demosaicing to 160x128, outputs `FpImage`.
- `dev_class->temp_hot_seconds`: Set to `-1` (disables thermal polling loop).
- `gx_class->ep_in = 0x83`, `gx_class->ep_out = 0x01`.

## Code Layout
- Driver source tree: `/tmp/libfprint-goodix/libfprint/drivers/goodixtls/`
  - `goodix5e0a.c` (Target driver implementation)
  - `goodix5e0a.h` (Target driver headers & config tables)
  - `goodix5xx.c`, `goodix5xx.h` (Base class `FpiDeviceGoodixTls5xx`)
  - `goodix.c`, `goodix.h`, `goodixtls.c`, `goodix_proto.h` (TLS engine & USB transport)
- NixOS module tree: `/home/sastauser/NixOS-Hyprland/modules/goodix/`
  - `default.nix` (NixOS service & PAM config)
  - `libfprint-goodix.nix` (Nix derivation)
  - `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` (Integrated patch)
- E2E Test Suite: `/home/sastauser/code/temp/goodix/tests/`
