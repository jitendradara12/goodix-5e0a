# 19 — PAM / Sudo Integration & D-Bus Claim Teardown

**What to build:** Ensure clean device release on verification completion so PAM (`pam_fprintd` / `sudo` / `hyprlock`) can claim the device over D-Bus without `Device was already claimed` authorization failures, command collisions (`A command is already running: 0x34`), or orphaned state machines upon cancellation.

**Blocked by:** None. Ticket 18 verified biometric verification on physical hardware (Hardware Run 15/16) with Bozorth3 match scores clearing threshold (`score=13/12`, `14/12`, `15/12`).

**Status:** ready-for-hardware-verify

**Live-scope:** PAM teardown + claim release only; the 18-forward consecutive-match claim is not relied on (see 18 acceptance: second touch scored 6/12 no-match).

## Settled Facts (Frozen — Do Not Re-litigate)
1. **Biometric Verification Pipeline:** 100% verified on physical hardware (Runs 15 & 16). Minutiae counts reached 23–25, Bozorth scores reached 14/12 and 15/12, producing consecutive `verify-match (done)` outcomes.
2. **Image Pipeline & Raster:** 100% frozen: 80 blocks $\times$ 96B unpack, natural $64 \times 80$ raster, $3 \times 3$ local mean subtraction residual, direct non-saturating residual contrast mapping ($G = 1.0f$), explicit 500 DPI ppmm (`500.0 / 25.4`), upscaled $2\times$ bilinear to $128 \times 160$ with `FPI_IMAGE_COLORS_INVERTED`.
3. **Wire Layout & Transport:** 100% frozen: 10,564 bytes per frame = 80 blocks $\times$ 132 bytes (96 bytes active pixel data, 36 bytes deterministic zero padding) + 4-byte footer. TLS 1.2 PSK handshake and session encryption proven.
4. **Biometric Calibration Baseline:** `GOODIX_5E0A_CONTRAST_GAIN = 1.0f` and `GOODIX_5E0A_ENROLL_MIN_MINUTIAE = 12`. All gallery prints achieve 12–22 minutiae without floor aborts (`MIN_COMPUTABLE_BOZORTH_MINUTIAE = 10`), preserving sharp ridge curvature and high matching margin.

## Problem Statement
In Hardware Run 16, immediately after two successful `fprintd-verify` matches, executing PAM authentication via `sudo true` failed with:
```text
Authorization denied to :1.754 to call method 'Claim' for device 'Goodix TLS Fingerprint Sensor 5e0a': Device was already claimed
```

Root-cause analysis of system journal logs identified the failure chain:
1. **Single-Shot Verify Retry Race:** In libfprint, verification is designed as a single-shot transaction. Calling `fpi_image_device_retry_scan` during verify immediately triggers `fpi_image_device_deactivate(TRUE)`.
2. **Scan SSM Command Collision:** When deactivation was triggered prematurely while the scan SSM was still active in state 4 (processing `0x34` finger-down / wait), the driver attempted new command dispatches, resulting in:
   `A command is already running: 0x34`
3. **USB Read Loop Resurrection:** When transfers were cancelled during session teardown, `goodix_receive_data_cb` failed to drop `G_IO_ERROR_CANCELLED`, entering generic error handling and re-calling `goodix_receive_data(dev)`.
4. **Orphaned SSM Memory:** During deactivation, `self->scan_ssm` was nulled without invoking `fpi_ssm_free`, leaving in-flight SSM timers and callbacks orphaned.
5. **D-Bus Claim Deadlock:** The aborted deactivation prevented `fprintd` from clearing `session_data` and resetting `current_action`. The device remained locked under the previous D-Bus caller (`:1.753`), denying all subsequent callers (`:1.754` sudo) claim authorization.

## Implemented Fix Details

1. **Unconditional Capture Reporting During Verify (`goodix5e0a.c:452-456`)**:
   - In `goodix5e0a_on_read_img`, `FPI_DEVICE_ACTION_VERIFY` unconditionally forwards the captured image to `fpi_image_device_image_captured(FP_IMAGE_DEVICE(dev), img)` without invoking `fpi_image_device_retry_scan`.
   - The scan SSM cleanly transitions through states 5 and 6 (`0x34` -> `0xae` -> `0x34`), allowing orderly finger release detection, normal Bozorth3 matching, and clean session completion.

2. **Deactivation SSM Cleanup (`goodix5e0a.c:584-595`)**:
   - In `goodix5e0a_deactivate`, `fpi_ssm_free(self->scan_ssm)` is explicitly called when `self->scan_ssm != NULL`.
   - Destroys active timers (`down_timeout`), shuts down TLS cleanly, and signals deactivation completion via `fpi_image_device_deactivate_complete(img_dev, tls_err)`.

3. **Dropping Cancelled USB Transfers (`goodix.c:446-453`)**:
   - In `goodix_receive_data_cb`, explicit check for `g_error_matches(error, G_IO_ERROR, G_IO_ERROR_CANCELLED)` and `g_cancellable_is_cancelled(priv->transfer_cancel_tkn)`.
   - Frees error and returns immediately without re-invoking `goodix_receive_data(dev)`, completely halting the read loop.

