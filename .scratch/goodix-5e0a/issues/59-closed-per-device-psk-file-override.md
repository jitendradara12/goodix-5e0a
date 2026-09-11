# 59 — Per-device PSK without vendoring secrets (file override vs hardcoded)

**What to do:**
Evaluate a read-only PSK-file override (e.g. `/etc/libfprint/goodix-5e0a.psk`
+ `~/.config/libfprint/goodix-5e0a.psk`, 64 hex chars, SHA256-verified
against the `0xbb020001` slot per /tmp/libfprint `on_psk_read_5e0a`) that
falls back to the hardcoded host PSK + cold `0xe4` latch (ticket 48).
Driver must never erase/provision (their @55a7379 brick warning + our
ticket 44§27: `0xe0` needs IAP + WhiteBox-96B, rejected in APP mode).

**Do not relitigate:**
- Tickets 26/37/44/48: `bb020001` = SHA256(psk), factory-table stripped as
  upstream-unacceptable, cold latch before TLS + config after TLS, no `0xa2`.
- Docs `UPSTREAM.md` section 6 disclosure stays accurate whichever source wins.

**Source:** /tmp/libfprint `goodix5e0a.c` `load_psk_from_file()` +
`compute_sha256()` verify, `tools/extract_psk.py` (DPAPI TLV `0xBB010002`
read + Windows-SYSTEM decrypt), `RE_PSK_*.md`.

**Status:** closed (verdict: decided / shelved)

**Acceptance:**
- Decision with upstream rationale: hardcoded-only, file-override, or
  file-only; no secret added to the tree either way.
- If file-override: missing/invalid file behaves exactly like today
  (fallback + warn, no handshake behavior change); `ninja` clean.

## Final Audit & Closure (2026-09-11)
- Verdict: CLOSED (decided / shelved).
- Findings:
  1. On our ChicagoH hardware, physical MCU slot `0xbb020001` SHA256 matches the hardcoded class PSK 100% byte-for-byte.
  2. TLS handshake (`PSK-AES128-CBC-SHA256`) and frame reception succeed reliably without error.
  3. Adding disk I/O, file permissions parsing, and state caching to a root-level system daemon (`fprintd`) is unneeded complexity and bloat for zero hardware benefit. The hardcoded host key remains authoritative.
