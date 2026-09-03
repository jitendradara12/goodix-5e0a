# 07 — Back-to-back verify and PAM stability

**What to build:** Repeated verification and system-auth logins work without timeouts and without daemon restarts — the original multi-run failure loops stay fixed, including across activation/deactivation cycles.

**Blocked by:** 06 — Finger exposure and air-gate validation (stability is untestable before enroll and verify work once).

**Status:** ready-for-agent

- [ ] Five consecutive `fprintd-verify` runs complete with no timeouts and no daemon restart.
- [ ] sudo and lock-screen authentication succeed repeatedly via PAM.
- [ ] No command-timeout or unknown-error appears in the daemon log across the whole sequence.
