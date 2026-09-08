# 45 — Remove cold-activation reset (CMD 0xa2) to fix cold-boot TLS handshake failure

**What to build:**
In `libfprint-driver/goodix5e0a.c`, remove `ACTIVATE_RESET` (CMD `0xa2`) from the cold activation ladder so activation goes directly from `ACTIVATE_READ_AND_NOP` to `ACTIVATE_CHECK_FW_VER -> UPLOAD_CONFIG -> TLS`. Keeps all other SSM states, callbacks, and biometric pipeline untouched. One variable: activation ladder sequence on cold boot only.

**Blocked by:** None. Successor to ticket 44 (closed with confirmed hardware proof).

**Status:** ready-for-agent

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

## 2. Planned Changes

1. `libfprint-driver/goodix5e0a.c`:
   - In `activate_run_state`: remove `ACTIVATE_RESET` (or jump over it on both cold and warm, or delete state from enum).
   - In `activate_states` enum: remove `ACTIVATE_RESET`, `ACTIVATE_READ_CHIP_ID`, `ACTIVATE_READ_OTP` if dead, or make `ACTIVATE_READ_AND_NOP` transition directly to `ACTIVATE_CHECK_FW_VER`.
2. Sync with upstream tree checkout at `/home/sastauser/code/temp/libfprint-upstream` (`test-5e0a` branch).
3. Regenerate unified patch `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`.
4. Run hermetic test suite: `tests/run_all_tests.sh` and driver-only ninja build.

---

## 3. Hardware Verification Protocol (User Only)

1. Deploy:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Cold boot test:
   Power off machine (shutdown -h now), wait 30s, power on, boot into Linux, run `fprintd-verify`.
3. Predicted journal signatures:
   - Confirm: `5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)` on the very first activation after cold boot. Zero `bad record mac` errors.
