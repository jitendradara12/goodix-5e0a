# 55 — Memory/GObject: GSource UAF, dispose, clean-close leak

**What to fix:**
- `goodix.c:444` `receive_timeout_cb → receive_done → reset_state → g_source_destroy(timeout)` on already-fired (freed) source = freed-`GSource` deref. `goodix5e0a.c:673` pattern (NULL on fire) is correct.
- No `dispose`/`finalize` anywhere: `tls_hop`, `transfer_cancel_tkn`, `tls_ready_callback`, `best_img`, `scan_ssm`, `down_timeout` leak on early destroy.
- `goodix.c:1203` clean-close skips `shutdown_tls`, leaks parked `tls_hop` + fds/SSL through `img_close`.
- `goodixtls.c:183` overwrites `*error` without NULL check + fabricates `0x0` on empty ERR queue; `:241` `deinit` always TRUE (dead `suspend` error path); `goodix.c:1529` NULL-callback crash on init failure.

**Settled facts (21/27/28/30):**
- FDT-mode free-then-read UAF real (pass `free_func` through); `receive_done` error leak on collision paths real; double-free claims refuted — verify with trace, don't relitigate.
- `g_memdup2`, `g_new0`, `g_clear_object`, NULL-after-destroy, `pthread_create` check (50) — keep.

**Status:** closed (verdict: rejected / defective)

**Acceptance:**
- Timeout destroy NULL-safe on fired path; `dispose` releases all owned refs/sources; clean-close frees parked TLS; error paths check `error==NULL`, no fabricated errors; `ninja` clean.

## Final Audit & Closure (2026-09-11)
- Verdict: CLOSED (rejected / defective).
- Findings:
  1. The assertion that clean-close skipping `shutdown_tls` is a "leak" represents a fundamental misunderstanding of the driver lifecycle. The parked TLS session is an intentional performance cache (Tickets 38, 40, 46) designed to survive across claims with a 30s TTL.
  2. Shutting down TLS on clean-close destroys session reuse for repeated PAM claims (e.g. `sudo`), forcing a 1.5s cold handshake every time and directly violating AGENTS.md Rule 3.
  3. Custom GObject dispose methods introduced teardown races during unref. Master baseline lifecycle is retained.
