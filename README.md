# Goodix 27c6:5e0a Linux Driver

A reverse-engineered Linux driver for the **Goodix 27c6:5e0a** fingerprint scanner found on laptops such as the Realme Book Slim / Enhanced (MilanF / ChicagoH / GF5288 architecture), built for `libfprint` and `fprintd`.

---

## Features & Highlights

- **Native `libfprint` Integration**: Clean subclass of `FpiDeviceGoodixTls5xx` adhering to minimal, event-driven design principles.
- **Hardware FDT Touch & Release**: Uses hardware capacitive Finger Detection Trigger (`0x32` FDT DOWN, `0x34` FDT UP) with sampled channel-energy gating (short silent re-poll on idle).
- **TLS 1.2 PSK Encryption**: On-wire `TLS_PSK_WITH_AES_128_CBC_SHA256` with a device-specific PSK; cold path latches MCU crypto state via a Geneva 16-byte `0xe4` read of slot `0xbb020001` before TLS and uploads chip config after TLS (ticket 48).
- **NIST NBIS Minutiae Verification**: NBIS extraction with Bozorth3 matching at operating point threshold 14 (`bz3_threshold = 14`, 14 enroll stages; tickets 43/65/70).
- **Sub-300ms Instant Unlock**: Direct SSM completion and immediate finger release reporting on image capture eliminate perceived latency without stalling on finger-lift polling.
- **Empty-Air Rejection Gate**: Touch-gated capture plus an enrollment minutiae floor keep untouched or faint touches out of templates.
- **Multi-Run PAM Stability**: Parked-TLS session reuse with idle-only gating across back-to-back claims, no desync or unknown-errors (tickets 38, 46, 49).
- **Verify-Retry Release Guard**: Rapid retries park in FDT-UP until a genuine finger release instead of burning attempts on a held finger (tickets 47, 49).
- **System Power Management**: Genuine `.suspend` and `.resume` vfunctions handle S3 sleep cleanly without wedging PAM.
- **Exhaustive Automated Test Suite**: 448 tests across 5 tiers (tiers 1–5 green via `bash tests/run_all_tests.sh` as of 2026-09-09).
- **Hermetic NixOS Flake & Derivation**: Automated compilation, patch validation, and systemd service generation via standard Nix workflows.

---

## Running the Test Suite

The test suite runs hermetically without requiring hardware access:

```bash
bash tests/run_all_tests.sh
```

Or a single test from the repo root:

```bash
python3 -m unittest tests.tier1_feature.test_f13_no_polling
```

(`discover -s tests` has loader failures; run per-tier or per-module instead.)

---

## NixOS Installation

In your `flake.nix` or NixOS configuration:

```nix
imports = [
  ./path/to/goodix/nixos-module.nix
];

services.fprintd.enable = true;
```

---

## License

LGPL-2.1-or-later (consistent with upstream `libfprint`).

## Known limitations

- **Enrollment coverage**: `fprintd` enrolls 14 stages of limited sensor area — less than the vendor Windows driver captures. Same-finger multi-enroll is an operator workaround with a FAR tradeoff; the matching pipeline is frozen (no tuning without impostor data).
- **First-tap misses**: occasional no-match on the first tap after boot/restart, matching on re-tap. Under watch; not yet a ticket.
