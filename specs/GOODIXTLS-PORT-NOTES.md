# goodixtls port notes — /tmp/libfprint (branch goodixtls, 55a7379..3111a8b) → this tree

Source of truth for this tree stays the hardware journals + pcap; the other
tree is an independent implementation for a different unit (realme Book Prime,
FW APP_10034, geometry 80x88 flat) vs ours (ChicagoH, FW APP_10036, 64x80
block-aware 10564B wire). Port only what is provably better; ticket the rest.

## Ported (safe, behavior-preserving or tools-only)

1. TLS relay coalesced reads — `libfprint-driver/goodix.c`
   - From: goodixtls@83e5522 `read_all_tls_records()` + `tls_hex_dump()`.
   - What: `goodix_tls_read_all_records()` (5B TLS record framing, poll-50ms
     coalesce, buf-bounded) + `goodix_tls_hex_dump()` (fp_dbg, 128B trunc).
   - Used in the two server→device handshake stages (HELLO_S, CHANGE_CIPHER_S,
     now 4096B). Fixes ticket 51 bullet 1 for the handshake path: a single
     `read()` short count no longer truncates the ServerHello/CCS flight.
   - Not changed: 0xd4 timeout-is-success (ticket 50), parked single-TLS
     model, `goodix_tls_client_read` itself, SSL_ERROR handling / accept
     timeout / deinit re-entrancy (rest of ticket 51 stays open).

2. WhiteBox correction — `experiments/goodix_whitebox.py`
   - The old module used a single-SHA derivation (key = digest[:16]).
     Verified algorithm (RE_WHITEBOX_EXACT.md, whitebox_encrypt.py,
     test vector 32 zeros → `ec35ae3a…6a756c5` 96B) needs the second hash:
     `hash2 = SHA256(prefix + zeros(48) + WB_CONSTANT)`,
     `WB_CONSTANT = 5cba6e25819518de2d53e96dc0347ab0`, key = hash2[:16],
     HMAC key = full hash2, IV = prefix. Module now asserts the KAT.
   - Safety (goodixtls@55a7379): `McuEraseApp 0xA4 [00 32]` bricked a sensor
     into the bootloader when interrupted — never auto-erase from the driver.
     WhiteBox stays a MANUAL provisioning reference (IAP-mode chunked 0xE0,
     rejected in APP mode). Driver does no on-device provisioning.

3. Dynamic-FDT reference — `libfprint-driver/goodix5e0a.h`
   - From: RE_FDT_PAYLOAD_DETAIL.md (SwitchToFdtMode@0x1800585c4,
     CalcFdtDownBase@0x1800632a0, CoreCalcBase + fdt_delta).
   - What: prefix defines + formula comment next to the static tables.
     DOWN `((raw>>1)<<8)|0x80` (no delta); UP `(((raw>>1)+delta)<<8)|0x80`;
     raw = 6x u16LE from FDT_MANUAL 0x36 resp [4..15]; Windows reads base 3x.
   - NOT wired into scan: S12/retry/U01 stay authoritative (77s+85s
     air-silence proven). Integration is ticket 57 (needs hardware run:
     per-unit DAC from OTP, drift falsification, fallback order).

## Deliberately NOT ported (tickets 57-61)

- SIGFM matcher replacing NBIS/Bozorth (touches core fp-image/fpi-print;
  our NBIS pipeline scores 12-18/12 with best-of-N — needs A/B on images).
- Dual cmd+image TLS with per-device PSK file vs our single parked TLS +
  hardcoded host PSK + cold 0xe4 latch (upstream + lifecycle implications).
- 80x88 flat decode vs our 64x80 block-aware (96B×80 strip, 10564B wire);
  geometries disagree — needs image-metric shootout, not a merge.
- squash-thirds + unsharp(r=3,s=4.0) + diversity-reject vs our local-mean
  gain-1.0 + best-of-N minutiae proxy (gain/saturation findings conflict).
- OTP-derived DAC + 3x FDT_MANUAL ladder + 0x90/0xC4/A2 init questions
  (we intentionally omit 0xa2 per ticket 45; 0x90 upload stays post-TLS).

## How to verify the ported bits without fingers

- `python3 experiments/goodix_whitebox.py` → KAT + round-trip PASSED.
- Driver build: ninja drivers-only target per AGENTS.md; no handshake
  behavior change expected on healthy path (relay bytes identical, just
  no longer truncatable). Journal signature on next run: unchanged
  `5e0a frame stats` + no new `TLS-RELAY` errors (fp_dbg only).
