# 26 — Cold-Boot / Post-Reboot TLS 1.2 PSK Disagreement & Key Provisioning

**What to build:** 
Resolve the post-reboot / cold-boot TLS 1.2 PSK handshake failure. On machine cold boot or hardware power cycle, the Goodix 27c6:5e0a MCU rejects the TLS Finished record with a bad record MAC (`error:0A000119:SSL routines::decryption failed or bad record mac`), preventing the sensor from entering encrypted session mode and causing all subsequent image captures (`0x20`) to be rejected with `0xd0` (`GOODIX_CMD_REQUEST_TLS_CONNECTION`).

**Blocked by:** None. Supersedes the cold-boot OTP hypothesis from Ticket 20.

**Status:** ready-for-agent

---

## 1. Ground Truth Journal Evidence (Post-Reboot Failure)

Following a system reboot (machine cold start), `fprintd-enroll` and `fprintd-verify` consistently fail with `enroll-unknown-error` / `verify-unknown-error`.

**Systemd Journal Signature (`journalctl -u fprintd` at 14:38:08, 14:54:02, 15:30:16):**
```text
Sep 05 15:30:16 sastapc fprintd[60626]: 5e0a PSK callback: using device-specific PSK (32 bytes, identity='Client_identity')
Sep 05 15:30:16 sastapc fprintd[60626]: 5e0a TLS accept failed: error:1C800066:Provider routines::cipher operation failed (0x1c800066, cipher: PSK-AES128-CBC-SHA256)
Sep 05 15:30:16 sastapc fprintd[60626]: 5e0a TLS accept failed: error:0A000119:SSL routines::decryption failed or bad record mac (0xa000119, cipher: PSK-AES128-CBC-SHA256)
Sep 05 15:30:16 sastapc fprintd[60626]: 5e0a TLS accept failed: error:0A000139:SSL routines::record layer failure (0xa000139, cipher: PSK-AES128-CBC-SHA256)
Sep 05 15:33:22 sastapc fprintd[60626]: 5e0a D32 reply: status=0x02 len=16 bytes=[02 00 3f 00 35 01 5c 01 f4 00 0e 01 34 01 17 01 ]
Sep 05 15:33:22 sastapc fprintd[60626]: 5e0a D32 touch confirmed: mask=0x3f energy=1758
Sep 05 15:33:22 sastapc fprintd[60626]: Invalid protocol command: 0xd0
Sep 05 15:33:23 sastapc fprintd[60626]: 5e0a failed to scan: Command timed out: 0x20 (code: 24)
Sep 05 15:33:23 sastapc fprintd[60626]: Device reported an error during identify for enroll: Command timed out: 0x20
```

---

## 2. Chronological Analysis: What Worked vs What Failed

### A. When it was working (Run 15 & Run 16, 02:20–02:36 AM)
- In Hardware Runs 15 and 16, the system achieved consecutive verified biometric matches on physical hardware (`13/12`, `15/12`, `14/12`).
- The sensor was actively decrypting live 10,564-byte wire frames via `SSL_read`, yielding 23–25 minutiae.
- **Critical Context:** The laptop had been running continuously without a cold reboot or USB power loss. The MCU's volatile RAM retained the active session PSK matching `goodix_5e0a_psk` (`d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab`).

### B. What Happened During Reboot
- During machine reboot or power-off, USB VBUS drops and the Goodix Geneva MCU executes a cold reset.
- Volatile SRAM on the MCU is cleared.
- Upon booting Linux, the MCU initializes in an unprovisioned or reset cryptographic state.
- When `libfprint` attempts a TLS 1.2 PSK handshake using `goodix_5e0a_psk`, the MCU's internal crypto engine computes a different message authentication code (MAC) for the Finished record, resulting in OpenSSL error `0x0A000119: decryption failed or bad record mac`.
- The TLS handshake fails, leaving the MCU in unencrypted mode.
- When the user touches the sensor, the MCU sends `0xd0` (`REQUEST_TLS_CONNECTION`) because it requires TLS before it will stream raw fingerprint frames (`0x20`). Libfprint times out waiting for `0x20`, emitting `enroll-unknown-error` / `verify-unknown-error`.

