# 19 — PAM / Sudo Integration & D-Bus Claim Teardown

**What to build:** Ensure clean device release on verification completion so PAM (`pam_fprintd` / `sudo`) can claim the device over D-Bus without `Device was already claimed` authorization failures.

**Blocked by:** None. Ticket 18 was verified on hardware with two consecutive `verify-match (done)` results (`score=15/12`, `score=14/12`).

**Status:** ready-for-agent

## Settled Facts (Frozen — Do Not Re-litigate)
1. **Biometric Verification:** 100% verified on physical hardware (Run 16). Minutiae counts reached 23–25, Bozorth scores reached 14/12 and 15/12, producing two consecutive `verify-match (done)` outcomes.
2. **Image Pipeline & Raster:** 100% frozen: 80 blocks $\times$ 96B unpack, natural $64 \times 80$ raster, 3x3 local mean subtraction, direct residual contrast ($G=1.0$), explicit 500 DPI ppmm.
3. **Enrollment Quality Gate:** 100% frozen: `GOODIX_5E0A_ENROLL_MIN_MINUTIAE = 15`. All gallery prints have 17–22 minutiae.

## Problem Statement
In Hardware Run 16, immediately after two successful `fprintd-verify` matches, running `sudo` failed with:
```text
Authorization denied to :1.754 to call method 'Claim' for device 'Goodix TLS Fingerprint Sensor 5e0a': Device was already claimed
```
Journal revealed:
1. Touch 3 had `minutiae_count = 13 < 15`, calling `fpi_image_device_retry_scan`.
2. In libfprint, verify is single-shot: calling `retry_scan` during verify immediately invokes `deactivate(TRUE)`.
3. The scan SSM was still active in state 4 (running `0x34`), causing command collision:
   `A command is already running: 0x34`
4. The aborted deactivation left the D-Bus device claimed by the prior process `:1.753`. Subsequent `sudo` invocations were denied claim authorization.

## Implemented Fix (Build f7a1b29)
1. Removed `fpi_image_device_retry_scan` from `FPI_DEVICE_ACTION_VERIFY`. Verify mode now always passes the image to `fpi_image_device_image_captured` for normal matching and clean teardown.
2. Verified all 40 unit tests pass.
3. Synchronized patch `b2528706bfa2a3502c7fdd15debf12b97377366fc0198af8648ddf678cf620b8`.

## Verification Protocol
1. Deploy updated patch:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Test verify in client:
   `fprintd-verify`
3. Test authentication in sudo:
   `sudo true`
