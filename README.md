# Goodix 27c6:5e0a Linux Driver

A reverse-engineered Linux driver for the **Goodix 27c6:5e0a** fingerprint scanner found on laptops such as the Realme Book Slim / Enhanced (MilanF / ChicagoH / GF5288 architecture), built for `libfprint` and `fprintd`.

---

## Features & Highlights

- **Native `libfprint` Integration**: Clean subclass of `FpiDeviceGoodixTls5xx` adhering to minimal, event-driven design principles.
- **Hardware FDT Touch & Release**: Uses hardware capacitive Finger Detection Trigger (`0x32` FDT DOWN, `0x34` FDT UP) with zero CPU-hogging polling loops.
- **TLS 1.2 PSK Encryption**: Implements the on-wire `TLS_PSK_WITH_AES_128_CBC_SHA256` protocol required by Goodix secure firmware.
- **NIST NBIS Minutiae Verification**: Extracts 23–25 minutiae per finger scan on hardware and passes Bozorth3 biometric match validation with scores of 13–15 (threshold: 12). See ticket 19 for the hardware run log.
- **Empty-Air Rejection Gate**: Prevents capturing ambient thermal noise into templates when the sensor is touched lightly or untouched.
- **Multi-Run PAM Stability**: Deterministic teardown and cancellable USB read loops prevent daemon hangs or timeouts across consecutive authentications.
- **Exhaustive Automated Test Suite**: 380 tests across 5 tiers covering feature isolation, boundaries, pairwise integration, system scenarios, and adversarial fuzzing.

---

## Repository Structure

```text
.
├── libfprint-driver/        # C driver source files for libfprint
│   ├── goodix5e0a.c         # Sensor-specific subclass driver
│   ├── goodix5e0a.h         # Sensor tables, opcodes, and constants
│   ├── goodix5xx.c / .h     # Base class for 5xx/5e0a Goodix sensors
│   ├── goodix.c / .h        # Low-level USB transport and protocol framing
│   └── goodixtls.c / .h     # In-process OpenSSL TLS 1.2 PSK engine
├── tests/                   # 380-test automated test suite
│   ├── run_all_tests.sh     # Master end-to-end test runner
│   ├── test_utils.py        # Authoritative protocol mock & framing library
│   ├── repo_paths.py        # Portable repo-root / external-tree paths
│   ├── tier1_feature/       # Feature unit tests in isolation
│   ├── tier2_boundary/      # Boundary value & buffer limits
│   ├── tier3_combination/   # Cross-feature pairwise integration
│   ├── tier4_realworld/     # PAM auth, enrollment, & lifecycle scenarios
│   └── tier5_adversarial/   # Fuzzing, fault injection, & stress tests
├── experiments/             # Reverse-engineering prototypes and sample data
├── specs/                   # Reverse-engineering gap specs (research, read-only)
├── docs/                    # Progress & architecture documentation
├── .scratch/goodix-5e0a/issues/  # Experiment tickets (status-tracked)
├── goodix_protocol.py       # Hardware USB bulk transport for experiments
├── libfprint-goodix.nix     # Nix package derivation for libfprint with driver
├── nixos-module.nix         # NixOS module configuration
└── 0001-Add-driver-support-for-Goodix-27c6-5e0a.patch  # Unified libfprint patch
```

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
