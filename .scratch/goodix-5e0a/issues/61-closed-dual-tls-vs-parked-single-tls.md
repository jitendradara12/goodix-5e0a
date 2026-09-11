# 61 — Dual-TLS vs parked single-TLS (do not merge blindly)

**What to do:**
Evaluate whether anything from the /tmp/libfprint dual-TLS design (cmd TLS
with zero-PSK + image TLS with per-device PSK, `POV 0xD6` check, separate
`image_tls_hop` + `tls_read_image_5e0a_with_payload`) is needed here, or
whether our single parked TLS (TTL 30s, `0xae` health, full-ladder fallback,
tickets 38/40/46) already covers it. Default: no change.

**Do not relitigate:**
- Tickets 38/46/48/50: park-only-when-idle, mid-FDT_DOWN teardown destroys,
  cold latch + post-TLS config, `0xd4` timeout-is-success, suspend destroys.
- Ticket 51 remainder (SSL_ERROR/WANT_*, accept timeout, deinit re-entrancy,
  PSK-callback lifetime) is separate work; this ticket is architecture only.

**Source:** /tmp/libfprint `goodix.{c,h}` dual context, `goodix5e0a.c`
`ACTIVATE_CMD_TLS/POV_IMAGE_CHECK/IMG_TLS` ladder, `RE_INIT_SEQUENCE.md`
(`0x90/0xC4/0xA2/0xD2` map; they omit `0x90/0xC4`, we upload `0x90` post-TLS).

**Status:** closed (verdict: decided / single-TLS kept)

**Acceptance:**
- Written decision: keep parked single-TLS (with journal/pcap citation) or
  adopt named pieces with per-piece hardware proof. No dual-TLS merge
  without a failing case single-TLS cannot serve.

## Final Audit & Closure (2026-09-11)
- Verdict: CLOSED (decided / single-TLS kept).
- Findings:
  1. Full architectural evaluation completed and documented in `docs/DECISION-61-PARKED-SINGLE-TLS.md`.
  2. Single parked TLS over `PSK-AES128-CBC-SHA256` carries all commands and image transfers reliably.
  3. None of the falsification criteria were met: dual-TLS context is unneeded on ChicagoH. Parked single-TLS remains authoritative.
