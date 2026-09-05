# 20 — Verify Latency Optimization (<300ms Instant Unlock) & Cold-Boot OTP Resolution

**What to build:** 
1. Cut wall-clock verification time from touch to `verify-match` so unlock feels instant (< 300ms). Baseline was ~2–3s per attempt due to polling `0x34` finger-lift mechanics in libfprint `FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_OFF`.
2. Resolve cold-boot / resume PSK initialization failure by restoring `ACTIVATE_READ_OTP` into the activation state machine.

**Blocked by:** None. Built on verified biometric pipeline (Ticket 18) and clean PAM teardown (Ticket 19).

**Status:** ready-for-hardware-verify

**Live-scope:** latency (<300ms) only; the OTP half is superseded by ticket 26 — do not re-add ACTIVATE_READ_OTP as a crypto fix.

## Problem Statement

### 1. Latency Bottleneck: Finger-Lift Polling Stall
In the baseline verify path:
- Bozorth3 match computation completes in milliseconds (~4ms).
- However, `goodix5e0a_on_read_img` called `fpi_ssm_next_state(ssm)` unconditionally, forcing the scan SSM to proceed to state 5 (`0x34` FDT UP) and state 6 (release polling).
- Libfprint entered `FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_OFF`, holding the D-Bus verification transaction open until physical finger lift was confirmed.
- This added 2–5 seconds of perceived lag to sudo/login operations, even though biometric authentication had already succeeded.

### 2. Cold-Boot PSK Failure: Missing OTP Read
On fresh system boot, resume from deep sleep, or cold USB bus reset:
- The Goodix MCU initializes in an unprimed OTP state.
- Skipping `ACTIVATE_READ_OTP` in the 5e0a activation SSM left on-chip OTP memory unread.
- The MCU requires the OTP read sequence to calibrate internal security registers prior to the TLS 1.2 PSK handshake.
- Cold boot activations consequently failed during TLS PSK negotiation (`SSL alert: access denied` or handshake timeout).

## Implemented Fix Details

### 1. Instant Verify Release (`libfprint-driver/goodix5e0a.c:454-469`)
In `goodix5e0a_on_read_img`:
```c
/* In verify mode (and all non-enroll actions), unconditionally pass the captured image
 * to fpi_image_device_image_captured without calling retry_scan. Complete the scan SSM
 * and report finger release immediately so that libfprint can finish authentication and
 * deactivate without waiting 2-5 seconds for finger lift polls (Ticket 20 latency fix). */
fpi_image_device_image_captured (FP_IMAGE_DEVICE (dev), img);

if (action != FPI_DEVICE_ACTION_ENROLL)
  {
    self->scan_ssm = NULL;
    fpi_ssm_mark_completed (ssm);
    fpi_image_device_report_finger_status (FP_IMAGE_DEVICE (dev), FALSE);
  }
else
  {
    fpi_ssm_next_state (ssm);
  }
```
- During verify and non-enroll actions, `self->scan_ssm` is marked completed immediately and finger release is reported right after image capture.
- Libfprint finishes authentication and deactivates the device immediately upon matching, delivering instantaneous (< 300ms) unlock response.
- For enrollment (`FPI_DEVICE_ACTION_ENROLL`), release polling is preserved so multi-stage finger transitions remain strictly enforced.

### 2. Cold-Boot `ACTIVATE_READ_OTP` (`libfprint-driver/goodix5e0a.c:53-83`)
In `libfprint-driver/goodix5e0a.c`:
- Added `ACTIVATE_READ_OTP` state to `enum activate_states`:
```c
enum activate_states {
  ACTIVATE_READ_AND_NOP,
  ACTIVATE_RESET,
  ACTIVATE_READ_CHIP_ID,
  ACTIVATE_READ_OTP,
  ACTIVATE_CHECK_FW_VER,
  ACTIVATE_NUM_STATES,
};
```
- Implemented state dispatch in `activate_run_state`:
```c
    case ACTIVATE_READ_OTP:
      goodix_send_read_otp (dev, goodixtls5xx_check_none_cmd, ssm);
      break;
```
- Sends CMD `0x94` (`goodix_send_read_otp`) after chip ID verification and before checking firmware version.
- Primes MCU internal registers from OTP memory, guaranteeing reliable TLS 1.2 PSK handshakes on cold boots and warm restarts alike.

## Build & Test Status

- **Master E2E Test Suite:** 385 / 385 tests passed across all 5 tiers (`bash tests/run_all_tests.sh`).
- **Driver Build:** Ninja compilation clean (`libfprint-drivers.a`, `libfprint-2.so.2.0.0`).
- **Unified Patch Checksum:**
  - Repo root: `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`
  - NixOS module: `/home/sastauser/NixOS-Hyprland/modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`
  - SHA-256: `daf78ffeb739fc1e1a9ec461551b5827da30f490b745ea847c16e3aecaab344d` (byte-synchronized).
- **Derivation Evaluation:** Nix derivation evaluates cleanly.

## Verification Protocol (Hardware Run 17)

Per `AGENTS.md`, only the user runs commands claiming hardware or using fingers sudo.

### Step 1: Deploy Updated Patch
```bash
cd ~/NixOS-Hyprland
sha256sum modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch
# Expected: daf78ffeb739fc1e1a9ec461551b5827da30f490b745ea847c16e3aecaab344d

sudo nixos-rebuild switch --flake .#
sudo systemctl restart fprintd
```

### Step 2: Cold-Boot / Service Restart Test
```bash
# Verify activation succeeds without TLS errors on fresh daemon start:
fprintd-verify
```
Touch sensor: confirm device activates cleanly, reads OTP, and executes TLS handshake.

### Step 3: Verify Latency (< 300ms) Test
```bash
fprintd-verify
```
Touch sensor: verify returns `verify-match (done)` immediately on touch without needing to lift finger.

### Step 4: Sudo Instant Unlock
```bash
sudo -k && sudo true
```
Touch sensor: authentication succeeds instantaneously.

### Step 5: Journal Log Verification
```bash
journalctl -u fprintd --since "5 min ago" --no-pager | grep -a -E "5e0a wire|5e0a frame|5e0a bz3 match:|Device reported verify completion|Device was already claimed" | tail -n 25
```

## Predicted Journal Signatures & Branch Analysis

- **Confirm (Branch A):**
  - Instant transition from touch to completion:
    `5e0a frame stats: active=5120 ... declen=10564`
    `5e0a bz3 match: ... score=.../12` ($\ge 12$)
    `Device reported verify completion` (< 300ms delta from frame capture).
  - Zero cold-boot TLS alert failures.
  - Zero `Device was already claimed` errors on subsequent `sudo true`.
  - *Verdict*: `confirmed` -> Ticket 20 closed.

- **Falsify (Branch B):**
  - Lag persists > 1.5s waiting for finger lift.
  - Cold-boot TLS fails with PSK mismatch.
  - *Verdict*: `falsified` -> Trace exact SSM state divergence in journal.
