# 45 — Remove cold-activation reset (CMD 0xa2) to fix cold-boot TLS handshake failure

**What to build:**
In `libfprint-driver/goodix5e0a.c`, remove `ACTIVATE_RESET` (CMD `0xa2`) from the cold activation ladder so activation goes directly from `ACTIVATE_READ_AND_NOP` to `ACTIVATE_CHECK_FW_VER -> UPLOAD_CONFIG -> TLS`. Keeps all other SSM states, callbacks, and biometric pipeline untouched. One variable: activation ladder sequence on cold boot only.

**Blocked by:** None. Successor to ticket 44 (closed with confirmed hardware proof).

**Status:** ready-for-hardware-verify

---

## 1. Settled facts & Ground Truth (from ticket 44, frozen)

1. **Hardware key state verified**: Live hardware probe (`probe_psk_provision_wbdi.py`) executed 2026-09-09 00:13 IST confirmed:
   - Reading slot `0xbb020001` returned `68776fdcf6352a215cc11cd58db2b361eb95a506cb503da68fb01ac1506ff1c9`, which is the exact byte-for-byte SHA-256 hash of `goodix_5e0a_psk` (`d853ad...b2ab`).
   - Reading slot `0xbb010002` returned the 128-byte Windows DPAPI sealed PSK blob (`01000000d08c9ddf0115d1118c7a00c04fc297eb...`).
   - The MCU has **always held the correct operational key in hardware NVM/flash**. The key mismatch / PSK loss hypothesis is closed for good.
2. **Windows driver parity**:
   - In `wbdi.dll`, `McuResetMcuStub` and `McuResetFpAndMcuStub` are **unimplemented stubs** (`0x18007b620`) that log `"not implemented"` and return 0.
   - Across all 19 Windows captures (`goodix-win*.pcapng`, cold boot, first open, session start), **CMD `0xa2` appears exactly ZERO times**. Windows NEVER resets the MCU or sensor on activation.
3. **The failure mechanism**:
   - In Linux `goodix5e0a.c`, cold activation currently executes `ACTIVATE_RESET`:
     `goodix_send_reset (dev, TRUE, 20, ...)` -> Sends CMD `0xa2` with payload `[0x01, 0x14]` (`reset_sensor = 1, soft_reset_mcu = 0, sleep = 20ms`).
   - This sensor AFE reset desynchronizes the MCU internal crypto state before `0xd0` (`REQUEST_TLS_CONNECTION`), triggering `bad record mac` (`0x0A000119`).
   - On warm activation fast path (ticket 40), `ACTIVATE_RESET` was already skipped, and warm activations consistently succeeded.
   - Eliminating `ACTIVATE_RESET` aligns Linux with Windows wire parity and resolves the cold-boot TLS handshake MAC failure.

---

## 2. Implementation Summary

1. `libfprint-driver/goodix5e0a.c`:
   - Updated `case ACTIVATE_RESET:` in `activate_run_state` to unconditionally jump to `ACTIVATE_CHECK_FW_VER`:
     ```c
     case ACTIVATE_RESET:
       /* Windows wire parity (ticket 45): wbdi.dll has McuResetMcu unimplemented
        * and sends zero 0xa2 commands across all captures. CMD 0xa2 (reset_sensor=1)
        * on cold boot desyncs MCU crypto state causing bad record mac on TLS accept.
        * Proceed directly to CHECK_FW_VER on both cold and warm. */
       fpi_ssm_jump_to_state (ssm, ACTIVATE_CHECK_FW_VER);
       break;
     ```
2. Synced with:
   - Build tree: `/tmp/libfprint-goodix/libfprint/drivers/goodixtls/goodix5e0a.c` (ninja build clean).
   - Upstream tree: `/home/sastauser/code/temp/libfprint-upstream/libfprint/drivers/goodixtls/goodix5e0a.c`.
3. Regenerated unified patch `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` (SHA256: `15e9bfdb9ff26ed3e446bf19c84f1f75e0314b1de2cb0749df6f4eaaafa92d90`).
4. Synced patch with NixOS flake module at `/home/sastauser/NixOS-Hyprland/modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`.
5. Full package hermetic build verified: `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'` exited 0.
6. Master test suite: 438/438 tests passed in `tests/run_all_tests.sh`.

---

## 3. Hardware Verification Protocol (User Only)

1. Deploy:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Cold boot test:
   Power off machine (`sudo shutdown -h now`), wait 30s, power on, boot into Linux, run `fprintd-verify`.
3. Check journal:
   `journalctl -u fprintd --since "5 min ago" --no-pager | grep -a -E "5e0a TLS|5e0a frame|error|failed" | tail -n 20`
4. Predicted journal signatures:
   - **Confirm**: `5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)` on the very first activation after cold boot. Zero `bad record mac` errors.
   - **Falsify**: `bad record mac` (`0x0A000119`) persists after cold boot.
