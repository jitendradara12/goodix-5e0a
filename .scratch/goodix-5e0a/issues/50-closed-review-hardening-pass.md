# 50 — Review hardening pass (memory hygiene, dead guards, stale comments)

**What was built:** Three parallel read-only reviews (5e0a lifecycle,
transport/TLS, base drivers) returned 25 candidates. Each load-bearing
claim was re-verified against the code before touching it. Fixed the
confirmed set below in one behavior-preserving batch (all changes gate on
error/edge paths unreachable in healthy flows, or are comment/allocator
hygiene). Biometrics untouched throughout.

**Blocked by:** None.

**Status:** closed

**Verdict:** CONFIRMED on hardware 2026-09-09 (fixed build `24ahq4d9…` generation).

Re-smoke after the B5 revert: enrolled verify runs clean, 5-min error grep
empty (zero `timed out`, zero `Invalid ACK`, zero `verify-unknown-error`,
zero `failed to`). The 0xd4-funnel line never reappeared — consistent with
the analysis that it could only come from the pre-revert binary. Ticket
closed; batch committed.

**Live-scope:** memory/error-path hardening only. No biometric changes, no
threshold changes, no protocol redesign.

## Fixed (verified before editing)

- `goodix.c` deinit double-free: `timeout`/`data` destroyed+freed then
  `goodix_reset_state` freed again → NULL after destroy/free.
- `transfer_cancel_tkn` leaked per open/close (created 1386, never unreffed)
  → `g_clear_object` in deinit.
- `goodix_tls_init` failure leaked `tls_hop` + `err` and stranded the
  activation waiter → forward `err` to the ready callback, free hop.
- `goodix_shutdown_tls` stranded a racing ready callback (leak) → release
  without invoking (invoking would double-complete the torn-down claim).
- `on_tls_successfully_established` swallowed transport errors as success
  (same class as the ticket-48 request-path fix) → forward `error`.
- BUSY collision stalled the incoming waiter forever → fail it loudly too.
- `pthread_create` unchecked in `goodixtls.c` → checked, cleaned up, error set.
- `get_mcu_cfg` dereferenced unguarded in base scan (latent NULL-crash) →
  skip-stage guards mirroring siblings.
- `goodix5e0a.h` ground-truth tables kept (test-pinned fixtures, zero
  runtime cost); `goodix511.h` ODR hazard reverted to keep the pristine pin.
- `g_memdup` → `g_memdup2` (checked, wire-parsed lengths);
  `malloc` → `g_new0` for `GoodixCallbackInfo` (29 sites, fields always
  assigned — zeroing strictly safer).
- Retry-guard re-issue stop-loss: past 30s (all live clients time out by
  ~25s) fail the orphaned claim instead of re-issuing forever. No struct
  change (reuses `retry_guard_mono`).
- Stale comments rewritten (46 ladder, 20-vs-47 deliver, 511 NOP, 5xx
  contract); dead TODOs/cast/stray `;` removed; dead `goodix_tls_ready`
  wrapper folded (sole caller passed NULL always).
- Tests repaired to green: f26 bold-Status + empty-workfront agreement,
  stale LOC caps 1425→1525, tier5 800-char windows→1600/function slice,
  f25 pristine set shrinks (proto.c patched), tier5 pin → `f0bdb6bb…`.

## Round 2 (same batch, pre-smoke)

Second review round (adversarial diff audit + packaging audit + SSM
coexistence audit, all pairs safe) added, all verified before editing:
- `on_tls_successfully_established` NULL-guards the ready callback
  (teardown race; error freed when waiterless).
- BUSY second message logs the captured `busy_cmd` (was post-reset `0x00`).
- Deinit cancel NULL-checked (double-deinit tolerant, mirrors line 551).
- Packaging: module version suffix unified to `-5e0a` (both derivations
  now resolve to the IDENTICAL store path); module postPatch idempotent
  guards; `libfprintSrc` override parameter deleted (single base by
  construction); repo `nixos-module.nix` gains the udev extraRules stanza;
  new f22 fetch-parity test (rev+hash equality, no-override assertion).
- Evidence refreshed: 450/450 green (228+130+24+5+63), ninja clean, both
  derivations → same store path, tier5 pin → `f0bdb6bb…`. Smoke protocol
  below covers this batch as well.

## Declined with reason (do not re-litigate without new evidence)

- Gen guards on `on_chip_enabled` / `on_post_tls_config_uploaded` /
  `on_psk_hash_read` / per-callback SSM checks: orphaned single-flight
  replies are already dropped by `goodix_reset_state` (clears
  callback/user_data/ack/reply); residual mistyped-consumption class needs
  wire sequencing, not callback guards — no occurrence on record.
- Activate-SSM orphan leak (~64B per teardown-mid-activation): tracking
  handle risks double-free against self-freeing completed SSMs; rare + tiny.
- FDT_DOWN `timeout 0`: blocking wait is the Windows-faithful design;
  framework-bounded (client timeout/deactivate).
- Non-guard FDT_UP error completing scan: verified end-of-scan behavior.
- Base-scan dead legs / header tables: vtable contract + test-pinned.
- `Transfer was cancelled` noise: sink already `fp_dbg`; no 5e0a `fp_warn`
  CANCELLED site exists.

## Evidence (pre-hardware)

- `bash tests/run_all_tests.sh`: 448/448 (226+130+24+5+63), all tiers green.
- ninja drivers build: 0 warnings, 0 errors.
- Both nix derivations build with fresh store paths (no stale cache);
  module `.so` contains the new markers (`orphaned hold`, `re-issuing`,
  `park invalidated`).

## Smoke incident 2026-09-09 — B5 error-forwarding broke every activation

Deployed smoke failed 3/3 claims: `failed during TLS activation: Command
timed out: 0xd4`. Root cause: `0xd4` is `TLS_SUCCESSFULLY_ESTABLISHED`,
which the MCU never ACKs — the timeout fires on EVERY healthy handshake
(said in-tree at the send site: "it will always timeout for some reason").
The old swallow-as-success was load-bearing, not a fault mask; forwarding
it as failure failed 100% of activations. The review theory never asked
whether error is non-NULL on the healthy path. Reverted to
report-success + free-the-error (keeps the leak fix and the NULL guard);
send-site comment now records that the timeout IS the success signal so no
future pass "fixes" it again. Patch re-rolled (`b7b12f7c…`), both
derivations rebuilt to one identical store path, suite still 450/450.

## Hardware smoke protocol, round 2 (user only)

Deploy + restart fprintd, then one enrolled-tap verify plus:
`journalctl -u fprintd --since "5 min ago" --no-pager | grep -a -E "timed out|Invalid ACK|verify-unknown-error|failed to|double|critical|WARNING" | tail -n 15`
- Confirm: `verify-match`, empty grep (no new warnings from the touched
  paths), normal reuse/guard lines unchanged.
- Falsify: any new warning/critical or behavior change vs tickets 46–49 →
  bisect by reverting this batch (single commit) and report which area.
