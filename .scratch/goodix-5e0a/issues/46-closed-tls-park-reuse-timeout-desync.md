# 46 — Parked TLS session reuse command timeout and desync during rapid verify/enroll

**What to build:** Eliminate `Command timed out: 0x96` and `Command timed out: 0x32`
errors during parked TLS session reuse across back-to-back claims (identify-for-enroll,
consecutive verifications, PAM multi-factor checks).

**Root cause analysis:**
1. In Ticket 38 (`goodix5e0a_deactivate`), when a claim ends while the sensor is
   waiting for touch (`SCAN_5E0A_FDT_DOWN` 0x32), the host frees `scan_ssm`, resets
   local state (`goodix_reset_state`), and stops the read loop (`goodix_stop_read_loop`),
   parking the session (`tls_parked = TRUE`). However, the physical MCU is never notified
   to cancel FDT DOWN mode or return to idle.
2. When the next claim arrives immediately (e.g. `parked 0.0s` or a few seconds later),
   `dev_activate` restarts the read loop and sends `GOODIX_CMD_QUERY_MCU_STATE (0xae)`.
3. The MCU responds to the pending state / probe, but an ACK arrives out-of-order or
   duplicated, triggering `Invalid ACK command: 0xae` right as the host enters `0x96`
   (enable chip).
4. Because the ACK is dropped and the MCU is desynced, CMD `0x96` times out:
   `failed to enable chip: Command timed out: 0x96 (code: 24)`.
   Or, if `0x96` succeeds, the subsequent scan enters `SCAN_5E0A_FDT_DOWN` and times out:
   `5e0a failed to scan: Command timed out: 0x32 (code: 24)`.
5. These timeouts cause `fprintd` to report `verify-unknown-error (done)` to client
   applications (PAM, hyprlock, fprintd-verify).
6. The failure marks the session dirty, triggers a USB reset, and forces a full cold
   activation on the next attempt.

**Status:** closed

**Verdict:** confirmed on hardware 2026-09-09 (deployed driver)

**Live-scope:** session reuse teardown/flush and in-flight cancellation only.
No biometric changes, no threshold changes.

## Implementation (2026-09-09)

One variable: park eligibility pinned to idle deactivation in
`goodix5e0a_deactivate` (`libfprint-driver/goodix5e0a.c`).
`scan_was_active = (self->scan_ssm != NULL)` captured before the SSM free;
park requires `goodix_tls_is_alive && warm_ok && !scan_was_active`.
A non-idle teardown logs `5e0a park invalidated: scan SSM in-flight at
deactivate, clean bring-up` (`fp_dbg`, needs debug env) and falls through
to the destroy branch for a clean bring-up (fresh warm/full handshake, no
parked reuse). `warm_ok` untouched — next claim does a fresh handshake,
not a desynced reuse. `retry_guard` path unaffected: post-image deactivates
have `scan_ssm == NULL`, so 47's guard still parks.

## Hardware result 2026-09-09 — CONFIRMED, ticket closed

5 rapid back-to-back `fprintd-verify` (incl. `verify-match` on right-ring-finger):
`grep -E "timed out|Invalid ACK|verify-unknown-error" | wc -l` → `0`.
Reuse line present: `5e0a TLS session reused (parked 0.0s, gen=11)` — the
exact 0.0s-gap scenario from the root-cause analysis now reuses cleanly.

## Predicted journal signatures (pre-run; confirm branch matched)

- Confirm: 5x back-to-back `fprintd-verify` show zero `Command timed out:
  0x96`, zero `Command timed out: 0x32`, zero `Invalid ACK command: 0xae`,
  zero `verify-unknown-error`. Claim cancelled mid-FDT_DOWN logs the park-
  invalidated line (debug env) then `5e0a warm path` or `5e0a warm expired`
  + clean `Chip enabled!`.
- Falsify: `Invalid ACK 0xae` + `0x96`/`0x32` timeouts persist on rapid
  reuse despite idle-only parking → desync source is stale USB pipe bytes,
  not park gating; next experiment is a pre-probe flush, not wider gating.

## Build breakage 2026-09-09 (fixed same day)

Regenerating the unified patch via `git -C /tmp/libfprint-goodix diff
c343b69` broke `nixos-rebuild`: the NixOS module fetched
`jitendradara12/libfprint@a5029fe`, a base that already carries
`goodix5e0a.c`, so new-file sections failed (`5 out of 5 hunks FAILED` on
`goodix5xx.h`, reversed `goodix_proto.h`/`goodixtls.c`, failed
`meson.build`). One patch cannot serve two bases. Fix: module src pointed
at `goodix-fp-linux-dev@c343b69` (same rev+hash as repo `libfprint-
goodix.nix`; old fork rev recorded in the module nix comment). Verified:
module derivation builds (`/nix/store/kcw7wcsfrj6spf8qd3yw6kgxvr6l2mih-
libfprint-goodix-1.94.5-goodixtls`, `strings` shows `park invalidated`);
repo `nix-build` builds; `test_f25`, `test_f21`, tier5 parity green
(stale `054aa1cf` pin refreshed to `2da873c5` — was already red at HEAD).

## Settled facts (do not re-litigate)

1. Deactivating an image device while it is not idle (`AWAIT_FINGER_ON`) leaves
   hardware FDT DOWN active on the MCU unless explicitly cancelled.
2. An uncancelled command produces dangling ACKs/replies on the USB bulk pipe
   that poison the next read loop lifecycle.
3. `fprintd-verify` and `fprintd-enroll` frequently make back-to-back D-Bus calls
   (e.g., identify check before enroll, rapid verify retries).

## Target fix sketch

1. In `goodix5e0a_deactivate`: if `SCAN_5E0A_FDT_DOWN` or any scan SSM is in-flight,
   cleanly abort or drain before parking, OR invalidate the park (`tls_parked = FALSE`)
   when deactivating from a non-idle state so that a clean bring-up occurs rather
   than a desynced reuse.
2. Alternatively, ensure the parked session health probe flushes stale input packets
   before asserting that the session is healthy and sending `0x96`.

## Hardware verify protocol (user only, AGENTS.md compliant)

1. Deploy + restart:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Run 5 consecutive `fprintd-verify` attempts back-to-back without waiting.
3. Check journal:
   `journalctl -u fprintd --since "5 min ago" --no-pager | grep -a -E "timed out|Invalid ACK|verify-unknown-error" | tail -n 20`
4. Expected: Zero `Command timed out: 0x96`, zero `Command timed out: 0x32`, zero `verify-unknown-error`.
