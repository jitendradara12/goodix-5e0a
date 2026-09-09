# Ticket 48: Cold-Boot TLS Handshake Fix (Geneva CMD 0xe4 Slot Latch & Wire Parity)

**Status:** closed

Verdict: CONFIRMED on hardware 2026-09-09 (deployed driver).
Opened: 2026-09-09
Supersedes: 45 (insufficient — warm-sensor test, not true cold boot)

## Root Cause (Directly from Windows wbdi.dll Disassembly)

Disassembly of Windows `wbdi.dll` (`Start` at `0x180083900`, `PresetPskIsVaildG` at `0x180038888`, and `PresetPskReadG` at `0x1800978c8`) revealed the exact hardware lifecycle:

1. **MCU Power-Loss / Cold-Boot Requirement (`McuLostPower`)**:
   At `0x180083e31`, Windows logs: `"fetch psk, SgxLost:%d McuLostPower:%d TlsConnected:%d"`.
   When the sensor powers on from a cold shutdown, `McuLostPower` is TRUE.
   Windows immediately calls `ProcessPsk` -> `PresetPskIsVaildG` **BEFORE** calling `start tls...` (CMD `0xd0`).

2. **Geneva 16-Byte Wire Framing for CMD 0xe4**:
   In `PresetPskReadG` (`0x1800978c8`), Windows issues CMD `0xe4` with a 16-byte payload:
   `[length (4B LE), offset (4B LE), flags (4B LE), reserved (4B LE)]`
   reading slot `0xbb020001` (32-byte hash) and `0xbb010002` (128-byte sealed blob).
   Reading slot `0xbb020001` prompts the MCU's secure enclave to latch its operational PSK from NVM flash into active crypto registers.
   Without reading this slot on cold boot, the MCU's crypto registers are unlatched/empty, causing `bad record mac (cipher operation failed)` when the TLS Finished record is decrypted during `SSL_accept`.

3. **Config Upload Order (`download chip config...`)**:
   Windows calls `download chip config...` (`0x180084227`) **AFTER** TLS is established (`start tls...` at `0x180083fb6`).
   Linux was uploading config BEFORE TLS on cold boot.

4. **Why Ticket 26 / 37 Stripped CMD 0xe4**:
   The Linux driver previously used an 8-byte payload (`GoodixPresetPsk { flags, length }`, from Goodix 511) and compared the returned hash against the raw PSK via `memcmp`. Because `0xbb020001` returns `SHA256(psk)` rather than plaintext `psk`, the check failed, leading devs to believe `0xe4` was rejected or broken. Python testing in Ticket 44 §28 using the 16-byte framing proved the MCU happily responds on live hardware.

## Implementation

1. `goodix.h` / `goodix.c`:
   - Added `goodix_send_preset_psk_read_5e0a` sending the 16-byte Geneva payload:
     `[length=32, offset=0, flags=0xbb020001, reserved=0]`.
   - Propagate CMD 0xd0 error in `on_goodix_request_tls_connection` directly to `tls_ready_callback`.
2. `goodix5e0a.c`:
   - Added `ACTIVATE_CHECK_PSK` state and `on_psk_hash_read` callback.
   - On cold activation, reads slot `0xbb020001` via `goodix_send_preset_psk_read_5e0a` to latch the MCU crypto state before TLS.
   - Warm path skips `CHECK_PSK` and `UPLOAD_CONFIG` directly to `ACTIVATE_NUM_STATES`.
   - Post-TLS: `on_tls_activation_complete` uploads config on cold path before enabling chip.

## Hardware result 2026-09-09 (true cold boot) — handshake CONFIRMED,
## mechanism line still open

True cold boot (uptime 0:01 at 20:22). First post-power-on activation
20:20:39: `5e0a warm expired: reason=cold-start` → `5e0a TLS connection
ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)`, zero `bad record
mac`, zero `failed during TLS`. Hands-off 60s silent (`0` frame-stats).
Manual verifies after boot: no-match, no-match, then `verify-match`
(right-ring-finger, enrolled) — first taps after boot, no journal errors;
fresh fprintd (PID 3075) cold driver path also clean-TLS at 20:23:48/49.
Caveat: `set-environment` does not survive reboot, so the `fp_dbg`
mechanism lines (`reading PSK slot…`, `PSK hash read`, `Chip enabled!`)
could not appear — handshake success on a true cold MCU is proven, latch-
step execution needs one debug-env re-run (below).

## Mechanism re-run 2026-09-09 — full chain CONFIRMED, ticket closed

Debug-env re-run (PID 3506): `Cold path — reading PSK slot 0xbb020001`
→ `PSK hash read (0xbb020001): success=1, len=32` → device-specific PSK
→ `TLS connection ready` → `Cold path — uploading config after TLS...`
→ `Chip enabled! Activation complete.` → `verify-match`. Zero `bad record
mac`. Combined with the true-cold-boot TLS success above, both halves
hold: cold MCU handshakes clean AND the latch step demonstrably executes.

## Prior verification (builds/unit, pre-hardware)

- Unit tests (`tests.tier1_feature.test_f40_warm_activation`, `test_f47_verify_retry_release_guard`, `test_f28_whitebox`): All PASS.
- Ninja driver compilation: 0 warnings, 0 errors.
- Full `nix-build`: Successful.
- Flake patch updated at `/home/sastauser/NixOS-Hyprland/modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`.
