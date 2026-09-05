# 07 — Back-to-back verify and PAM stability

**What to build:** Repeated verification and system-auth logins work without timeouts and without daemon restarts — the original multi-run failure loops stay fixed, including across activation/deactivation cycles.

**Blocked by:** 08 as written is retired (superseded by 10; see 08 rationale) — its prerequisite is already satisfied: enroll proven by 13 (8/8 stages on hardware), verify proven by 18 (two consecutive matches). This ticket is actionable on hardware as stated.

**Status:** ready-for-agent

- [ ] Five consecutive `fprintd-verify` runs complete with no timeouts and no daemon restart.
- [ ] sudo and lock-screen authentication succeed repeatedly via PAM.
- [ ] No command-timeout or unknown-error appears in the daemon log across the whole sequence.

## Hardware evidence (2026-09-05, post deploy of dead-code-squeeze build)

`sudo echo "hi"` via PAM: two consecutive `Failed to match fingerprint`
followed by a match on the third touch (`hi` printed). TLS and capture
path functional on this warm session; match consistency still
placement-sensitive (future usability workfront, not this ticket).
Five-consecutive-pass criterion NOT yet met — this ticket stays open.
