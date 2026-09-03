# 05 — FDT touch-wait on real hardware

**What to build:** Enrollment advances only on physical touch. The finger-detect arming order and the post-finger release step are validated against a real finger on this unit — no invented payloads, no instant air-advance, no infinite wait.

**Blocked by:** 01 — Flush-tolerant NOP, 04 — Discover the frame-data key.

**Status:** verified-on-hardware

Live-trace evidence & resolution (2026-09-03):
- Root cause of always-fire: `SCAN_STAGE_SWITCH_TO_FDT_DOWN_ARM` was sending 0x32 with `noreply`, but the MCU actually generates a 17-byte reply (`a0 18 00 b8 32...`). This reply was left in the USB IN queue and immediately popped by the subsequent 01-WAIT stage within 0.01s on empty air.
- Fix: Bypassed redundant 00-ARM stage in `goodix5xx.c`. The 01-wait now blocks cleanly on empty air, and wakes up immediately on physical finger touch.

- [x] 60 seconds of air-idle produces zero enroll-stage advances (verified on hardware).
- [x] Each physical press-and-lift advances exactly one enroll stage.
- [x] No invented release command remains: verified via hardware packet captures.
