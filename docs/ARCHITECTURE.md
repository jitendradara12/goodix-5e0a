# Architecture (final goal, stated first)

Host-image `libfprint` driver: the sensor streams encrypted frames over bulk
USB, the driver decrypts, decodes, and normalizes them into grayscale images,
and the in-tree NBIS extractor plus Bozorth3 matcher decides. No on-chip
template storage, enroll, or match.

## Pipeline

1. **Transport**: bulk endpoints, interface 0; flush-tolerant NOP, reset,
   chip-ID read, OTP identification read (`0xa6` — its use as a crypto
   fix is falsified in ticket 26), firmware check, ChicagoH provisioning,
   chip enable, then TLS 1.2 PSK session (`TLS_PSK_WITH_AES_128_CBC_SHA256`,
   warm-session only: cold boot disagrees on the key, ticket 26).
2. **Touch gating**: sampled finger-down replies; touch iff the channel byte
   is live and channel energy is positive — never the status byte. Idle
   replies re-sample on a short silent timer.
3. **Capture**: full decrypted wire frame per touch; empty air stays silent
   and never becomes a template.
4. **Decode**: strip the active prefix of each of the eighty blocks, discard
   deterministic zero padding and footer, unpack 12-bit words in block order
   into the native 64x80 raster.
5. **Image**: 3x3 local-mean residual flattening, direct mid-gray contrast
   mapping at unity gain, 2x bilinear upscale to 128x160, inverted polarity
   for capacitive ridges, explicit 500 DPI resolution.
6. **Match (host)**: NBIS minutiae extraction; enrollment admits only touches
   clearing the enrollment floor of twelve (faint touches retry with a
   firmer-press prompt); verification forwards every capture to the matcher;
   match threshold twelve with the in-tree floor of ten.

## Decisions

- **Host matching, not match-on-chip**: the firmware exposes capture and
  finger-detect primitives only — no store, enroll, or match — and a custom
  matcher would be a second invention to sell upstream alongside the driver.
  The MR argues an image driver with software matching and brings
  pixel-compared capture tests, not storage-protocol tests.
- **Canonical wire layout**: eighty blocks of 96 active bytes plus 36 zero-pad
  bytes with a short footer, decoded in block order. Contiguous unpack
  swallowed pads as pixels; strided-transpose sliced scanlines, inverted
  correlation, and zeroed minutiae; sibling-family geometries sheared
  scanlines. Any geometry change needs correlation plus minutiae evidence
  against this baseline, never visual inspection.
- **Sampled gating, not a blocking wait**: the MCU answers in milliseconds
  even on empty air, so a blocking wait fires on stale data or hangs on the
  first collision; the status byte cannot separate idle air from poor
  contact. Cancellation disarms the re-sample timer and the scan state
  machine together; latency work builds on prompt capture, not on removing a
  wait that never existed.

## Frozen (do not re-litigate without journal-backed reason)

- USB transport shape, reset phasing, TLS-PSK handshake wiring and cipher,
  ChicagoH provisioning blob and checksum, firmware identity, PSK flags.
  Live key agreement is NOT frozen: cold boot fails the record MAC
  (ticket 26, the current workfront).
- Channel-energy gating rule; silence on empty air.
- Canonical wire layout and native raster geometry with inverted polarity.
- Synchronous teardown: reset state, shut down TLS, stop the read loop,
  complete immediately.
- Class shape: image device, press scan type, eight enrollment stages,
  128x160 image, match threshold twelve.

## Active (the only legal workfront)

- Ticket 26: cold-boot PSK disagreement (TLS is warm-only until key
  provisioning lands; owns the `0xe0`/`0xe4` experiments).
- Tickets 19–20: PAM/sudo lifecycle and sub-300ms instant release
  (implemented, awaiting hardware verdicts).
- Tickets 21–24: transport memory hygiene, compile-link isolation, base
  runtime hardening, per-frame debug dump removal.
- Upstream packing: logical commits, Meson and device-table wiring,
  `umockdev` replay coverage; see `docs/UPSTREAM.md`.

## Retired (must not be followed)

- Blocking finger-down wait, status-byte gating, `01`-first capture payload,
  contiguous first-bytes decode, strided column extraction with transpose,
  sibling-family geometries, POV handshake requirement, verify-path retry
  scans. The ticket chain `14 → 15 → 16 → 17 → 18` records the sequence.
  Superseded tickets read like live instructions — check the `Status` header
  before acting.

## Errata (traps for future readers)

- TLS works only while MCU SRAM holds the warm key; after power loss the
  MCU reports a different key and rejects the record MAC. The
  OTP-read-as-crypto-fix hypothesis is falsified in ticket 26.
- The OTP priming command is `0xa6`, not `0x94` (`0x94` is the
  powerdown-scan frequency command). Some progress notes say `0x94`; the code
  is correct.
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

Journal lines and packet numbers beat prose. This file and `README.md` are
claims; `journalctl -u fprintd` output, `umockdev` traces, and the hermetic
suite are evidence. `README.md` is aspirational by policy (`AGENTS.md`);
trust it last.
