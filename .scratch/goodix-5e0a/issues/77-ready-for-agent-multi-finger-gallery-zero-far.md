# 77: Multi-Finger Gallery Verification & Zero-FAR Hardware Validation

**What to build:** Full multi-finger enrollment and authentication with zero false acceptance rate across enrolled fingers (un-enrolled fingers and different fingers are strictly rejected with 0 score, while all enrolled fingers unlock on first touch).

**Blocked by:** 76 (closed 2026-09-14, verdict falsified — driver behaves as ticket-39 minutiae judging; gallery isolation is independent of frame ranking, so this ticket is unblocked)

**Status:** ready-for-agent

## Acceptance Criteria

- [ ] Multiple distinct fingers (e.g. right index, right thumb, left index) can be enrolled consecutively without template collisions or state corruption.
- [ ] Each enrolled finger authenticates cleanly (`verify-match`) in single-touch unlock.
- [ ] Non-enrolled fingers and un-enrolled persons are 100% rejected (`verify-no-match`) with zero false acceptances across repeated trials.
- [ ] Rule-7 smoke check passes on live journal: `journalctl -u fprintd` has zero unhandled timeouts or errors.

## Context & Evidence

- User originally observed: "when you have multiple fingers enrolled, it also unlocks with any finger if you try enough. the accuracy just sucks and it's not my drivers, it's the fundaments which i don't think would be possible in linux."
- In Ticket 72 offline shootout, Milan achieved 0.0% FAR across different fingers and noise.
- This ticket validates full multi-finger gallery isolation and 0% FAR on live hardware under fprintd.
