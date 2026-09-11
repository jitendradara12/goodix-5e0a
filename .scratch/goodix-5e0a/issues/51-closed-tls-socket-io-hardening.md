# 51 — TLS socket I/O hardening (short-read, SSL errors, blocking accept)

**What to fix:**
In `libfprint/drivers/goodixtls/goodixtls.c` (+ `goodix_proto` glue):
- `goodix_tls_client_read` single `read()` returns short counts as success.
- `goodix_tls_server_read` ignores `accept_done`, no `SSL_get_error` / `WANT_READ|WANT_WRITE` handling, fabricates `0x0` error on empty queue, overwrites `*error`.
- `goodix_tls_init_serve` blocks in `SSL_accept` with no timeout/cancellable; `deinit` `pthread_join` can hang deactivate.
- `server_deinit` not re-entrant (double-join/close/free), `server_init` overwrites live state, PSK callback UAF (`user_data` raw `FpDevice*` on serve thread).

**Settled facts (do not relitigate):**
- Tickets 44/45: `0xa2` never sent, `bad record mac 0x0A000119` was crypto desync, not PSK loss. `bb020001` = SHA256(psk).
- Ticket 38/46: park only when idle + `0xae` health + full-ladder fallback; suspend always destroys.
- Ticket 50: `0xd4 TLS_SUCCESSFULLY_ESTABLISHED` timeout IS success — never forward as failure.

**Status:** closed (verdict: redundant / falsified)

**Progress (goodixtls port, this tree):**
- Handshake short-read fixed in `goodix.c`: `goodix_tls_read_all_records()`
  (TLS-record framing + poll-50ms coalesce, 4096B) + `goodix_tls_hex_dump()`
  now serve both server→device stages. Single-`read()` truncation of the
  ServerHello/CCS flight is gone; healthy-handshake bytes unchanged.
- Remaining: `goodix_tls_server_read` SSL_ERROR/WANT_* mapping, accept
  timeout/cancellable teardown, deinit/init re-entrancy guards, PSK-callback
  lifetime. See `specs/GOODIXTLS-PORT-NOTES.md`.

**Acceptance:**
- client_read loops until `length` or EOF/error (EINTR + EAGAIN handling, NULL checks).
- server_read checks handshake state, maps `SSL_ERROR_WANT_*` to retry not fatal, checks `*error==NULL` before set.
- accept has bounded wait + cancellable teardown path; deinit/init guards against double-call; PSK callback refs device or documents lifetime.
- No behavior change on healthy handshake; `ninja` clean.

## Correction (2026-09-10, hardware-line reconciliation)
- Reverted: `server_read` handshake-fatal gate + `ZERO_RETURN → CLOSED`
  error + 10x image-read retry loop. Restored the settled retry contract
  (`WANT_* → WOULD_BLOCK`, else `err_from_ssl`, return `retr` as-is;
  single-read image handler). Evidence: `~/code/temp/libfprint`
  `add-goodixtls-5e0a` (`server_read` has no gate; image handler is a
  single read) — timeout/TLS teardown races are non-compromising.
- Kept: client loops, bounded cancellable accept, deinit/init
  re-entrancy, `*error==NULL` guards, PSK lifetime doc (no wire change).
- Smoke per AGENTS.md rule 7 after deploy.

## Incident (2026-09-10, hardware-caught)
- The init liveness guard shipped with `sock_fd >= 0 || client_fd >= 0`
  clauses. `goodix_tls_init` passes a fresh `g_new0` struct (fd 0), so
  `0 >= 0` failed EVERY init: journal showed `failed to init tls server:
  TLS server already initialized` + `verify-unknown-error` on all
  verifies. Static tests and compile could not catch it (no runtime).
- Fix: guard checks `ssl_ctx/ssl_layer/serve_thread` only; `goodix_tls_init`
  sentinels fresh fds to -1. Regression tests in `test_f18` pin both.
- Lesson: any `fd >= 0` liveness check is wrong on zeroed structs; rule-7
  smoke is mandatory before calling a change safe.

## Final Audit & Closure (2026-09-11)
- Verdict: CLOSED (redundant / falsified).
- Findings:
  1. The genuine hardware bug (short-read truncation of the ServerHello/CCS flight) was already solved and hardware-verified in master commit `4a6620c` via `goodix_tls_read_all_records()`.
  2. The remaining speculative socket hardening on the local `AF_UNIX` socketpair was unnecessary and introduced fatal bugs:
     - The `0 >= 0` init liveness check broke 100% of driver initializations.
     - Clearing `user_data` in deinit broke subsequent PSK callbacks on device re-initialization.
     - `goodix_shutdown_tls()` already unblocks `SSL_accept` instantly via `shutdown(client_fd, SHUT_RDWR)`.
  3. Speculative socket hardening discarded; master `4a6620c` implementation remains authoritative.
