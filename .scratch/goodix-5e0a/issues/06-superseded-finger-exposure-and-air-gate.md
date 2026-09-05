# 06 — Finger exposure and air-gate validation

**What to build:** The enrolled template is a real finger and empty air can never create one. The finger-capture exposure and the empty-air rejection gate are proven on hardware: full enroll on touch, nothing but rejected frames on air, minutiae actually present.

**Blocked by:** 05 — FDT touch-wait on real hardware (frames are meaningless before touch gating works).

**Status:** superseded by 08 — content flows via the active-mode path proven by the
script capture; exposure/gate tuning happens inside 08's poll-until-content
loop, not as a separate stage.

Live-trace evidence & resolution (2026-09-03):
- Root cause: `goodix.c` was sending `45 03 a7 00 a1 00 a7 00 a3 00` (an unverified prototype artifact from `driver_52xd.py`) for `mcu_get_image` (`0x20`). This caused the sensor die to return all-zero frames (7,680 bytes of `0x00`).
- Disassembly of `windows_driver/wbdi.dll` at `0x4c0a6` (`_FpMcuGetImage`) revealed Goodix zeroes a 10-byte buffer and sets byte 0 to `0x01`.
- Live hardware capture with payload `{0x01, 0x00...}` delivered 817 non-zero raw pixels, 14,727 active demosaiced pixels, and visually clear friction ridges across the entire 128x160 frame (`live_captured_finger.png`).

- [ ] A full multi-stage enroll completes on a real finger (requires deployed driver — not yet tested).
- [ ] Daemon logs show minutiae extracted from enrollment frames (requires deployed driver — not yet tested).
- [ ] Air-only frames are rejected before template storage — air can never complete an enroll.
- [ ] `fprintd-verify` matches the enrolled finger (requires deployed driver — not yet tested).
