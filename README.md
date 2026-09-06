# Goodix 27c6:5e0a Linux Driver

A reverse-engineered Linux driver for the **Goodix 27c6:5e0a** fingerprint scanner found on laptops such as the Realme Book Slim / Enhanced (MilanF / ChicagoH / GF5288 architecture), built for `libfprint` and `fprintd`.

---

## Features & Highlights

- **Native `libfprint` Integration**: Clean subclass of `FpiDeviceGoodixTls5xx` adhering to minimal, event-driven design principles.
- **Hardware FDT Touch & Release**: Uses hardware capacitive Finger Detection Trigger (`0x32` FDT DOWN, `0x34` FDT UP) with sampled channel-energy gating (short silent re-poll on idle).
- **TLS 1.2 PSK Encryption**: Implements the on-wire `TLS_PSK_WITH_AES_128_CBC_SHA256` protocol required by Goodix secure firmware with a static host key (no on-device provisioning; ticket 26 instrumentation stripped as upstream-clean).
- **NIST NBIS Minutiae Verification**: Extracts 23–25 minutiae per finger scan on hardware and passes Bozorth3 biometric match validation with scores of 13–15 (threshold: 12; Tickets 18, 35).
- **Sub-300ms Instant Unlock**: Direct SSM completion and immediate finger release reporting on image capture eliminate perceived latency without stalling on finger-lift polling.
- **Empty-Air Rejection Gate**: Touch-gated capture plus an enrollment minutiae floor keep untouched or faint touches out of templates.
- **Multi-Run PAM Stability**: Deterministic teardown and cancellable USB read loops prevent daemon hangs or timeouts across consecutive authentications.
- **System Power Management**: Genuine `.suspend` and `.resume` vfunctions handle S3 sleep cleanly without wedging PAM.
- **Exhaustive Automated Test Suite**: 400 tests across 5 tiers covering feature isolation, boundaries, pairwise integration, system scenarios, and adversarial fuzzing.
- **Hermetic NixOS Flake & Derivation**: Automated compilation, patch validation, and systemd service generation via standard Nix workflows.

---

## Repository Structure

```text
goodix/
├── libfprint-driver/        # Production C driver sources for libfprint
│   ├── goodix5e0a.c         # Model-specific driver implementation
│   ├── goodix5e0a.h         # Model constants, registers & tables
│   ├── goodix5xx.c/h        # Goodix TLS 5xx base class
│   └── goodixtls.c/h        # TLS 1.2 PSK transport layer
├── tests/                   # 5-Tier Master End-to-End Test Suite
│   ├── run_all_tests.sh     # Master end-to-end test runner
│   ├── test_utils.py        # Authoritative protocol mock & framing library
│   ├── repo_paths.py        # Portable repo-root / external-tree paths
│   ├── tier1_feature/       # Feature unit tests in isolation (165 tests)
│   ├── tier2_boundary/      # Boundary value & buffer limits (130 tests)
│   ├── tier3_combination/   # Cross-feature pairwise integration (24 tests)
│   ├── tier4_realworld/     # PAM auth, enrollment, & lifecycle scenarios (5 tests)
│   └── tier5_adversarial/   # Fuzzing, fault injection, & stress tests (63 tests)
├── experiments/             # Reverse-engineering prototypes and sample data
├── specs/                   # Reverse-engineering gap specs (research, read-only)
├── docs/                    # Progress & architecture documentation
├── .scratch/goodix-5e0a/issues/  # Experiment tickets (01–37, status-tracked)
├── goodix_protocol.py       # Hardware USB bulk transport for experiments
├── libfprint-goodix.nix     # Nix package derivation for libfprint with driver
├── nixos-module.nix         # NixOS module configuration
└── 0001-Add-driver-support-for-Goodix-27c6-5e0a.patch  # Unified libfprint patch
```

Upstream `libfprint` tree with canonical `umockdev` replay fixtures is maintained at `/home/sastauser/code/temp/libfprint-upstream` (`test-5e0a` branch).

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
