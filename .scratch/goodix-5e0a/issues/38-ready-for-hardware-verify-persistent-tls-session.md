# 38 — Persistent TLS session across claims (kill per-attempt activation cost)

**What to build:** Keep the negotiated TLS session (and chip-enabled state)
alive across deactivate/claim cycles instead of tearing everything down
after every attempt. Next claim reuses the live session after a cheap
health check; only a failed check falls back to the full ladder
(reset → config upload → handshake → enable). One variable: session
lifetime across `deactivate` (activation ladder, scan SSM, teardown order
otherwise untouched).

**Blocked by:** None. Builds on ticket 33 (measured: ~1s activation per
attempt, total unlock = attempts × ~2s) and Update-3/4 (device key can die
independently of the host — see constraint below).

**Status:** ready-for-hardware-verify

**Live-scope:** session reuse + health-check fallback only. No biometric
tuning, no threshold changes, no warm-path skipping of reset/config (that
is ticket 40's lane — this ticket reuses the session OR runs today's full
ladder, never a third half-bring-up).

## Settled facts (do not re-litigate)

1. Ticket 33 measured per-attempt driver cost ~1s (VerifyStart :40 → TLS
   ready :40; :42 → :43) with capture+match completing same-second.
   Attempts dominate wall-clock, and each attempt today pays full bring-up.
2. Today's teardown is total by design (`deactivate`: gen-bump, state reset,
   SSM free, read-loop stop, TLS shutdown). Suspend path already proved
   teardown-then-reprime is safe; this ticket adds the missing reuse branch.
3. Update-3/4 lesson (hard constraint): the device-side TLS key can die
   while the host session looks alive (SRAM key loss → peer Finished
   bad-record-mac). A naive "keep session forever" makes key-loss sticky
   and converts every later attempt into dead-session hangs. Reuse MUST be
   gated on a lightweight live check (e.g. `QUERY_MCU_STATE` round-trip or
   single FDT poll with short timeout) with automatic full-ladder fallback.
   The new accept-failure gating (fail activation loudly, no dead sessions)
   is the fallback's foundation — reuse it, do not invent a second error
   path.

## Design sketch (agent refines, journal decides)

- `deactivate`: if session healthy, park it (stop read loop, keep TLS ctx +
  chip enable) instead of shutting down; record park timestamp + generation.
- Next `activate`: health-check first. Pass → skip to chip-enable confirm +
  scan. Fail/timeout → today's full ladder (unchanged code path).
- Park expiry: unpark after N seconds idle or on suspend (suspend keeps
  today's teardown — reclaiming sleep safety is out of scope).
- Stale-guard (ticket 34) keeps working: parked session belongs to a
  generation; any racing completion still drops on mismatch.

## Hardware verify protocol (user only, AGENTS.md compliant)

1. Deploy + restart:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Phase 1, single enrolled finger, 3 consecutive `fprintd-verify` runs.
   Record wall-clock per run + paste:
   `journalctl -u fprintd --since "10 min ago" --no-pager | grep -a -E "TLS connection ready|session reu|health|activat|verify-" | tail -n 30`
3. Phase 2, key-loss drill: full poweroff, drain 60s, boot, verify once
   (forces the fallback path on a dead parked session, if any).

### Predicted journal signatures

- **Confirm (close ticket):** runs 2–3 show session-reuse lines, NO
  `TLS connection ready` re-handshake, wall-clock clearly under today's
  ~2s/attempt; Phase 2 falls back to full ladder once with a clear TLS
  error or clean re-handshake, then verifies. Verdict: confirmed → close
  (then file the upstream-pattern question separately — session caching
  has no blessed in-tree precedent yet).
- **Falsify:** reuse path shows `Command timed out` / dead-session hangs,
  OR Phase 2 never recovers without daemon restart. Verdict: falsified →
  next lane is reuse-gate strictness (shorter park TTL, stronger health
  check), NOT removing the fallback.
- **Inconclusive:** mixed timings with finger-wait dominating (user held
  finger late), or missing pasted lines. Verdict:
  `inconclusive-because-[flaw]` + rerun with finger pre-placed.

## Hermetic verification (agent-run 2026-09-06, no hardware)

- Implemented: park-on-deactivate + QUERY_MCU_STATE health-check reuse +
  full-ladder fallback; `goodix_tls_is_alive` helper; suspend always tears
  down. Struct fields `tls_parked/tls_parked_at/tls_parked_gen`, TTL 30s,
  probe timeout 500ms.
- `python3 -m unittest tests.tier1_feature.test_f38_tls_park` — 9/9 green.
- Driver ninja build green (`on_parked_health_reply` in `libfprint-drivers.a`).
- Full suite + patch/NixOS/hash-pin/LOC hygiene re-verified green at
  ticket-40 close-out (425 passed). Unified patch re-rolled by later
  tickets; see docs/PROGRESS.md Staged NixOS Patch line for current hash.
- NO wall-clock improvement claimed — runs 2-3 timing delta is hardware-only.

## Hardware finding 2026-09-06 (falsified-as-implemented, corroboration pending)

- Deployed build `3c4ed07e` verified live (`TLS connection ready` lines
  present). Across ~20 claims (pids 146872–149977) NO `session reused`
  line appears; every claim falls through to the full ladder.
- Root cause (code): fprintd opens per claim and `goodix_dev_init`
  (`img_open`, `goodix.c:1298-1326`) runs `g_usb_device_reset()` on every
  open — wiping the device-side TLS key before activate runs, so the
  health-check can only fail into fallback. Park is stamped at deactivate
  but murdered at the next open. design assumption "park across claims"
  missed the open/reset between them.
- Successor: ticket 42 (conditional USB reset). If 42 confirms, this
  ticket re-verifies with ZERO code changes. Formal close verdict after
  the corroborating `session reu|parked|health` grep lands.

## Mechanism update (code inspection, same day)

Corroboration landed: EVERY post-first-claim shows `parked TLS session
unhealthy (gen-mismatch)` — never tls-error/expired/timeout, never reuse.
A second killer was found in the same lifecycle: `goodix_dev_deinit`
(the CLOSE handler, `goodix.c:1380`) runs `goodix_activation_gen_bump()`
AND `goodix_shutdown_tls()` on every close. Full per-claim kill chain:
open (reset + boot_seq++) → activate (pre=A, bump) → verify →
deactivate (bump, park gen=A+2, host TLS alive) → close (bump A+3, host
TLS destroyed) → next activate: pre=A+3 ≠ A+2 → gen-mismatch cleanup.
Deterministic, matches 100% of journal lines (first claim per PID clean,
all later ones mismatch). Ticket 42's scope is extended to cover this:
deinit must not bump-or-destroy on a clean close, and `boot_seq++` must
fire only when the reset is actually taken — same one variable
(clean-vs-dirty session lifetime), not scope creep.
