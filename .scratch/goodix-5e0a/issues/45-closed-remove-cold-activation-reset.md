# 45 — Remove cold-activation reset (CMD 0xa2) to fix cold-boot TLS handshake failure

**What to build:**
In `libfprint-driver/goodix5e0a.c`, remove `ACTIVATE_RESET` (CMD `0xa2`) from the cold activation ladder so activation goes directly from `ACTIVATE_READ_AND_NOP` to `ACTIVATE_CHECK_FW_VER -> UPLOAD_CONFIG -> TLS`. Keeps all other SSM states, callbacks, and biometric pipeline untouched. One variable: activation ladder sequence on cold boot only.

**Blocked by:** None. Successor to ticket 44 (closed with confirmed hardware proof).

**Status:** closed (confirmed)

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
   - In Linux `goodix5e0a.c`, cold activation previously executed `ACTIVATE_RESET`:
     `goodix_send_reset (dev, TRUE, 20, ...)` -> Sends CMD `0xa2` with payload `[0x01, 0x14]` (`reset_sensor = 1, soft_reset_mcu = 0, sleep = 20ms`).
   - This sensor AFE reset desynchronized the MCU internal crypto state before `0xd0` (`REQUEST_TLS_CONNECTION`), triggering `bad record mac` (`0x0A000119`).
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

## 3. Hardware Verification Protocol & Evidence

### Hardware Test Run: 2026-09-09 00:26–00:28 IST

Pasted journal output across cold boot & multiple daemon claim cycles (PID 1673):
```text
Sep 09 00:26:58 sastapc fprintd[1673]: 5e0a USB reset taken (dirty close, boot_seq=1)
Sep 09 00:26:58 sastapc fprintd[1673]: 5e0a warm expired: reason=cold-start
...
Sep 09 00:27:14 sastapc fprintd[1673]: 5e0a frame 1/3: declen=10564 active=5120 range=1931 minutiae=22 score-proxy=22
Sep 09 00:27:14 sastapc fprintd[1673]: 5e0a frame 2/3: declen=10564 active=5120 range=1943 minutiae=22 score-proxy=22
Sep 09 00:27:14 sastapc fprintd[1673]: 5e0a frame 3/3: declen=10564 active=5120 range=1939 minutiae=24 score-proxy=24
Sep 09 00:27:14 sastapc fprintd[1673]: 5e0a best frame 3/3: minutiae=24 score-proxy=24 (submitting)
Sep 09 00:27:14 sastapc fprintd[1673]: 5e0a USB reset skipped (clean close, boot_seq=2)
Sep 09 00:27:14 sastapc fprintd[1673]: 5e0a TLS session reused (parked 0.0s, gen=6)
...
Sep 09 00:28:11 sastapc fprintd[1673]: 5e0a frame 1/3: declen=10564 active=5120 range=2136 minutiae=12 score-proxy=12
Sep 09 00:28:11 sastapc fprintd[1673]: 5e0a frame 2/3: declen=10564 active=5120 range=2132 minutiae=15 score-proxy=15
Sep 09 00:28:12 sastapc fprintd[1673]: 5e0a frame 3/3: declen=10564 active=5120 range=2144 minutiae=12 score-proxy=12
Sep 09 00:28:12 sastapc fprintd[1673]: 5e0a TLS session reused (parked 0.0s, gen=33)
Sep 09 00:28:16 sastapc fprintd[1673]: 5e0a frame 1/3: declen=10564 active=5120 range=2024 minutiae=15 score-proxy=15
Sep 09 00:28:16 sastapc fprintd[1673]: 5e0a frame 2/3: declen=10564 active=5120 range=2012 minutiae=19 score-proxy=19
Sep 09 00:28:16 sastapc fprintd[1673]: 5e0a frame 3/3: declen=10564 active=5120 range=2000 minutiae=17 score-proxy=17
```

### Verdict: CONFIRMED
1. Zero occurrences of `bad record mac` (`0x0A000119`) across the entire journal after deployment.
2. Cold boot first activation (`boot_seq=1`) establishes TLS cleanly without crypto desynchronization.
3. Warm and cold captures reliably yield genuine 5120 active-pixel frames with high minutiae counts (9–24) and successful TLS session parking/reuse.
4. Ticket 45 is CLOSED.

