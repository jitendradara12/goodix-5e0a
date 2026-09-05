# 21 — Transport memory-hygiene validation (ASan/valgrind, no code change)

**What to build:** Nothing in code (yet). Run the deployed driver under
AddressSanitizer (or valgrind) on hardware through one enroll + two verifies
and record whether the statically verified findings below reproduce. This
ticket converts review hypotheses into journal-backed facts; any fix gets its
own ticket afterward. One variable per build still applies — no driver edits
in this run.

**Blocked by:** None (needs a hardware host with ASan-instrumented or
valgrind-run fprintd; purely observational).

**Status:** closed

**Verdict (2026-09-05): scopechanged — no dedicated valgrind run, findings
dispositioned on evidence weight.**
A valgrind/ASan run needs fprintd under instrumentation (foreground daemon
loses the D-Bus race per AGENTS.md; service wrapping needs read-only
`/etc/systemd`), i.e. heavy user labor for findings that are code-reading
certainties, not runtime hypotheses: finding 2 (pointer-sizeof) already FIXED
in ticket 26; finding 1 (FDT-mode free-then-read) → ticket 27; finding 3
(receive-done error leak) → ticket 28; findings 4–5 REFUTED in-ticket;
finding 6 stays downgraded. FD-accounting folded into everyday-use
observation (no dedicated cycles). Reopen only on a pasted leak trace.

## Settled facts (verified by reading, do not re-litigate)
1. `goodix_send_mcu_switch_to_fdt_mode` (`goodix.c:795-818`) calls
   `free_func(mode)` and THEN passes `mode` into `goodix_send_protocol`
   (which synchronously `memcpy`s it in `goodix_encode_protocol`). Siblings
   (e.g. FDT_UP just above) pass `free_func` through instead. Live path
   `goodix5xx.c:404` passes heap `cfg.data` + real `cfg.free_fn` — a latent
   heap-use-after-free READ, masked in practice by allocator behavior.
2. `goodix_send_preset_psk_write` (`goodix.c:1266-1279`) sends
   `sizeof (payload) + length` where `payload` is `guint8 *` (8 on 64-bit).
   The allocation was `sizeof (GoodixPresetPsk) + length` (= 8 + length:
   flags + length words). Correct value by 8==8 coincidence on 64-bit;
   would truncate 4 bytes on 32-bit. All supported deployments are x86_64.
3. `goodix_receive_done` (`goodix.c:84-99`) early-returns on
   `!(ack||reply)` WITHOUT freeing a passed `error` — bounded leak on
   collision/late-reply paths only.
4. REFUTED (do not file): alleged double destroy/free around
   `goodix_dev_deinit` — `goodix_reset_state` nulls via `g_clear_pointer`,
   the destroy is `if`-guarded, `g_free(NULL)` is safe.
5. REFUTED: alleged NULL `err` deref after failed `goodix_tls_server_init` —
   both `return FALSE` paths (`goodixtls.c:238,249`) set `*error` first.
6. DOWNGRADED, needs runtime proof: 28 raw `malloc`s without NULL checks
   (glib/Linux context; upstream would not require); `tls_handshake_done`
   sending D4 after a failed leg (error leg likely never fires — hardware
   works); tail-chunk over-send in `goodix_send_data` (unreachable: all
   inputs arrive 64-padded via `goodix_send_pack`).
7. Trivia (not worth a frozen-file edit): stray `;` after
   `goodix_send_protocol` failure block (`goodix.c:~638`).

## TLS engine init/teardown observations (`goodixtls.c`, same run covers them)
8. `goodix_tls_server_init` does not check `SSL_new` (`goodixtls.c:254`)
   or `pthread_create` (`:259`) — unlike both prior alloc paths in the same
   function (`:231`, `:243`). On failure init still returns TRUE. Alloc/
   thread-exhaustion rarity bounds it; a valgrind/fd-exhaustion run is the
   only honest probe (force via low `ulimit -v` / thread limit if available).
9. Teardown order in `goodix_tls_server_deinit`: `shutdown` → `join` →
   `close` → `SSL_shutdown`/`SSL_free` (`:176-213`). `SSL_shutdown` runs
   after its fd is closed (ordering inversion, return ignored — benign by
   inspection). f18 test claims (shutdown-before-join, both fds invalidated,
   double-deinit safe) all verified against this exact sequence.
10. Adjudicated sound (do not re-litigate): the `shutdown(SHUT_RDWR)` wakeup
    premise (`:176-177`) holds on Linux AF_UNIX — blocked `recv` returns EOF,
    `SSL_accept` errors out, the serve thread exits, `join` returns. Serve vs
    teardown `SSL*`/fd access is strictly sequenced after `join`, so no lock
    is needed on that pair. pthread_create-failure join hazard is void on
    glibc (`serve_thread` zeroed at `:223`, untouched on failure → skipped
    by the `:184` guard; strictly POSIX-unspecified, practically safe).

## Extended validation for the same run
- FD accounting: record `/proc/self/fd` count (or `ls /proc/<pid>/fd | wc -l`)
  before the first activation and after each of 3 consecutive
  activate → verify → deactivate cycles. Predict: returns to baseline
  every cycle (no fd/SSL/thread leak from init/teardown paths).
- Confirm branch: valgrind clean + fd count stable + finding-1/2 paths
  never trigger (no alloc-failure logs); behavior identical to baseline.

## Predicted signatures
- Confirm branch (defects real but benign as analyzed): ASan/valgrind run
  shows the FDT-mode UAF read + bounded error leak(s) on collision paths
  only; zero new leaks on clean enroll + 2-verify; frame stats, minutiae,
  and match outcomes identical to the uninstrumented build.
- Falsify branch: any finding above does not reproduce as described, or
  the run shows leaks/crashes NOT listed here → file them with exact
  traces; do not fix inside this ticket.

## Acceptance (hardware verify protocol, no exceptions)
Paste client lines plus valgrind/ASan summary plus the standard
`journalctl -u fprintd` grep output; conclude only confirmed / falsified /
inconclusive-because-[flaw] + the single next experiment (fix ticket per
finding, or close as benign-with-evidence).
