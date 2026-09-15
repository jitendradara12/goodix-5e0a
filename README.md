# Goodix 27c6:5e0a Linux Driver

A reverse-engineered Linux driver for the **Goodix 27c6:5e0a** fingerprint scanner found on laptops such as the Realme Book Slim / Enhanced (MilanF / ChicagoH / GF5288 architecture), built for `libfprint` and `fprintd`.

---

## Features & Highlights

- **Native `libfprint` Integration**: Clean subclass of `FpiDeviceGoodixTls5xx` adhering to minimal, event-driven design principles.
- **Hardware FDT Touch & Release**: Uses hardware capacitive Finger Detection Trigger (`0x32` FDT DOWN, `0x34` FDT UP) with sampled channel-energy gating (short silent re-poll on idle).
- **TLS 1.2 PSK Encryption**: On-wire `TLS_PSK_WITH_AES_128_CBC_SHA256` with a device-specific PSK; cold path latches MCU crypto state via a Geneva 16-byte `0xe4` read of slot `0xbb020001` before TLS and uploads chip config after TLS (ticket 48).
- **Goodix Milan Matching Engine**: Native Windows vendor engine (`GoodixEngineAdapter.dll`) running in-process via custom lightweight PE loader and `%gs` TEB shims (`goodix_milan.c`), providing commercial-grade 1:1 verification, 1:N identification, and 8-stage multi-impression template stitching.
- **Native Frame Quality Ranking**: Burst captures ranked via Milan native quality/overlap metrics (`getQuality`) and local contrast range before submission.
- **Sub-300ms Instant Unlock**: Direct SSM completion and immediate finger release reporting on image capture eliminate perceived latency without stalling on finger-lift polling.
- **Contact & Air Rejection Gate**: Active contact threshold (`active >= 64`) and quality checking keep untouched or faint touches out of templates.
- **Multi-Run PAM Stability**: Parked-TLS session reuse with idle-only gating across back-to-back claims, no desync or unknown-errors (tickets 38, 46, 49).
- **Verify-Retry Release Guard**: Rapid retries park in FDT-UP until a genuine finger release instead of burning attempts on a held finger (tickets 47, 49).
- **System Power Management**: Genuine `.suspend` and `.resume` vfunctions handle S3 sleep cleanly without wedging PAM.
- **Exhaustive Automated Test Suite**: 311 tests across 5 tiers (`bash tests/run_all_tests.sh` passes 311/311 in 16s).
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
