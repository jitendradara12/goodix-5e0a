# 75: Back-to-Back Claim TLS Lifecycle & Park/Shutdown Hygiene

**What to build:** Rapid consecutive fingerprint authentications (e.g. repeated `sudo -v`, sequential PAM claims, or retry after non-matching touch) succeed without crashing `fprintd` with `libfprint:ERROR:../libfprint/drivers/goodixtls/goodix.c:1851:goodix_tls_init: assertion failed: (priv->tls_hop == NULL)`.

**Blocked by:** 74 (closed)

**Status:** closed (verdict: confirmed; back-to-back warm claims complete TLS without abort; successor: none)

## Acceptance Criteria

- [x] Consecutive authentication claims (e.g. back-to-back `sudo -v` within 3 seconds) complete without daemon abort (`SIGABRT`) or core dump.
- [x] `priv->tls_hop` is guaranteed NULL before any warm activation `goodix_tls_init`: `dev_activate` shuts down an alive-but-unparked orphan before any ladder starts (code + 459/459 tests + hardware Run 3, see Fix below). Deviation from the "park on completion" alternative is journal-backed (claim 2's `warm activation` lines prove the device stayed open — no close/deactivate ran between claims, so there is no completion-time hook to park in; the activate-entry choke point covers both open-held and close-reopen worlds).
- [x] All invariants preserved: `0x32` FDT_DOWN timeout is strictly 0; `0x34` finite guard loop intact; park cross-claim TTLs survive idle park; `CANCELLED` never re-issues (independent review, 3/3 confirm).
- [x] Ninja driver build links cleanly, `bash tests/run_all_tests.sh` passes 459/459 tests, and patch is synced to NixOS module (SHA-256 `6e95402c6aa28c8200c6c882a379ad00639ac73f4aa77e3ba1e08c869ed026b5`, byte-identical in `/home/sastauser/NixOS-Hyprland/modules/goodix/`; hash pin rolled; build tree `diff -q` clean).
- [x] Hardware verification: two consecutive `sudo -v` commands execute without crash (Run 3: claim2 `exit=0` via fingerprint; daemon serves 6 consecutive activations under one PID with zero aborts).

## Context & Evidence

In Ticket 74 Hardware Run 2:
- Attempt 1 verified successfully via Milan and opened a root session via PAM (`sudo -v`).
- Attempt 2 (0.3s later) crashed on warm activation:
  ```
  Sep 14 17:37:53 sastapc fprintd[258081]: 5e0a warm activation: reusing MCU config (age=0.3s, boot_seq=2)
  Sep 14 17:37:53 sastapc fprintd[258081]: 5e0a warm path: skipping RESET + config upload, entry=CHECK_FW_VER
  Sep 14 17:37:53 sastapc fprintd[258081]: **
  Sep 14 17:37:53 sastapc fprintd[258081]: libfprint:ERROR:../libfprint/drivers/goodixtls/goodix.c:1851:goodix_tls_init: assertion failed: (priv->tls_hop == NULL)
  ```
- Because `goodix5e0a_deactivate` was removed from verify deliver in Ticket 74 to eliminate the SSM use-after-free, `tls_parked` was never set. The next claim fell through to warm activation and invoked `goodix_tls_init`, while `priv->tls_hop` from the previous session was still non-NULL.

## Fix (one variable: orphaned TLS shutdown at activate entry)

`libfprint-driver/goodix5e0a.c`, `dev_activate`, between the ticket-38 void-park fallback and the ticket-40 warm check (goodix5e0a.c:644):

```c
  if (goodix_tls_is_alive (dev))
    {
      /* Ticket 75: alive but unparked — the previous claim completed without
       * parking (FpDevice holds the device open, so no deactivate runs
       * between claims) or an error path left its context behind. Every
       * ladder below ends in goodix_tls_init, which asserts tls_hop == NULL,
       * so shut the orphan down now; warmth still earns the warm ladder. */
      fp_dbg ("5e0a closing orphaned TLS session before new activation");
      goodix_shutdown_tls (dev, NULL);
    }
```

Why this shape (rejected alternative: park-on-claim-completion in `on_read_img`):
- The crash journal proves the device stays open across claims (claim 2 reads `warm_ok`/same `boot_seq`), so no deactivate/close hook runs between claims — the activate-entry choke point is the only site that sees every second claim.
- Park-on-completion would be a second variable (new park site + changed close semantics) and breaks the frozen `goodix_session_mark_clean == 1` pin (test_f42) without journal-backed reason. The shutdown keeps all frozen pins green: `tls_init == 1`, `g_message == 23`, `mark_clean == 1`, compactness 1832/1850, no `tls_hop` in 5e0a.c.
- Claim 2 still takes the warm ladder (fresh TLS handshake on warm is designed ticket-40 behavior — the handshake is never skipped, only RESET/CHIP_ID/OTP/config are). `goodix_start_read_loop` is idempotent (`priv->inited` guard), and `goodix_shutdown_tls` is idempotent with designed stranded-callback drops.

## Verification (agent-side, no hardware)

- Ninja drivers-only build: `[3/3] Linking target libfprint-2.so.2.0.0`, 0 warnings/errors; build tree in sync (`diff -q` clean).
- `bash tests/run_all_tests.sh`: 459 passed, 0 failed, 1 env-gated skip.
- Unified patch section for `goodix5e0a.c` regenerated (`@@ -0,0 +1,2083 @@`); repo SHA-256 `fd954578948cea1026bba3a95b4277f2ad73c7f13b5205a5cec42d97ae8f70f6`, byte-identical in `/home/sastauser/NixOS-Hyprland/modules/goodix/`; stale hash pin in `test_m1_c1_lifecycle_adversarial.py` refreshed (routine per-ticket pin roll, cf. ticket 46).
- Three independent subagent reviews: invariants (rules 1-7) CONFIRMED, static pins CONFIRMED (all counts re-run), lifecycle CONFIRMED (single init site at `activate_complete`, guarantee holds on park/warm/full/probe-fallback paths; reuse path returns before the new block).

## Predicted Journal Signatures (debug env, `G_MESSAGES_DEBUG=all`)

- Confirm (claim 2, ~0.3s after claim 1): `5e0a closing orphaned TLS session before new activation` → `5e0a warm activation: reusing MCU config (age=0.xxs, boot_seq=N)` → `5e0a warm path: skipping RESET + config upload, entry=CHECK_FW_VER` → `Starting up goodix tls server` → `TLS connection ready!` → `Warm path — config already loaded, enabling chip...` → `Chip enabled!` → verify-match, PAM session opens, no abort.
- Falsify: recurrence of `goodix_tls_init: assertion failed: (priv->tls_hop == NULL)` / `SIGABRT`, or claim 2 falling to the full ladder (`5e0a warm expired` / `Cold path — uploading config`) which would falsify "warmth earns the warm ladder".

Conclude only: confirmed / falsified / inconclusive-because-[flaw] + the single next experiment.

## Hardware Run 1 (2026-09-14 ~18:21, verdict: inconclusive-because-stale-build-and-debug-ordering)

User pasted:
```
Sep 14 18:21:30 sastapc fprintd[289503]: 5e0a warm activation: reusing MCU config (age=0.3s, boot_seq=1)
Sep 14 18:21:31 sastapc fprintd[289503]: libfprint:ERROR:../libfprint/drivers/goodixtls/goodix.c:1851:goodix_tls_init: assertion failed: (priv->tls_hop == NULL)
Sep 14 18:21:31 sastapc fprintd[289503]: Bail out! libfprint:ERROR:../libfprint/drivers/goodixtls/goodix.c:1851:goodix_tls_init: assertion failed: (priv->tls_hop == NULL)
```

Three flaws, each load-bearing — no conclusion about the fix is possible:
1. **Stale build (proven):** the abort cites `goodix.c:1851` as `assertion failed`. At run time the tree carried an unreviewed second-variable edit at exactly that site (see 3: `if`-recover instead of `g_assert`, since reverted — `g_assert` is back at 1851), so the deployed daemon predated the tree regardless. The `5e0a closing orphaned TLS...` line is also absent, but see flaw 2.
2. **Debug env ordered after restart (proven):** the run did `restart fprintd` BEFORE `set-environment G_MESSAGES_DEBUG=all`, so the serving daemon never had the debug env and every `fp_dbg` (including the fix's shutdown line) was invisible by construction. Correct order is set-environment first, restart second.
3. **Second variable found and reverted (proven):** `libfprint-driver/goodix.c` carried an unreviewed 18:15:33 edit replacing the `g_assert` with shutdown-and-recover (`closing orphaned TLS session in tls_init, recovering`). Per the one-variable lane it was reverted (tree + patch hunk `@@ -1402,11`, header recount verified by `test_f25_patch_sync` 9/9); the assert stands as the tripwire. Single variable is again exactly the `goodix5e0a.c:644` shutdown; suite back to 459/459; patch re-synced (`6e95402c...`).
- Single next experiment: rerun below (deployed-bytes check + correct debug order + back-to-back `sudo -v`).

## Hardware Run 2 (2026-09-14 ~18:34 local, verdict: inconclusive-because-timestamp-cache)

- `systemctl status fprintd` → `inactive (dead)`; `pgrep -x fprintd` empty. No new fprintd PID in the journal — only the 18:21 PID 289503 lines plus 18:29:29 PID 301792 startup lines (which already show the new driver: `scan type changed to 'press'`, `enroll stages changed to 8`).
- Both `sudo -v` returned `exit=0` with zero new driver lines because the sudo timestamp was already fresh (the runbook's own `sudo` proof-grep preceded the claims) — `sudo -v` then succeeds from cache with no PAM authentication at all. The claims never reached the driver.
- Single next experiment: kill the timestamp (`sudo -k`) before each claim, or use `fprintd-verify` which bypasses sudo caching entirely.

## Hardware Runbook, attempt 2 (user only — agent never runs claims)

```bash
cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl set-environment G_MESSAGES_DEBUG=all && sudo systemctl restart fprintd
# Prove the serving store path carries the fix (must print a .so path, never NO-FIX-IN-STORE):
sudo sh -c 'grep -l "5e0a closing orphaned TLS session before new activation" $(find /nix/store -maxdepth 4 -path "*libfprint-goodix*/lib/libfprint-2.so*" 2>/dev/null) 2>/dev/null || echo NO-FIX-IN-STORE'
# Phase 1: hands off 60s ("hands off" + timestamp): silent vs cycles.
sudo -v   # Phase 2a: touch enrolled finger, note unlock time
sudo -v   # Phase 2b (within ~3s): second consecutive claim — must unlock, no crash
sudo systemctl set-environment G_MESSAGES_DEBUG=
journalctl -u fprintd --since "10 minutes ago" | grep -E "orphaned TLS|warm activation|assertion failed|SIGABRT|core dump"
# Rule-7 smoke: grep -E "timed out|Invalid ACK|verify-unknown-error|failed to" scoped to the serving instance's match-claim window must be empty outside ticket-47/53 tolerant paths.
```
Conclude only: confirmed / falsified / inconclusive-because-[flaw] + the single next experiment.

## Hardware Run 3 (2026-09-14 ~18:35-18:36 local, verdict: confirmed)

User ran `fprintd-verify` x2 (both `verify-no-match`, sloppy touches per user — match result out of scope for this ticket), then `sudo -k` + `sudo -v` x2 (claim1 `exit=1` after 3 failed touches + password-required; claim2 `exit=0` via fingerprint). Journal, one PID throughout (304847, no daemon restart):

```
Sep 14 18:35:44 sastapc fprintd[304847]: 5e0a warm expired: reason=cold-start
Sep 14 18:35:45 sastapc fprintd[304847]: 5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)
Sep 14 18:35:47 sastapc fprintd[304847]: 5e0a warm expired: reason=cold-start
Sep 14 18:35:48 sastapc fprintd[304847]: 5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)
Sep 14 18:35:50 sastapc fprintd[304847]: 5e0a warm expired: reason=cold-start
Sep 14 18:35:50 sastapc fprintd[304847]: 5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)
Sep 14 18:35:53 sastapc fprintd[304847]: 5e0a warm activation: reusing MCU config (age=0.3s, boot_seq=3)
Sep 14 18:35:53 sastapc fprintd[304847]: 5e0a warm path: skipping RESET + config upload, entry=CHECK_FW_VER
Sep 14 18:35:53 sastapc fprintd[304847]: 5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)
Sep 14 18:35:55 sastapc fprintd[304847]: 5e0a warm activation: reusing MCU config (age=0.3s, boot_seq=3)
Sep 14 18:35:55 sastapc fprintd[304847]: 5e0a warm path: skipping RESET + config upload, entry=CHECK_FW_VER
Sep 14 18:35:56 sastapc fprintd[304847]: 5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)
Sep 14 18:36:04 sastapc fprintd[304847]: 5e0a warm expired: reason=cold-start
Sep 14 18:36:05 sastapc fprintd[304847]: 5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)
```

Load-bearing facts:
- 6 activations, 6 completed TLS handshakes, 0 asserts, 0 aborts, 1 PID (no daemon restart).
- The 18:35:53 / 18:35:55 activations are the exact ticket-74 crash shape (warm path, age=0.3s) and both completed the handshake. The `g_assert (tls_hop == NULL)` in `activate_complete` is synchronous and deterministic — survival entails `tls_hop` was NULL.
- Same `boot_seq=3` + intact `warm_ok` on the warm pair proves the device stayed open between them: any close/reopen takes the USB reset (`clean_close` is set only in the never-reached park branch, so every reopen resets) and bumps `boot_seq`. With the device open, the prior claim's TLS context was necessarily alive at the second claim's `dev_activate` — no other path shuts it down on this trace (destroy-branch deactivate, suspend, and probe-fallbacks are all unreachable here) — so the ticket-75 orphan shutdown (`goodix5e0a.c:644`) executed.
- Caveat (corroboration only): the `closing orphaned TLS` fp_dbg line is absent because this run's chain unset `G_MESSAGES_DEBUG` before the claims (runbook flaw on the agent side — the set step was dropped when the chain was rewritten for `fprintd-verify`). Behavioral proof above is decisive; no re-run needed for the verdict.
- 18:36:04 `cold-start` after warm successes is designed ticket-42 behavior: separate client sessions close the device (verify-process exit / PAM claim end) → dirty close → USB reset on reopen → new boot_seq → full ladder. Not a regression.
- Rule-7 smoke: no `timed out`, `Invalid ACK`, `verify-unknown-error`, or `failed to` in the window.
- Successor: none (independent falsification review: shutdown-site census over all 8 `goodix_shutdown_tls` callers leaves the ticket-75 block as the only path consistent with the warm-pair trace — deduction holds).
