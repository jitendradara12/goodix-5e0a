# Decision 61: keep parked single-TLS (no dual-TLS merge)

Status: decided (offline architecture review; hardware falsifiers named below).
Default: **no change** — the parked single-TLS session (tickets 38/40/46)
stays, and nothing from the /tmp/libfprint dual-TLS design is merged.

## What dual-TLS would bring (all reviewed, none adopted)

| Piece (their tree) | What it does | Why it is not needed here |
|---|---|---|
| Cmd TLS with zero-PSK + image TLS with per-device PSK | Two negotiated contexts: commands on one, images on the other | Our single parked context already carries every post-handshake command (0x90 config, 0x32/0x34 FDT, 0x20 image) on one cipher suite (`PSK-AES128-CBC-SHA256`); journal shows one `TLS connection ready` per ladder, no per-command re-handshake |
| `POV 0xD6` check in the activate ladder | Wake-on-finger image poll before TLS | Our flow skips POV by design (no wake-on-finger product requirement); a second TLS context to serve a poll we do not send buys nothing |
| Separate `image_tls_hop` + `tls_read_image_5e0a_with_payload` | Image reads on the image context with an explicit payload | Our `goodix_tls_read_image` on the parked context delivers full 10564B frames (ticket 12: `05…` verbatim `B2 pack10638/declen 10564`); no payload variant has been needed on FW 10036 |
| Per-device PSK via file for the image context | File-backed image key | Covered read-only by ticket 59 on the single context instead |

## Why parked single-TLS is sufficient (evidence to cite on hardware)

- Reuse is proven by the health probe, not assumed: one `0xae`
  `QUERY_MCU_STATE` round-trip (500ms budget) gates every park reuse; a
  dead device-side key fails fast into the full ladder (ticket 38), and a
  mid-FDT_DOWN teardown never parks (ticket 46).
- Warmth is host-observed recency, never a device-key claim: the handshake
  always runs (ticket 40), so session-key staleness cannot hide.
- `0xd4` timeout-is-success and the cold `0xe4` latch (tickets 48/50) are
  single-context behaviors with no dual-context counterpart needed.

## What would falsify this decision (any one reopens the ticket)

1. Parked reuse fails with crypto errors (`bad record mac`, dead
   device-side key surviving the `0xae` probe) in a case where a fresh
   dual-TLS command channel succeeds — cite journal + pcap.
2. The MCU rejects image/FDT commands on the single context (e.g. `0x20`
   or `0x32` NACK/timeout post-handshake) while a separate image-TLS
   context serves them — cite packet numbers.
3. A measured regression attributable to one context (wake latency, power)
   that two contexts remove — cite numbers, not prose.

Until then: no dual-TLS merge, no matcher/geometry default changes
(tickets 58/60 decide those on captured-frame metrics).
