# 86: Eliminate 2000ms CMD 0xd4 TLS Established Timeout Delay

**What to build:** In `goodix_send_tls_successfully_established` (`goodix.c`), change CMD `0xd4` (`GOODIX_CMD_TLS_SUCCESSFULLY_ESTABLISHED`) from `reply = TRUE` with hardcoded 2000ms timeout to `reply = FALSE` with `GOODIX_TIMEOUT` (1000ms). The Goodix MCU acknowledges CMD 0xd4 in ~16ms with standard `GOODIX_CMD_ACK` (0xb0) and sends no subsequent data packet (matching Python `tls_successfully_established` which only checks ACK). Setting `reply = FALSE` allows `goodix_receive_ack` to complete the command immediately upon ACK receipt, eliminating an artificial 2.000-second pause on every TLS bring-up.

**Blocked by:** None.

**Status:** ready-for-hardware-verify

## Acceptance Criteria

- [x] In `libfprint-driver/goodix.c:goodix_send_tls_successfully_established`: pass `reply = FALSE` and `timeout_ms = GOODIX_TIMEOUT` (1000ms) to `goodix_send_protocol`.
- [x] In `libfprint-driver/goodix.c:on_tls_successfully_established`: handle genuine errors rather than discarding errors.
- [x] Unit test `test_f86_tls_established_ack.py` passes hermetically.
- [x] Full test suite (319 tests) passes cleanly across all 5 tiers.
- [x] Unified patch `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` and NixOS module patch stay byte-identical.
- [x] Derivation builds cleanly via `nix-build`.
- [ ] Verified on hardware: `sudo -k; time fprintd-verify -f right-index-finger` total latency drops from ~2.85s down to ~0.65–0.85s (2.000s delay eliminated).
- [ ] Verified on hardware: Time delta between `Running command: 0xd4` and `HANDSHAKE DONE` drops from 2001ms to ~16ms.
- [ ] Rule-7 smoke check passes: zero `timed out|Invalid ACK|verify-unknown-error|failed to`.

## Context & Evidence

- In recent user hardware tests, `sudo -k; time fprintd-verify -f right-index-finger` repeatedly took ~2.858s, 2.857s, 2.856s.
- Microsecond journal inspection (`journalctl -u fprintd -o short-precise`) revealed:
  ```
  Sep 16 20:18:14.188923: Running command: 0xd4
  Sep 16 20:18:14.205342: Got protocol msg
  Sep 16 20:18:14.205348: got ack
  Sep 16 20:18:16.190421: HANDSHAKE DONE
  ```
  The MCU sent the ACK in 16.4ms, but `HANDSHAKE DONE` did not fire until exactly 2.0015s later.
- Root cause: In `goodix_send_protocol`:
  - `reply = FALSE`: Command only expects an ACK. When `goodix_receive_ack` receives `GOODIX_CMD_ACK` (0xb0), it completes the command immediately via `goodix_receive_done` and disarms the timeout.
  - `reply = TRUE`: Command expects an ACK followed by a separate data packet with payload.
- In legacy Goodix code, CMD 0xd4 had `reply = TRUE` and a hardcoded 2000ms timeout with a comment:
  `// todo: work out why it always times out for this but not the python driver`
  In `legacy-experiments/vendor/goodix.py:672`, the python driver only called `check_ack(...)` and never waited for a second packet. Because the C driver passed `reply = TRUE`, it waited for a data packet that never exists until the 2000ms timer fired.

## Implementation Details

One variable: CMD 0xd4 `reply` flag and timeout in `goodix_send_tls_successfully_established`.

- `libfprint-driver/goodix.c`:
  - In `goodix_send_tls_successfully_established`: Pass `GOODIX_TIMEOUT` and `FALSE` for `reply`.
  - In `on_tls_successfully_established`: Propagate error if `error != NULL`.
- `tests/tier1_feature/test_f86_tls_established_ack.py`:
  - Hermetic structural tests verifying `reply=FALSE`, no hardcoded 2000ms timeout, and error propagation.
- `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`:
  - Synced patch hunks for `goodix.c`.

## Build and Test Verification

- **Nix Derivation Build:**
  ```bash
  nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'
  ```
  Output: `/nix/store/ixm4xwrhlz8a9d56dzzsr48xphpy76ss-libfprint-goodix-1.94.5-goodixtls-5e0a` (Exit: 0).
- **Master Test Runner:**
  ```bash
  bash tests/run_all_tests.sh
  ```
  Total Tests Passed: 319, Failed: 0, Skipped: 1. All tiers passed!

## Hardware Verify Protocol (user-only; agent has no fingers/sudo)

1. Deploy driver:
   ```bash
   cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd
   sudo systemctl set-environment G_MESSAGES_DEBUG=all
   sudo systemctl restart fprintd
   ```
2. Run benchmark:
   ```bash
   sudo -k; time fprintd-verify -f right-index-finger
   ```
3. Inspect journal:
   ```bash
   journalctl -u fprintd -o short-precise --since "1 min ago" --no-pager | grep -a -E "Running command: 0xd4|got ack|HANDSHAKE DONE|Running command: 0x90|5e0a D32 touch|fast-path"
   sudo systemctl unset-environment G_MESSAGES_DEBUG
   ```

## Predicted Journal Signatures

- **Confirm:**
  - Journal logs:
    ```
    Running command: 0xd4
    got ack
    HANDSHAKE DONE
    Running command: 0x90
    ```
    Time between `Running command: 0xd4` and `HANDSHAKE DONE` is ~16ms (NOT 2001ms).
  - Total `time fprintd-verify` drops from ~2.85s to ~0.65–0.85s (or < 100ms if pre-holding finger).
- **Falsify:**
  - `failed to send TLS established` error or MCU rejects subsequent 0x90 config upload.
- **Inconclusive-because-[flaw]:**
  - fprintd was not restarted after rebuild or `G_MESSAGES_DEBUG` was unset during run.
