# 117 — Dynamic OTP DAC calibration and unified driver configuration

**What was built:**
1. Dynamic hardware OTP DAC derivation in `libfprint-driver/goodix5e0a.c`: reads 64 bytes of OTP via CMD `0xa6` during activation and derives 4-channel DACs (`otp[0x2e..0x31]`, `otp[0x32..0x35]`, and high bits `otp[0x13]`).
2. Unified runtime packet configuration: dynamically generates FDT DOWN, FDT UP, and capture payloads matching sensor OTP, automatically supporting both maintainer and Jet-Soup hardware units without external patches.
3. Preserved validated safeguards: Milan quality floor (`best_quality >= 15`), physical release guard, and Linux-only PSK recovery.
4. Added test coverage in `tests/tier1_feature/test_f117_dynamic_otp_calibration.py`.

**Hardware verification runs:**
- Maintainer unified run (`b170e90a5c396f6c`): built directly from HEAD with zero patch files. Silent hands-off (20s), single holding advance, 12 stages enrolled cleanly, 5/5 genuine matches (pts: 29, 96, 100, 100, 100), 5/5 impostor rejections.
- Jet-Soup run 1 (`77abe5d8`): genuine 5/5, wrong 1/1, aborted — client timed out on wrong 2/5; driver scanned continuously to frame 555 of 4 due to spurious air trigger loop.
- Jet-Soup run 2 (`69953408`): genuine 4/5 (1 miss at pts=0, bad contact), wrong 5/5; verdict: falsified.
- Evidence shows runtime config offsets and checksum differed from verified wire patch, and store canary was absent.

**Blocked by:** None.

**Status:** superseded by 118-ready-for-hardware-verify-spurious-air-trigger-and-dac-alignment.md

**Successor:** 118-ready-for-hardware-verify-spurious-air-trigger-and-dac-alignment.md
