# Ticket 48: Cold-Boot TLS Handshake Fix

Status: ready-for-hardware-verify
Opened: 2026-09-09
Supersedes: 45 (insufficient — warm-sensor test, not true cold boot)

## Root Cause

Three bugs combined to cause `verify-unknown-error` on cold boot after
overnight shutdown:

### Bug 1: Config upload order (primary)
Linux uploaded MCU config (`ACTIVATE_UPLOAD_CONFIG`, CMD `0x22`) **before**
TLS handshake.  Windows does it **after** TLS (`wbdi.dll Start` at
`0x180083900`: check PSK → start TLS → download chip config).  On cold boot,
uploading config to an un-initialized MCU crypto engine desynchronizes it,
causing `bad record mac` on subsequent TLS `SSL_accept`.

### Bug 2: CMD 0xd0 payload mismatch
Linux sent `REQUEST_TLS_CONNECTION` (CMD `0xd0`) with a 0-byte empty
payload.  Windows sends it with a 2-byte payload `[0x00, 0x00]` (confirmed
at `wbdi.dll` offset `0x1800a6ec7`: `r9d = 2`, `lea r8, [rsp + 0x40]`
where 0x40 was zero-filled).

### Bug 3: TLS error fallthrough
In `goodix.c` `on_goodix_request_tls_connection`, when CMD 0xd0 response
returned an error, the code called
`goodix_send_tls_successfully_established(dev, NULL, NULL)` — proceeding as
if TLS succeeded.  This sent scan commands on a dead channel →
`Invalid protocol command: 0xd0` → `Command timed out: 0x20` →
`verify-unknown-error`.

## Fix Applied

### goodix5e0a.c
- `ACTIVATE_UPLOAD_CONFIG` in the SSM now unconditionally jumps to
  `ACTIVATE_NUM_STATES` (config skipped in pre-TLS ladder).
- New callback `on_post_tls_config_uploaded` added.
- `on_tls_activation_complete` success path: cold path uploads config
  via `goodix_send_upload_config_mcu` then chains to chip enable;
  warm path skips config (already loaded) and goes straight to chip enable.

### goodix.c
- `goodix_send_request_tls_connection`: payload changed from
  `GoodixNone payload = {}` (0 bytes) to `guint8 payload[2] = {0x00, 0x00}`.
- `on_goodix_request_tls_connection` error path: propagates error to
  `priv->tls_ready_callback` (same pattern as `tls_handshake_done` error
  path) instead of calling `goodix_send_tls_successfully_established`.

## Predicted Journal Signatures

### Cold boot (confirm):
- `TLS connection ready!` followed by `Cold path — uploading config after TLS...`
  followed by `Config uploaded after TLS, enabling chip...`
- No `bad record mac`, no `Invalid protocol command`, no `Command timed out`

### Warm reuse (confirm):
- `TLS connection ready!` followed by `Warm path — config already loaded, enabling chip...`
- No config upload command on warm path

### Falsify:
- `bad record mac` or `verify-unknown-error` on cold boot after overnight
  shutdown → reopen with pasted journal output.

## Verification

Hardware test required — true cold boot from power-off (not sleep/suspend).
