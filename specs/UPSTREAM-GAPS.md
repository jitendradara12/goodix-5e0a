# Upstream gap adjudication (supersedes the gate in BUGS-5e0a-reverse-engineering-gaps.md)

The research-only gap spec stays immutable history. This file adjudicates
each of its nine items against the current tree and lists what upstream
still requires. Filenames are grep anchors, not line references — verify
against the tree before quoting.

## B-item verdicts

- **B1 (command-number swap)**: fixed. POV-image is `0xd2` and
  handshake-done is `0xd4` (`goodix_proto.h`), and the handshake sender uses
  the latter (`goodix.c`).
- **B2 (driver-state command never sent)**: half-fixed, requirement retired.
  The sender exists (`goodix.c`) but no activation path calls it;
  provisioning succeeds without it on tested hardware, so the strict 52xD
  parity demand is retired, not trace-closed.
- **B3 (POV handshake missing)**: same as B2. Helpers exist, unused; the
  driver ships without the POV leg. Open only if strict sibling-flow parity
  is ever demanded.
- **B4 (wrong image payload)**: superseded and fixed differently. Neither
  the old hardcoded value nor the sibling-family value is used; the frozen
  `05`-first payload matches dozens of identical Windows captures
  (`goodix5e0a.h`, `goodix.c`).
- **B5 (single finger-down without arming)**: reworked. There is no blocking
  wait on this MCU; the driver samples finger-down replies and re-polls
  silently on idle (`goodix5e0a.c`). The old arming-sequence prescription
  must not be implemented.
- **B6 (invented finger-up payload)**: refuted by capture and fixed. The
  finger-up table and its no-reply/reply/no-reply triple is Windows-grounded
  (`goodix5e0a.h`, `goodix5e0a.c`).
- **B7 (synchronous NOP racing the next command)**: partially fixed,
  unverified. NOP is now flush-tolerant in code (`goodix.c`) but its ticket
  is still `ready-for-agent` (ticket 01) — do not mark closed until the
  state-zero advance is observed on hardware.
- **B8 (single-flight guard hanging the state machine)**: fixed to fail
  loud, plus a scan-concurrency guard and sampled gating. Residual
  collision logs from the old era are root-caused, not open.
- **B9 (full-range stretch templating air)**: fixed structurally. Canonical
  strip-decode plus local-contrast pipeline plus the enrollment floor
  replaced the old geometry and normalization (`goodix5e0a.c`,
  `goodix5e0a.h`).

The old testing warning — synthetic payload tests passing while hardware
loops — is stale as a gate (capture-grounded tickets re-derived the
behavior) but stands as caution: synthetic mocks never verify.

## Remaining upstream gaps

1. **Replay coverage**: no `umockdev` traces exist for open, enrollment,
   matching/non-matching verification, cancellation, or suspend/resume.
   The Python tiers are mocks, not replays.
2. **Hygiene** (tickets 21–24): always-on per-frame logging, per-frame disk
   dumps, raw allocation calls, and a cross-driver global in shared code —
   each an upstream refusal reason on its own.
3. **Proof** (tickets 19–20): suspend/resume re-initialization, mid-scan
   cancellation without leaks, and stall timeouts that never hang PAM need
   hardware runs with pasted journal evidence.
4. **Legal**: the MR must disclose the hardcoded secret and provisioning
   blob provenance plus the passive-capture derivation method, with no
   vendor code included (see `docs/UPSTREAM.md` section 6).
5. **Packing**: the monolithic unified patch must become logical commits
   (transport, driver, recordings, device table) each passing CI.
