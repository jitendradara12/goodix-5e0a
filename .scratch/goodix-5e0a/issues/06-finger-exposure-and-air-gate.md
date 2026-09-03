# 06 — Finger exposure and air-gate validation

**What to build:** The enrolled template is a real finger and empty air can never create one. The finger-capture exposure and the empty-air rejection gate are proven on hardware: full enroll on touch, nothing but rejected frames on air, minutiae actually present.

**Blocked by:** 05 — FDT touch-wait on real hardware (frames are meaningless before touch gating works).

**Status:** ready-for-agent

- [ ] A full multi-stage enroll completes on a real finger.
- [ ] Daemon logs show minutiae extracted from enrollment frames (no zero-minutiae templates stored).
- [ ] Air-only frames are rejected before template storage — air can never complete an enroll.
- [ ] `fprintd-verify` matches the enrolled finger.
