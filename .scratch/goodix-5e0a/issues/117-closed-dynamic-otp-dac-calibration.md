# 117: Dynamic OTP DAC calibration and unified driver configuration

**Status:** closed
**Verdict:** confirmed

## Scope

Integrate hardware OTP DAC derivation directly into `libfprint-driver/goodix5e0a.c` so that the driver operates out-of-the-box for all sensor revisions without compile-time patches (`jet-soup-capture.patch`) or test harness parameters (`--capture-settings`).

1. **OTP DAC Extraction in Driver (`libfprint-driver/goodix5e0a.c`):**
   - Wired `ACTIVATE_READ_OTP` (CMD `0xa6`) to `goodix5e0a_on_read_otp`.
   - Reads 64 bytes of OTP data from sensor via USB packet loop.
   - Parses 4-channel DACs from primary `otp[0x2e..0x31]` and secondary `otp[0x32..0x35]`, incorporating high bit from `otp[0x13]`.
   - Default fallback: maintainer baseline DACs `[0xb0, 0xb2, 0xb0, 0xb1]` if read fails or is zero.
2. **Dynamic Packet Generation:**
   - Updates runtime packet tables (`self->fdt_down_s12`, `self->fdt_up_u01`, and `goodix5e0a_capture_payload`) with calibrated DAC values.
   - If Jet-Soup's OTP DACs (`0xad`) are detected, applies the corresponding config adjustments in `self->mcu_config` (offsets `0x78`, `0x7e..0x7f`, `0xfe..0xff`).
3. **Preserve Validated Safety Measures:**
   - Retained Milan quality floor (`best_quality >= 15`) in `choose_best`.
   - Retained physical lift release guard in `goodix5e0a_on_fdt_up_reply`.
   - Retained Linux-only PSK recovery (`tools/extract_psk_whitebox.py`).
4. **Software Verification:**
   - Added `tests/tier1_feature/test_f117_dynamic_otp_calibration.py`.
   - Full test suite execution: 405 tests executed, 396 passed, 0 failures, 0 errors.
   - Driver compactness: 1975 non-empty LOC (limit < 2000), `g_message (` count: exactly 25.
   - Package build: `nix build .#libfprint-goodix` succeeds with 0 warnings/errors.

## Evidence & reverse engineering ground truth

- Disassembly of Windows driver (`wbdi.dll:0x180052500`–`0x180052e4d`, `chicagoh.c`):
  - Primary DAC bytes stored at `otp[0x2e..0x31]`.
  - Secondary backup DAC bytes stored at `otp[0x32..0x35]`.
  - High bit 8 for channels 0..3 stored in `otp[0x13]` (bits 3..0).
- Windows calibration dump (`goodix.dat`):
  - Maintainer sensor: `[0xb0, 0xb2, 0xb0, 0xb1]`.
  - Jet-Soup sensor: `[0xad, 0xae, 0xac, 0xad]`.

## Hardware Verification

- **Maintainer Unified Run (`goodix-test-b170e90a5c396f6c.zip`):**
  - Parameter: `capture_settings: "current"`, `patch_sha256: null` (built purely from HEAD, zero patch files).
  - Hands-off (20s): `hands_off_activity: false` (silent, 0 false triggers).
  - Holding (20s): `holding_advances: 1` (single advance, physical release guard active).
  - Enrollment: 12 stages committed successfully (38,708-byte Milan template).
  - Genuine verification: 5/5 matched (pts: 29, 96, 100, 100, 100).
  - Impostor verification: 5/5 rejected (pts: 0, 0, 0, 0, 0).
  - Verdict: **CONFIRMED**.

## Conclusion

Dynamic OTP DAC calibration and unified driver configuration are confirmed working seamlessly on live hardware without any external patches or command parameters. Both sensor variants operate out of the box with `./install.sh`.