### C. Post-Mortem of Failed Attempts

| Attempt | Change Tested | Hypothesis | Actual Hardware Result | Why It Failed |
|---|---|---|---|---|
| **1** | Added `ACTIVATE_READ_OTP` (`0xa6`) | MCU needs OTP registers read before TLS to load PSK into SRAM. | `TLS accept failed: bad record mac` (identical) | CMD `0xa6` is a host read command that returns 128 bytes of OTP info to the host; it does not load or provision the internal crypto keys. |
| **2** | Reverted `ACTIVATE_READ_OTP` | Maybe `0xa6` perturbed the 4-state activation sequence. | `TLS accept failed: bad record mac` (identical) | Removing `0xa6` left the MCU in the same unprimed state. |
| **3** | Prioritized cipher `PSK-AES128-CBC-SHA256:ALL:@SECLEVEL=1` | OpenSSL 3.x negotiated wrong cipher suite or SECLEVEL rejected SHA256. | Cipher logged as `PSK-AES128-CBC-SHA256`, still `bad record mac`. | The cipher suite was never the issue; the failure is cryptographic HMAC verification due to mismatched secret keys between host and MCU. |
| **4** | Pre-TLS MCU Config Upload (`0x90`, 256B) | MCU needs sensor registers / AFE loaded before starting crypto engine. | `TLS accept failed: bad record mac` (identical) | Sensor configuration (`0x90`) sets AFE and touch scan registers, not crypto key registers. |

---

## 3. The Core Unknown & Missing Link

In Goodix TLS devices (511, 52xD, 5e0a), the PSK is not always hardcoded permanently in volatile MCU memory across power cuts.
There are three possible mechanisms:
1. **Host-Provisioned PSK via `0xe0` (`GOODIX_CMD_PRESET_PSK_WRITE`)**:
   - The Windows WBDI driver or Windows Biometric Service writes a pre-shared key to the device on cold boot using CMD `0xe0` before attempting TLS.
   - Sibling driver `goodix511.c` checks the PSK via `0xe4` (`GOODIX_CMD_PRESET_PSK_READ`), and `goodix.c` has `goodix_send_preset_psk_write` (`0xe0`).
2. **Device Key Derivation from Challenge / OTP**:
   - The device reports a key or challenge via `0xe4`, or derives a session key from OTP memory + host nonce.
3. **Prior Windows State Preservation**:
   - Prior to reboot, the machine may have booted into Windows (or ran a Python script that wrote the key), which primed the volatile SRAM. Once rebooted cleanly into Linux without Windows running first, the MCU was blank.

---

## 4. Planned Experiments

### Experiment 26.1: Probe MCU PSK Status via Python Standalone Harness
- **Control Test:** Stop `fprintd` (`sudo systemctl stop fprintd`).
- **Command:** Run `PYTHONPATH=. nix-shell -p python3Packages.pyusb openssl --run "python3 experiments/test_register.py"`.
- **Predicted Outcomes:**
  - *Branch A (Read returns key):* If `preset_psk_read(0xbb020001)` succeeds, inspect what 32-byte key the MCU currently holds. If it returns a key different from `d853ad...`, the MCU holds a default or generated key.
  - *Branch B (Read returns 0 bytes or error):* The MCU requires PSK provisioning via `preset_psk_write(0xbb020001, goodix_5e0a_psk)`.

### Experiment 26.2: Test `preset_psk_write` (`0xe0`) in Activation Sequence
- If Experiment 26.1 shows the MCU accepts `preset_psk_write`, add `ACTIVATE_WRITE_PSK` (`0xe0`) to `libfprint-driver/goodix5e0a.c` prior to `goodix_tls_init`.
- **Confirm Signature:** `5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)` without `bad record mac`.
- **Falsify Signature:** MCU rejects `0xe0` or still fails MAC.

---

## 5. Artifacts & References
- Previous working match evidence: `docs/PROGRESS.md` Run 15 & Run 16.
- OpenSSL error logs: systemd journal 14:38:08, 14:54:02, 15:30:16.
- Reverse engineering references: `experiments/test_register.py`, `experiments/test_init_sensor.py`.
