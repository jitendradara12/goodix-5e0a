# E2E Test Infra: Goodix 27c6:5e0a Fingerprint Sensor Driver

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing.

## Feature Inventory & Test Coverage
| # | Feature | Source (Requirement) | Tier 1 (Coverage) | Tier 2 (Boundaries) | Tier 3 (Pairwise) |
|---|---------|----------------------|:-----------------:|:-------------------:|:-----------------:|
| 1 | USB Interface & Endpoint Binding (0x01/0x83) | ORIGINAL_REQUEST §Verification | 5 | 5 | ✓ |
| 2 | NOP Buffer Flush & Command Serialization | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 3 | Read Register & Chip ID (0x0000) | ORIGINAL_REQUEST §Verification | 5 | 5 | ✓ |
| 4 | Read OTP & Firmware Query (GFUSB_GM168SEC_APP_10036) | ORIGINAL_REQUEST §Verification | 5 | 5 | ✓ |
| 5 | Preset PSK Status Read (0xbb020001) | ORIGINAL_REQUEST §Verification | 5 | 5 | ✓ |
| 6 | TLS 1.2 PSK Handshake (PSK-AES128-CBC-SHA256) | ORIGINAL_REQUEST §Verification | 5 | 5 | ✓ |
| 7 | MCU 256-Byte Config Upload (CONFIG_52XD) | ORIGINAL_REQUEST §Verification | 5 | 5 | ✓ |
| 8 | Sensor Register 0x022c Gain Configuration | ORIGINAL_REQUEST §Verification | 5 | 5 | ✓ |
| 9 | Chip Enable & Driver State Transition (0x96, 0xc4) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 10 | Hardware FDT Mode Configuration (0x36) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 11 | Hardware FDT DOWN Touch Detection (0x32, byte 26=0x01) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 12 | Hardware FDT UP Release Detection (0x34, byte 26=0x00) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 13 | Elimination of Software Polling Loops (0% CPU idle) | ORIGINAL_REQUEST §R1, §R2 | 5 | 5 | ✓ |
| 14 | Frame Acquisition & TLS Decryption (0x20) | ORIGINAL_REQUEST §Verification | 5 | 5 | ✓ |
| 15 | 12-bit Pixel Unpacking & 8-bit Normalization | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 16 | Bilinear Demosaicing (80x64 -> 160x128) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 17 | Deterministic USB Read Loop Cancellation | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 18 | Non-blocking TLS Socket Teardown (SHUT_RDWR) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 19 | Protocol State Reset on Deactivation (0xa2 elimination) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 20 | Meson / Ninja Build System Compilation | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 21 | NixOS Flake & Derivation Patch Integrity | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 22 | Hermetic nix-build & Flake Evaluation | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 23 | Multi-Run PAM Verification & Enrollment Reliability | ORIGINAL_REQUEST §R3, §Acceptance | 5 | 5 | ✓ |
| 24 | Adversarial Edge-Case Hardening (Empty Air, Rapid Abort) | ORIGINAL_REQUEST §Acceptance | 5 | 5 | ✓ |

## Test Architecture
- **Test Runner Location**: `/home/sastauser/code/temp/goodix/tests/run_all_tests.sh`
- **Pass/Fail Semantics**: All test scripts must exit with code 0 on pass, non-zero on failure.
- **Directory Layout**:
  - `tests/tier1_feature/` (Happy path unit/component tests)
  - `tests/tier2_boundary/` (Boundary, limits, timeout, empty air tests)
  - `tests/tier3_combination/` (Pairwise interaction, cancel-during-touch, reconnect tests)
  - `tests/tier4_realworld/` (End-to-end PAM authentication, multi-stage enrollment, consecutive verify loops)
  - `tests/tier5_adversarial/` (Adversarial fuzzing, memory leak audit, USB fault injection)

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Multi-stage Enrollment (`fprintd-enroll`) without false air advances | F1, F6, F7, F10, F11, F12, F14, F15, F16, F23 | High |
| 2 | Consecutive Sudo PAM Verifications (5x back-to-back `fprintd-verify`) | F1, F2, F6, F11, F12, F17, F18, F19, F23 | High |
| 3 | Lockscreen PAM Cancelation & Instant Re-auth (hyprlock / swaylock) | F11, F17, F18, F19, F23, F24 | High |
| 4 | Empty Air Finger Touch Rejection (0 false triggers over 60s idle) | F10, F11, F13, F24 | Medium |
| 5 | Hermetic Nix Package Build & Service Configuration Evaluation | F20, F21, F22 | Medium |

## Coverage Thresholds
- Tier 1: ≥ 120 test cases (5 × 24 features)
- Tier 2: ≥ 120 test cases (5 × 24 boundary conditions)
- Tier 3: ≥ 24 pairwise combination test cases
- Tier 4: ≥ 5 realistic application scenarios
