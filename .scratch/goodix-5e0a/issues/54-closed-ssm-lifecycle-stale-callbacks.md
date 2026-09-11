# 54 — SSM lifecycle: stale callbacks, timeout destroy, activate cancel

**What to fix:**
In `libfprint/drivers/goodixtls/goodix5e0a.c`:
- `step_cb:627` noreply errors swallowed + advances with no `scan_ssm==ssm` / gen check (siblings `:837,:1022,:675` have it). `deactivate:1225` frees `scan_ssm` while noreply callbacks pending = UAF.
- `down_timeout=NULL` without `g_source_destroy` (`:310,:325,:512`); only `:1143`/deactivate destroy. Leaked source can fire with freed ssm.
- Activate SSM anonymous (`:316,:330`), `activate_complete:460` has no gen check — deactivate mid-activate keeps driving USB + `tls_init` post-deactivate.
- Warm-fail path `:474` calls `start_full_activation` without `shutdown_tls/reset_state` (vs `:430` which does).
- FDT_DOWN timeout (`203cfc8`) marks whole claim failed on single 1s `GOODIX_TIMEOUT` blip instead of re-poll; `scan_timeout_gen != scan_gen` guard dead (both set equal at `:741`).

**Settled facts (29/34/40/42):**
- Disarm-before-free: `session_started=FALSE → timeout destroy → reset_state → ssm free → shutdown_tls`. Stale completions drop (gen mismatch → dbg only, no HW touch).
- Warm = host-recency only; handshake + health authoritative + silent full-ladder fallback. `boot_seq++` only on reset.
- `0xd4` timeout is success (50) — don't break it while fixing timeouts here.

**Status:** closed (verdict: rejected / falsified)

**Acceptance:**
- All SSM callbacks validate liveness before `next_state`; timeouts destroyed+NULLed on every exit; activate path cancellable via gen; warm-fail tears down TLS; FDT_DOWN transient re-polls (bounded) instead of instant fail.

## Correction (2026-09-10, hardware-line reconciliation)
- Reverted: FDT_DOWN 3x transient re-poll budget ("exhaustion fails
  loudly"). Restored immediate `mark_failed` on non-CANCELLED error
  (CANCELLED branch kept). Rationale: FDT_DOWN runs timeout 0, so an
  error means session death — re-sending DOWN flogs a dead session and
  manufactures TLS-error storms. Evidence: `~/code/temp/libfprint`
  `1da3a0f` (timeout 0, no retry) + AGENTS.md rules 1/5.
- Kept: SSM liveness guards, `clear_down_timeout` choke point,
  gen-pinned activate ladder, warm-fail teardown, dispose (no wire change).
  Deactivate already clears `retry_guard` on the destroy branch only
  (rule 3 ✓, matches `8ab64e0`).
- Smoke per AGENTS.md rule 7 after deploy.

## Final Audit & Closure (2026-09-11)
- Verdict: CLOSED (rejected / falsified).
- Findings:
  1. FDT_DOWN re-polling violates AGENTS.md Rules 1 & 5. 0x32 FDT_DOWN is a blocking capacitive interrupt with timeout 0; when it fails, the transport session is dead. Re-polling manufactures violent TLS-error storms.
  2. The generation-pinned cancellation check in `activate_complete` would drop D-Bus completion without calling `fpi_image_device_activate_complete()`, causing clients (fprintd/PAM) to hang for 25–30s until D-Bus timeout.
  3. Disarm-before-free and timeout destruction are already correctly handled in the master baseline; speculative changes introduced regressions.
