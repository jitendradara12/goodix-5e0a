# 52 — Frame decoder robustness (underflow, checksum, bounds)

**What to fix:**
In `libfprint/drivers/goodixtls/goodix_proto.c` + `goodix.c` pack/protocol path:
- `goodix_decode_protocol:127` `GUINT16_FROM_LE(length)-1` underflows to 65535 on wire `length==0`.
- `goodix_decode_pack` / `decode_protocol` compute `valid_checksum` / `valid_null_checksum` but `goodix_receive_pack/protocol` never enforce — corrupt frames accepted.
- `goodix.c:375` `g_realloc(priv->data, priv->length+length)` unbounded, no max-frame cap, no wraparound check; corrupt-frame path just `return` leaving cmd/timeout armed until timeout.
- Trailing-byte desync: surplus after one pack discarded, coalesced second pack lost.
- Unaligned casts `(GoodixPack*)data`, `(GoodixProtocol*)data`, `(GoodixPresetPsk*)(data+1)`, bitfield `GoodixAck` parsed from wire; `data_to_str` `length*2` wrap.

**Settled facts:**
- Ticket 12: healthy image = `05…` verbatim, expect 10638B/10564B. 7684B zeros = degraded session, not threshold.
- `a5029fe` touched only `goodix5e0a.c`/`goodix5xx.c`/`goodixtls.c`, never this path.
- Ticket 50: `g_memdup2` for wire lengths (keep), `0xd4` timeout is success (don't conflate decoder errors with it).

**Status:** closed (verdict: reconciled / rejected strict drops)

**Acceptance:**
- `length>=1` guard before subtract; checksum enforced or explicitly logged+dropped; max-frame cap (e.g. 0xFFFF+header) + `priv->length+length` overflow check; corrupt frame fails command fast (no timeout-stall); trailing bytes preserved or documented drop; unaligned-safe parsing (`memcpy`); `data_to_str` overflow guard + `G_STATIC_ASSERT(sizeof==3)` for packed headers.

## Correction (2026-09-10, hardware-line reconciliation)
- Reverted: checksum enforcement (`INVALID_DATA` fail-fast on protocol /
  pack mismatch, unknown flags, corrupt length, frame cap). Restored
  log-only tolerance (mismatch → `fp_dbg`, deliver). Evidence:
  `~/code/temp/libfprint` `goodix.c` ("calculation is not yet trusted
  against hardware quirks ... dropping here turns into command timeouts").
  The enforcement turned healthy device quirks into claim failures.
- Kept (behavior-neutral): `length>=1` underflow guard, unaligned-safe
  `memcpy` parsing, `data_to_str` overflow guard, packed-header
  `G_STATIC_ASSERT`s, typo fix.
- Smoke per AGENTS.md rule 7 after deploy.

## Final Audit & Closure (2026-09-11)
- Verdict: CLOSED (reconciled / rejected strict drops).
- Findings:
  1. Strict checksum enforcement fails on real hardware due to benign Goodix firmware null-checksum modes (`0x88`) and MCU quirks. Dropping packets causes command timeouts.
  2. Protocol layer must maintain log-only tolerance (`fp_dbg`) for checksum mismatches while delivering payloads.
  3. Arithmetic underflow guard (`wire_len < 1`) and `memcpy` alignment safety are noted for routine maintenance, but do not warrant a behavioral overhaul.