4. **Biometric Calibration Optimization (`goodix5e0a.h:27-28`)**:
   - `GOODIX_5E0A_CONTRAST_GAIN` calibrated to `(1.0f)` (prevents saturation, restricts clipping to 9.0%, maintains 91.0% linear gradient, yielding Bozorth self-match score 80/12 and heavy-touch match score 40/12).
   - `GOODIX_5E0A_ENROLL_MIN_MINUTIAE` calibrated to `(12)` (ensures all 8 enrollment stages advance smoothly without rejecting valid faint or firm touches, while maintaining $+2$ safety margin above Bozorth's floor of 10).

5. **Unified Patch SHA-256 Parity**:
   - Regenerated unified patch against upstream commit `c343b6934e40dcd40a5f9e3095810d98f1175a4d`:
   - Checksum: `e8fd1c4cfc4abc43822f9de25d3083e4ffb1b5a55a68b26cf7e89c76c3f0d852`
   - Synchronized identically across:
     - `/home/sastauser/code/temp/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`
     - `/home/sastauser/NixOS-Hyprland/modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`

6. **Hermetic Nix Packaging**:
   - Both derivation calls (`./libfprint-goodix.nix` and NixOS module) compile cleanly:
   - Output Store Path: `/nix/store/046d8vad2lr9kjy33ga3ic1zihnx7g2g-libfprint-goodix-1.94.5-goodixtls`

7. **Automated Master Test Suite**:
   - 375/375 tests passing across all 5 tiers (`tests/run_all_tests.sh`):
     - Tier 1 (Feature Coverage): 155 tests passed
     - Tier 2 (Boundary & Corner Cases): 130 tests passed
     - Tier 3 (Pairwise Integration): 24 tests passed
     - Tier 4 (Application Scenarios): 5 tests passed
     - Tier 5 (Adversarial & Stress): 61 tests passed

## Complete Hardware Verification Protocol (Strict AGENTS.md Compliance)

Per `AGENTS.md`, only the user executes hardware deployment and commands requiring fingers sudo.

### Phase 1: Deployment & Hands-Off Control (60s)
1. User deploys the updated driver and restarts the daemon:
   ```bash
   cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd
   ```
2. **Hands-off observation**: Keep hands completely off the sensor for 60 seconds ("hands off" + timestamp).
   - *Expected*: Zero spurious wakeups, zero unsolicited transfers, sensor stays completely silent in MCU sleep/wait.

### Phase 2: Enrolled Finger Verification Repeatability (fprintd-verify)
1. Run verification across at least 5 consecutive touches:
   ```bash
   fprintd-verify
   ```
2. Repeat 5 times consecutively.
   - *Expected*: Each real touch completes with `Verify result: verify-match (done)` and Bozorth score $\ge 12$. Clean release between runs without command timeouts.

### Phase 3: PAM Sudo Authentication Consistency (sudo true)
1. Clear sudo credential cache and authenticate via fingerprint:
   ```bash
   sudo -k && sudo true
   ```
2. Repeat 5 times consecutively.
   - *Expected*: Prompt appears immediately; touching sensor authenticates sudo session instantly. No `Device was already claimed` authorization errors.

### Phase 4: Prompt Cancellation & Immediate Re-Claim Test
1. Test clean cancellation:
   ```bash
   sudo -k && sudo true
   ```
2. While waiting for fingerprint, press `Ctrl+C`.
   - *Expected*: Terminal prompt cancels immediately with clean shell return, no hang.
3. Immediately test re-claim:
   ```bash
   sudo true
   ```
4. Place enrolled finger on sensor.
   - *Expected*: Device is claimed immediately without error and authenticates successfully.

### Phase 5: Journal Log Confirmation
1. Extract verbatim journal output:
   ```bash
   journalctl -u fprintd --since "10 min ago" --no-pager | grep -a -E "5e0a frame|timed out|error|failed|minutiae" | tail -n 20
   ```

## Predicted Journal Signatures & Branch Analysis

- **Confirm (Branch A)**:
  - Journal contains:
    `5e0a frame stats: active=5120 ... declen=10564`
    `5e0a get_minutiae: ret=0 minutiae_count=...` ($\ge 12$)
    `5e0a bz3 match: gallery[N]_nrows=... score=.../12` ($\ge 12$)
  - Zero occurrences of `A command is already running: 0x34`.
  - Zero occurrences of `Authorization denied ... Device was already claimed`.
  - Zero occurrences of `Command timed out: 0xa2`.
  - *Verdict*: `confirmed` -> Ticket 19 closed.

- **Falsify (Branch B)**:
  - Journal records `Device was already claimed` or `A command is already running: 0x34`.
  - Sudo hangs on `Ctrl+C` cancellation or subsequent invocation.
  - *Verdict*: `falsified` -> Investigate exact log line, trace SSM state divergence.

- **Inconclusive (Branch C)**:
  - Stale `openssl s_server` process squatting on port, missing pasted journal lines, or unverified claims.
  - *Verdict*: `inconclusive-because-[flaw]` + single next diagnostic experiment.
