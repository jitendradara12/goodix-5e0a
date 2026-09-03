# 05 — FDT touch-wait on real hardware

**What to build:** Enrollment advances only on physical touch. The finger-detect arming order and the post-finger release step are validated against a real finger on this unit — no invented payloads, no instant air-advance, no infinite wait.

**Blocked by:** 01 — Flush-tolerant NOP, 04 — Reconcile the TLS PSK (scanning is unreachable before activation and TLS work).

**Status:** ready-for-agent

- [ ] 60 seconds of air-idle produces zero enroll-stage advances.
- [ ] Each physical press-and-lift advances exactly one enroll stage.
- [ ] No invented release command remains: every touch/release payload is backed by a capture or a passing hardware run.
