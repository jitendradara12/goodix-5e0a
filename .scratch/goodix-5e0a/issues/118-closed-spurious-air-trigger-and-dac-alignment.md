# 118 — Spurious Air Trigger Bound, Wire DAC Alignment, and Store Canary

**What was built:**
1. Spurious air trigger bound: Bounded retry counter (`air_retries < 5`) and `goodix5e0a_reset_touch_frames` before re-arming `SCAN_5E0A_FDT_DOWN`, preventing runaway burst loops (frame 555 defect).
2. Wire DAC alignment: Correct config offsets (0xc8=0x1f, 0xeb=0xf0, 0xec=0x00), dynamic 16-bit LE additive checksum with seed 0xa5a5 (0x1e4a), and capture payload byte 0 set to 0x01 on `0xad` units.
3. Enrollment release guard stop-loss: 30s timeout on continuous contact in `goodix5e0a_on_fdt_up_reply`.
4. Hardware session store canary: Verified `prints_before_test == prints_after_restore`, 0 isolated prints, and guarded `--restore`.
5. Restored offset layout documentation in `docs/psk-extraction.md` and Jet-Soup attribution in `README.md`.

**Hardware verification runs:**
- Maintainer verification (`6f55ee4e9111c617`): 5/5 genuine matches (pts: 30, 64, 80, 30, 71 on frame 1 fast-path), 5/5 impostor rejections. Silent hands-off (20s), single holding advance, storage isolated, canary verified (7 prints before, 0 isolated, 7 after restore), `restored: true`. Verdict: confirmed.

**Blocked by:** None.

**Status:** closed

**Verdict:** confirmed on live hardware (bundle 6f55ee4e9111c617).
