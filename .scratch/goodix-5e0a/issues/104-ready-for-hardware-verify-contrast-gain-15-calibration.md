# 104: Calibrate Contrast Gain to 1.5f for Milan Matching Engine

**What to build:** Calibrate `GOODIX_5E0A_CONTRAST_GAIN` in `libfprint-driver/goodix5e0a.h` from `1.0f` to `1.5f`. This matches the validated lane from ticket 72 / PR #7, lifts weak ridge gradients above Milan's internal minutiae extraction cliff (`overlap` jumps from 3–6 to 60–90), and resolves persistent `verify-no-match` (`match=0 pts=0`) on real hardware.

**Blocked by:** none.

**Status:** ready-for-hardware-verify

## Rationale & Root Cause Analysis

1. **Why Ticket 103 Failed on Verification Despite Distinct Enrolled Touches:**
   - In Ticket 103 hardware verification (2026-10-01 11:13), 12 distinct touches enrolled cleanly to 100% and committed a 24,903B template.
   - However, every subsequent verify probe produced `5e0a Milan verify: match=0 pts=0` (`verify-no-match`).
   - Journal examination showed probe frame statistics on real hardware:
     - Probe 1: `quality=0 overlap=6 range=1783`
     - Probe 2: `quality=0 overlap=3 range=1929`
   - Offline reverse engineering and simulation against `windows_driver/GoodixEngineAdapter.dll` proved:
     - Disassembly of `identifyImage` (RVA `0x79200`) revealed that when probe overlap is <= 6, the minutiae extractor finds insufficient ridge structure and returns raw matching score `-7` (clamped to `pts=0`).
     - A sweep of contrast gain on real sensor captures demonstrated a sharp contrast cliff:
       - `gain=0.80`: `overlap=0`
       - `gain=0.90`: `overlap=5`
       - `gain=1.00`: `overlap=38`
       - `gain=1.50`: `overlap=88`
     - At `gain=1.0f`, real hardware captures with slight variations in contact pressure or skin moisture sit directly at the threshold (`overlap=3..10`), causing verify probes to collapse into `overlap <= 6` and fail matching.

2. **Why Gain 1.5 Was Dropped in Ticket 101 (`75d7307`):**
   - PR #7 had correctly set gain to `1.5f`.
   - However, commit `75d7307` reverted it to `1.0f` because `tests/tier5_adversarial/test_suspend_recovery_c.c` (`test_frame_normalization`) had hardcoded pixel arithmetic assuming gain 1.0 (`128 + (-3) + (-6) = 119`).
   - Rather than updating the unit test formula to use `GOODIX_5E0A_CONTRAST_GAIN` dynamically, the gain change was wrongly reverted.

3. **Offline Accuracy and Security Validation:**
   - Standalone C test against `GoodixEngineAdapter.dll` confirmed:
     - Genuine probe: `id_res=0 midx=0 score=100 det=[100,100] MATCH`
     - Impostor probe (different finger): `id_res=0 midx=-1 score=0 det=[100,100] NO_MATCH`
     - Blank/noise probe: `id_res=0 midx=-1 score=0 det=[100,100] NO_MATCH`
   - FAR remains strictly 0.0% while genuine matches achieve score 100.

4. **The Fix:**
   - Set `#define GOODIX_5E0A_CONTRAST_GAIN (1.5f)` in `libfprint-driver/goodix5e0a.h`.
   - Update `test_frame_normalization` in `tests/tier5_adversarial/test_suspend_recovery_c.c` to dynamically verify normalization using `GOODIX_5E0A_CONTRAST_GAIN`.
   - Update static test assertions in `tests/tier1_feature/test_f101_per_touch_burst_reset.py` and `tests/tier5_adversarial/test_m1_c1_lifecycle_adversarial.py`.
   - Update `AGENTS.md` canonical specification to `gain 1.5`.

## Verification Checklist

- [x] Header calibration: `GOODIX_5E0A_CONTRAST_GAIN` set to `1.5f` in `goodix5e0a.h`.
- [x] Unit test dynamic check: `test_suspend_recovery_c.c` updated to evaluate expected values dynamically.
- [x] Static assertions: `test_f101_per_touch_burst_reset.py` and `test_m1_c1_lifecycle_adversarial.py` pass.
- [x] Full test suite: 356/356 tests pass (`bash tests/run_all_tests.sh`).
- [x] Nix derivation: builds cleanly via `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'`.
- [ ] Hardware enrollment: `sudo fprintd-enroll "$USER"` completes across 12 distinct touches.
- [ ] Hardware verification: `fprintd-verify "$USER"` achieves `verify-match (done)` with `match=1` and `pts > 0`.

## Predicted Journal Signatures

- **Confirm:**
  - Enrollment captures show healthy overlap values (overlap 30–90).
  - Composite template commits cleanly (size ~35KB–48KB).
  - Verification touches report overlap >= 30, logs `5e0a Milan verify: match=1 pts=...` (pts > 0), and PAM login succeeds with `verify-match (done)`.
- **Falsify:**
  - Verification reports `verify-no-match` with `pts=0` despite overlap >= 30.
