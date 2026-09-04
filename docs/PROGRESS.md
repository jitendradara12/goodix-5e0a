# Goodix 27c6:5e0a Linux Driver — Progress & Architecture Documentation

## 1. Overview
Support for the Goodix 27c6:5e0a fingerprint sensor (Realme Book / ChicagoH / GF3658 DN3, APP_10036) in libfprint for NixOS.

---

## 2. Proven & Frozen Architecture

| Subsystem | Status | Proven Mechanism / Parameters |
|---|---|---|
| **USB Transport** | Frozen | Bulk endpoints `EP 0x83` (IN) / `0x01` (OUT), interface 0 |
| **Reset Phasing** | Frozen | NOP -> Reset (number 2048) -> Read chip ID -> Query FW version (`GFUSB_GM168SEC_APP_10036`) |
| **TLS Handshake** | Frozen | TLS 1.2 PSK (`PSK-AES128-CBC-SHA256`), PSK extracted from DPAPI, PSK flags `0xbb020001` |
| **Chip Provisioning** | Frozen | Base ChicagoH table from `wbdi.dll:0x197c50` (VMA `0x180198a50`), 256 bytes, checksum `0x0e53` (`53 0e`) |
| **Touch Gating** | Frozen | Dynamic 16-bit channel energy on D32 (`data[2] != 0xff && channel_energy > 0`); blocking hardware interrupt in empty air |
| **Frame Decryption** | Frozen | Full 10564-byte decrypted frames (`declen=10564`), 7040 decoded 12-bit values with all 5120 sensor pixels active |
| **Deactivation Teardown** | Frozen | Synchronous teardown: reset driver USB state, shutdown TLS, stop read loop, immediate completion callback |
| **Minutiae & Matching** | Active | `FPI_IMAGE_COLORS_INVERTED` (capacitive high ADC -> NBIS black 0), 2x bilinear scaling (`fpi_image_resize` to 160x128) matching NBIS 500 DPI |

---

## 3. Hardware Verification Run Log

### Run 1 (2026-09-04 18:57–19:01)
- **Observations:** Phase 1 silent for 77s and 85s in empty air; MCU remained in blocking hardware interrupt wait. Touch triggered instant interrupt and returned 16-byte D32 reply (`mask=0x3f`, channel energy 1062–1514).
- **Flaw found:** Driver checked `len >= 20` which failed on 16-byte ChicagoH packets.
- **Fix:** Changed gating check to `len >= 4` with dynamic channel energy summation across `len`.

### Run 2 (2026-09-04 19:18–19:20)
- **Observations:** Sensor delivered canonical 10564-byte decrypted frames (`declen=10564`). All 5120 pixels active (`nonzero=5120`, range 415–2948). First enroll stage passed (`enroll-stage-passed`).
- **Flaw found:** Scan SSM concurrency guard dropped subsequent touches because finger-off was reported before SSM completion.
- **Fix:** Clear `self->scan_ssm = NULL` and complete SSM prior to reporting finger status FALSE.

### Run 3 (2026-09-04 19:44–19:46)
- **Observations:** 14 consecutive touches processed without deadlock. 5 of 8 stages passed in rapid succession (stages 1 to 5).
- **Flaw found:** Driver was using legacy 19-column downsampling and horizontal blur from degraded frame era, throwing away 75% of horizontal resolution.
- **Fix:** Direct mapping of all 80 native sensor columns into `img->data` at 1:1 optical clarity.

### Run 4 (2026-09-04 20:02–20:03)
- **Observations:** Full 8 of 8 enrollment stages completed on physical hardware (`reported 8 of 8 have been completed`).
- **Flaw found:** Teardown collision: upon stage 8 completion, `goodix5e0a_deactivate` sent an async sleep command (`0x60`) colliding with in-flight finger release.
- **Fix:** Made `goodix5e0a_deactivate` synchronous, matching `goodix5xx` base class.

### Run 5 (2026-09-04 20:19–20:20)
- **Observations:** Enrollment finished cleanly (`enroll-completed`) and template was committed to disk. First verify attempt yielded `verify-retry-scan` followed by `verify-no-match`.
- **Root cause:** Journal logged `Failed to detect minutiae: No minutiae found`. Bozorth3 matcher was never reached because:
  1. Missing `FPI_IMAGE_COLORS_INVERTED`: capacitive ADC has high values for ridges, so normalized buffer had white ridges on black valleys. NBIS `mindtct` requires 0 = black for ridges.
  2. Native 80x64 sensor area trimmed by `PERIMETER_PTS_DISTANCE = 10` left only 60x44 pixels, too small for 24x24 analysis windows.
- **Fix applied:** Added `FPI_IMAGE_COLORS_INVERTED`, 2x bilinear scaling via `fpi_image_resize (img, 2, 2)` to 160x128 (standard small-sensor pattern in `elanspi`, `aes3k`, `egis0570`), and empty-air rejection gate.

---

## 4. Current State & Verification Protocol

- Derivation: `/nix/store/qbdkga0h4a390wdg6940grrqwg0qfgmr-libfprint-goodix-1.94.5-goodixtls`
- Unified patch: synchronized with `/home/sastauser/NixOS-Hyprland/modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`
- Tests: `test_f16_demosaicing` (10/10) and `test_f23_pam_reliability` (5/5) passing.
- Next step: Re-enrollment to generate 160x128 gallery prints, followed by `fprintd-verify`.
