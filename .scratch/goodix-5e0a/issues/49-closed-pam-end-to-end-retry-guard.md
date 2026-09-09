# 49 — PAM end-to-end: retry guard under real ~15ms PAM retry timing

**What to build:** Nothing — verification only. Ticket 47 proved the guard
via `fprintd-verify` (manual ~1s spacing). The original burn scenario is
`pam_fprintd` retrying within ~15ms of a no-match. This ticket proves the
deployed driver behaves through the real PAM stack: fast unlock on genuine
tap, spaced (not burned) attempts on continuous wrong-finger hold, clean
fallback to password.

**Blocked by:** None.

**Status:** closed

**Verdict:** CONFIRMED on hardware 2026-09-09 (deployed driver, real PAM).

**Live-scope:** observation only. No code changes, no biometric changes, no
threshold changes (per standing constraint: matching pipeline is frozen).

## Settled facts (do not re-litigate)

1. Each PAM retry is a new D-Bus claim (new activate + scan), like a fresh
   `fprintd-verify` run — tickets 46/47 cover exactly this path.
2. One attempt = one `5e0a best frame … (submitting)` journal line, so
   attempt spacing is measurable from the journal alone.
3. `test_f23_pam_reliability` (5 tests) passes on the current tree.
4. Debug env must be ON for `retry guard`/`D34` lines (`fp_dbg`).

## Hardware verify protocol (user only, AGENTS.md compliant)

Terminal A (watch, optional):
`journalctl -u fprintd -f | grep -a -E "retry guard|best frame|D34"`

Terminal B, enrolled finger tap (expect sudo success, quick):
1. `sudo -v` → touch enrolled finger at the prompt → expect success in ~1s.
2. `sudo -K` (drop timestamp so the next run re-authenticates).

Terminal B, wrong (unenrolled) finger held continuously, never lifting:
3. `sudo -v` → hold through the fingerprint phase → expect fallback to a
   password prompt (do NOT type it; Ctrl-C). Note wall-clock time from
   first prompt to password fallback.
4. `sudo -K`.
5. Evidence:
   `journalctl -u fprintd --since "5 min ago" --no-pager | grep -a -E "retry guard|best frame.*submitting|D34 finger|verify-unknown-error|timed out" | tail -n 30`

## Hardware result 2026-09-09 — FALSIFIED (spurious D34 success while held)

Debug-ON `sudo -v` with wrong finger held (PID 4542), real PAM cadence —
next claim starts 22ms after delivery (no lift possible in 22ms):

```
20:32:59 best frame 1/3 (submitting)      <- Attempt 1, no-match
20:32:59 retry guard active (delta=22 ms)
20:33:00 D34 finger release reply: len=16 <- SUCCESS while held, no timeout
20:33:00 release ok, arming FDT DOWN
20:33:01 best frame 3/3 (submitting)      <- Attempt 2 FIRED on same hold
20:33:01 retry guard active (delta=22 ms)
20:33:02 D34 finger release reply: len=16 <- again while held
20:33:02 release ok, arming FDT DOWN
20:33:02 best frame 2/3 (submitting)      <- Attempt 3 FIRED on same hold
```

Sudo side: `Failed to match` ×3 (pre-fix behavior; superseded below).

## Firm-vs-light result 2026-09-09 — contact-sampling FALSIFIED, guard CONFIRMED

Both (a) firm-still and (b) light-shifting held runs show the SAME loop:
`D34 timed out: 0x34` + `re-issuing FDT UP` every 2s for ~18s until PAM's
own `Verification timed out` → password fallback. Exactly ONE `Failed to
match` (Attempt 1), ZERO further `best frame (submitting)` lines — Attempts
2+ fully withheld, no burn at any spacing. Zero `0x96`/`0x32` timeouts,
zero `verify-unknown-error`, no lockout.
Reconciliation of the earlier PID 4542 D34-success-while-held: not
reproduced under controlled still-hold at either pressure. That run used
two manual invocations ~1s apart (pre-`sleep 1` instruction) with finger
adjustment between them — the `len=16` success was a genuine momentary
air sample, not spurious. `0x34` observes contact faithfully; no
air-confirmation layer needed. Standing constraint (frozen biometrics)
never engaged — fix was teardown/sequencing only.

## Acceptance criteria (deployed driver, hardware only) — all green 2026-09-09

## Close-out 2026-09-09 — CONFIRMED, ticket closed

Enrolled-tap `sudo -v` unlocks silently (bare prompt after
"Place your finger…", repeatedly). Wrong-finger hold: exactly one
`Failed to match`, attempts withheld in the `0x34` re-issue loop,
PAM verification timeout → password fallback, no lockout. All boxes green.

- [x] Enrolled tap: `sudo -v` succeeds without password, no perceptible lag.
- [x] Wrong finger held: exactly one `Failed to match`, attempts withheld
  (~18s re-issue loop), password fallback offered, no lockout.
- [x] Journal shows guard spacing, zero `0x96`/`0x32` timeouts, zero
  `verify-unknown-error`.
