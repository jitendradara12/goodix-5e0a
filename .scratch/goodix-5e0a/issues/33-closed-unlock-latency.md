# 33 — Unlock latency: kill per-attempt multipliers (user-facing)

**What to build:** Nothing in code until measured. This ticket owns
wall-clock unlock time (PAM/hyprlock), which is attempts × per-attempt cost.

**Blocked by:** None.

**Status:** closed

**Verdict (2026-09-05): dedup CORRECT but speed problem is accuracy, not
attempt count.** De-duplicating was right (3 slots = up to 3 full cycles per
unlock — never re-add duplicates), but single-finger sessions still miss at
11/12-class near-misses with strong probes AND strong gallery. Per-attempt
cost is sub-second (activation) + touch wait; total time = attempts × ~2s and
attempts stay high. Root cause promoted to ticket 35 (genuine-pair
shortfall); energy-gating idea killed by 125-touch analysis (no correlation).
34's stale-guard rides on (zero success-path impact).

## Measured (2026-09-05 21:16 hyprlock session, pid 34659, agent-pulled)

- Per-attempt driver cost is ~1s: VerifyStart :40 → TLS ready :40; :42 → :43.
  Capture+match complete same-second. Touch-wait (user) dominates the rest.
- The 6s = MULTIPLE attempts: PAM iterates enrolled fingers, and the user
  enrolled the same finger 3× ("different parts" trick) → up to 3 full
  activate+capture+match cycles per unlock. Duplicates also confuse coverage
  accounting from ticket 31.
- Same session showed the 19-pattern again: Release at :45 raced an in-flight
  activation (VerifyStart#2's TLS completed AFTER release:
  `Already deactivated, ignoring request` then stale `TLS connection ready!
  Enabling chip...`), followed by Claim denials at :09/:23/:17 until daemon
  restart. Stale post-release completion is ticket 34's fix; the stuck claim
  stays owned by 19.

## Experiment 1 (user, 2 min, no deploy): de-duplicate gallery

1. `fprintd-delete "$USER"`.
2. `fprintd-enroll` the ONE login finger ONCE (12 firm centered presses).
3. Use hyprlock/sudo normally; report perceived unlock time + tries.
- Confirm: worst-case attempts drop 3× → ~2s typical unlocks. Verdict
  confirmed → close (remaining per-attempt ~1s is activation floor work,
  separate ticket only if still slow).
- Falsify: still 3+ tries on single-finger gallery → per-attempt matching
  regressed or PAM iterates spuriously → measure again from journal.
