# 118 — Spurious Air Trigger Bound and Wire DAC Alignment

**What was built:**
1. Spurious air trigger retry bounding: Added `air_retries` counter (bounded to 5), calling `goodix5e0a_reset_touch_frames` before re-arming `SCAN_5E0A_FDT_DOWN`, and cleanly exiting to `deliver` (reporting no-match) upon retry exhaustion to eliminate the runaway scan loop (fixing the frame 555 defect observed in Jet-Soup run 1).
2. Byte-exact wire DAC alignment & checksum derivation: In `goodix5e0a_update_dacs`, for `(dacs[0] & 0xff) == 0xad`, update config at offsets 0xc8 (0x1f), 0xeb (0xf0), 0xec (0x00), dynamically compute the 16-bit LE additive checksum with seed 0xa5a5 (producing 0x1e4a), set capture payload byte 0 to 0x01, and keep 0x05 for standard units (matching `experiments/jet-soup-capture.patch` bit-for-bit).
3. Enrollment release guard stop-loss: Stamped `retry_guard_mono` on intermediate enrollments and terminated with `fpi_ssm_mark_failed` if held finger exceeds 30s.
4. Hardware session store canary: `tools/hardware_session.py` queries existing prints before test (`fprintd-list $USER`), asserts 0 prints in isolated namespace, asserts print count matches after restore, and gates `info["restored"] = True` strictly on `runtime_owned`, RUNTIME existence at restore start, and canary match.
5. OTP path logging: Added `fp_dbg` logging decoded DAC values in `goodix5e0a_on_read_otp`.
6. Documentation restored: Restored "Record layout and the by-offset read" section with the offset table in `docs/psk-extraction.md` and Jet-Soup credit line in `README.md`.
7. Test coverage enhanced: Enhanced `tests/tier1_feature/test_f117_dynamic_otp_calibration.py` to assert C implementation sites and byte-level alignment against `experiments/jet-soup-capture.patch`, and added store canary unit tests to `tests/tier1_feature/test_f115_hardware_session.py`.

**Evidence from Prior Hardware Runs:**
- Jet-Soup run 1 (`77abe5d8`): genuine 5/5, wrong 1/1, aborted — client timed out on wrong 2/5; driver scanned continuously to frame 555 of 4 due to spurious air trigger loop without frame reset or retry limit.
- Jet-Soup run 2 (`69953408`): genuine 4/5 (1 miss at pts=0, bad contact), wrong 5/5; verdict: falsified under harness rule.
- Store canary: both runs reported `restored: true` while the account's main enrollment store was empty.

**Blocked by:** None.

**Status:** ready-for-hardware-verify

## Predicted Signatures

### Branch 1: Maintainer Hardware (`dacs[0] == 0xb0`)
- **Confirm:**
  - `5e0a OTP DAC calibration: 0x0b0 0x0b2 0x0b0 0x0b1`
  - `5e0a dynamic config applied: standard unit`
  - `5e0a frame 1/4:` ... (burst strictly bounded to 4 frames, never runaway)
  - Config checksum remains `0x0e53`, capture payload byte 0 is `0x05`
  - 5/5 genuine matches, 5/5 impostor rejections
  - Canary confirms `prints_before_test == prints_after_restore`, `prints_isolated == 0`, `restored: true`
- **Falsify:**
  - Checksum rejection or sensor NACK
  - Runaway frame scanning beyond 4 frames
  - Impostor false match or canary count mismatch

### Branch 2: Jet-Soup Hardware (`dacs[0] == 0xad` or `0x1ad`)
- **Confirm:**
  - `5e0a OTP DAC calibration: 0x0ad 0x0ae 0x0ac 0x0ad` (or `0x1ad ...`)
  - `5e0a dynamic config applied: 0xad unit, checksum=0x1e4a`
  - Dynamically calculated checksum `0x1e4a`, capture payload byte 0 is `0x01`
  - On poor contact / spurious air trigger: `5e0a spurious air trigger rejected: quality=...` with frame reset, bounded by `air_retries < 5` without burst count runaway
  - On held finger exceeding 30s: `5e0a enrollment release guard: orphaned hold past 30s, failing claim` aborts cleanly with failed SSM
  - 5/5 genuine matches, 5/5 impostor rejections
  - Canary confirms `prints_before_test == prints_after_restore`, `prints_isolated == 0`, `restored: true`
- **Falsify:**
  - Continuous scan runaway beyond 4 burst frames (e.g. frame 555)
  - Checksum failure or NACK during config upload
  - Impostor false accept or store canary mismatch
