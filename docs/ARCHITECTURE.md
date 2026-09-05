# Architecture (final goal, stated first)

This driver is a **host-image `libfprint` driver**: the sensor streams encrypted
frames over bulk USB, the driver decrypts, decodes, and normalizes them into
grayscale images, and the in-tree NBIS extractor plus Bozorth3 matcher decides.
There is no on-chip template storage, no on-chip enroll, and no on-chip match.
Read `docs/adr/0001-host-image-matching.md` before touching the match path.

## Pipeline

1. **Transport**: bulk endpoints, interface 0; flush-tolerant NOP, reset,
   chip-ID read, OTP priming, firmware check, ChicagoH provisioning, chip
   enable, then TLS 1.2 PSK session (`TLS_PSK_WITH_AES_128_CBC_SHA256`).
2. **Touch gating**: sampled finger-down replies; touch if and only if the
   channel byte is live and channel energy is positive — never the status
   byte. Idle replies re-sample on a short silent timer. See
   `docs/adr/0003-sampled-touch-gating.md`.
3. **Capture**: full decrypted wire frame per touch; empty air stays silent
   and never becomes a template.
4. **Decode**: strip the active prefix of each of the eighty blocks, discard
   deterministic zero padding and footer, unpack 12-bit words in block order
   into the natural raster. See `docs/adr/0002-canonical-wire-layout.md`.
5. **Image**: local-mean residual flattening, direct mid-gray contrast mapping
   at unity gain, 2x bilinear upscale to 128x160, inverted polarity for
   capacitive ridges, explicit 500 DPI resolution.
6. **Match (host)**: NBIS minutiae extraction; enrollment admits only touches
   clearing the enrollment floor (faint touches retry with a firmer-press
   prompt); verification forwards every capture to the matcher; match
   threshold twelve with the in-tree floor of ten.

## Frozen (do not re-litigate without journal-backed reason)

- USB transport shape, reset phasing, TLS-PSK negotiation, ChicagoH
  provisioning blob and checksum, firmware identity, PSK flags.
- Channel-energy gating rule; silence on empty air.
- Canonical wire layout (active prefix per block, zero padding, footer) and
  natural raster geometry with inverted polarity.
- Synchronous teardown: reset state, shut down TLS, stop the read loop,
  complete immediately.
- Class shape: image device, press scan type, eight enrollment stages,
  128x160 image, match threshold twelve.

## Active (the only legal workfront)

- Hardware verification of PAM/sudo lifecycle and sub-300ms instant release
  (tickets 19, 20 — implemented, awaiting hardware verdicts).
- Transport memory-hygiene validation run, compile-link isolation of shared
  code from model-specific symbols, base runtime hardening, per-frame debug
  dump removal (tickets 21–24).
- Upstream packaging: patch split into logical commits, Meson and device-table
  wiring, `umockdev` replay coverage; see `docs/UPSTREAM.md`.

## Retired (must not be followed)

- Blocking finger-down wait, status-byte gating, `01`-first capture payload,
  contiguous first-bytes decode, strided column extraction with transpose,
  sibling-family geometries, POV handshake requirement, verify-path retry
  scans. Each was superseded or falsified with hardware evidence; the ticket
  chain `14 → 15 → 16 → 17 → 18` records the sequence. Superseded tickets
  read like live instructions — check the `Status` header before acting.

## Errata (traps for future readers)

- The OTP priming command is `0xa6`, not `0x94` (`0x94` is the powerdown-scan
  frequency command). Some progress notes say `0x94`; the code is correct.
- Native geometry is 64 wide by 80 tall; early notes using 80x64 describe the
  falsified transpose era.
- Test-suite totals drift across notes (375 / 385 / 387). Recount from the
  source of truth with per-module runs (`python3 -m unittest
  tests.tier1_feature.test_<name>` from the repo root) instead of quoting a
  note.
- Contrast gain and enrollment floor changed between the first-match era
  (gain 2.5, floor fifteen) and the current tree (unity gain, enroll-only
  floor twelve with verify passthrough). Quote the tree, not the old ticket.
- The double-match and PAM-stability journals live in progress notes, not
  inside their tickets — re-prove them on hardware before building on them.

## Evidence hierarchy

Journal lines and packet numbers beat prose. This file, `README.md`, and
`docs/PROGRESS.md` are claims; `journalctl -u fprintd` output, `umockdev`
traces, and the hermetic test suite are evidence. `README.md` is
aspirational by policy (`AGENTS.md`); trust it last.
