# Architecture (final goal, stated first)

Host-image `libfprint` driver: the sensor streams encrypted frames over bulk
USB, the driver decrypts, decodes, and normalizes them into grayscale images,
and the in-tree NBIS extractor plus Bozorth3 matcher decides. No on-chip
template storage, enroll, or match.

## Pipeline

1. **Transport**: bulk endpoints, interface 0; flush-tolerant NOP, FW check (RESET skipped, ticket 45; chip-ID/OTP reads cold-path only), Geneva 16-byte PSK-latch read of slot `0xbb020001` (cold path, ticket 48), then TLS 1.2 PSK session (`TLS_PSK_WITH_AES_128_CBC_SHA256`), post-TLS config upload (cold path), chip enable.
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
   match threshold fourteen with the in-tree floor of ten.

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
  Key agreement: ticket 48 (cold-boot `bad record mac` root-caused to
  unlatched MCU crypto registers; Geneva 16-byte `0xe4` read of `0xbb020001`
  pre-TLS latches them, config uploads post-TLS; ticket 26's 8-byte-framing
  falsification stands, its conclusion is reversed). Reopen only on a pasted
  record-MAC recurrence.
- Session lifecycle: idle-only TLS park gating (46), 0x34-timeout re-issue
  with cancel-drop in the retry guard (47), warm fast path (40). Retry
  claims park in FDT-UP until genuine release.
- Channel-energy gating rule; silence on empty air.
- Canonical wire layout and native raster geometry with inverted polarity.
- Synchronous teardown: reset state, shut down TLS, stop the read loop,
  complete immediately.
- Class shape: image device, press scan type, five enrollment stages,
  128x160 image, match threshold fourteen.

## Active (the only legal workfront)

- All driver tickets (01–49) closed. Upstream rebase, power management, and authentic umockdev capture complete.
- Upstream repo checkout: `/home/sastauser/code/temp/libfprint-upstream` (`test-5e0a` branch).
- Next legal workfront: upstream GitLab Merge Request against `freedesktop.org/libfprint/libfprint`.

## Retired (must not be followed)

- Blocking finger-down wait, status-byte gating, `01`-first capture payload,
  contiguous first-bytes decode, strided column extraction with transpose,
  sibling-family geometries, POV handshake requirement, verify-path retry
  scans. The ticket chain `14 → 15 → 16 → 17 → 18` records the sequence.
  Superseded tickets read like live instructions — check the `Status` header
  before acting.

## Errata (traps for future readers)

- Cold-boot TLS now works via the ticket-48 PSK latch; the "warm key only"
  era ended 2026-09-09 (hardware-verified true cold boot + debug re-run).
  Reopen only on a pasted record-MAC recurrence.
- The OTP priming command is `0xa6`, not `0x94` (`0x94` is the
  powerdown-scan frequency command). Some progress notes say `0x94`; the code
  is correct.
- Native geometry is 64 wide by 80 tall; early notes using 80x64 describe the
  falsified transpose era.
- Test-suite totals drift across notes (375 / 385 / 387 / 433). Recount from
  the source of truth with the runner (`bash tests/run_all_tests.sh`;
  448 across tiers 1–5, all green as of 2026-09-09) instead of quoting a
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
