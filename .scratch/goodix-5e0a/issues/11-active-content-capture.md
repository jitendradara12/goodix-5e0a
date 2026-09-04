# 11 — Active-mode capture with 01-payload (replaces 10)

**What to build:** Active-mode capture loop using proven `01 00...` image payload
with internal content gating (advancing only when frame contains non-zero
pixels), eliminating the 7-8s empty-air retry loop. Hands-off enroll stays
silent, press-and-hold advances stages to completed enroll.

**Blocked by:** None — ready now.

**Status:** ready-for-agent

## Background Evidence & Falsifications (Hardware Proven, Do Not Re-litigate)

1. **35B FDT does NOT block on APP_10036:**
   Hardware test on 2026-09-04 15:22:45–15:23:46 (Phase 1, 61s hands off) proved
   `0x32` with 35B S12 table returns `status=0x02 len=20` immediately in ~10ms
   on empty air. It is a mode acknowledgement, not a touch gate.
2. **Payload `05` produces pure blanks:**
   Hardware test on 2026-09-04 15:24:39 (Phase 2, firm hold) proved `0x20` with
   payload `05 00 b0 00 b2 00 b0 00 b1 00` returns 7684 bytes of pure `0x00`
   (`num_px=5120 nonzero=0 min=0 max=0`).
3. **Payload `01` is the proven content path:**
   `experiments/test_press_and_capture.py` and `windows_driver/wbdi.dll`
   disassembly (`_FpMcuGetImage`) corroborate `01 00 00 00 00 00 00 00 00 00`
   (10 bytes). It produced real live frames with 19 active columns at `4k+3`
   (`min=0, max=387, active=697`, saved as `/tmp/touch_test_raw.pgm`).
4. **Register 0x022c write is eliminated:**
   Bypassing `0x022c` during activation produced identical results to `0x030a`.
   Windows never writes `0x022c` in the capture. Kept bypassed.

## Precise Changes

1. **Image Payload in `libfprint-driver/goodix.c` & `goodix5e0a.h`:**
   Change capture payload to 10 bytes:
   `goodix5e0a_capture_payload[10] = {0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};`
2. **Content-Gated Loop in `goodix5e0a.c`:**
   - In `goodix5e0a_on_read_img`, check `total_nonzero`:
     - If `total_nonzero < 100` (empty air / no touch): Do **NOT** pass empty
       frame to minutiae detection (which causes `enroll-retry-scan` spam).
       Instead, delay ~200ms and re-capture internally within the SSM or
       restart scan without reporting `fpi_image_device_image_captured`.
     - If `total_nonzero >= 100` (finger detected): Process frame, report
       `fpi_image_device_image_captured`, proceed to `0x34` release wait.
3. **Remove FDT DOWN `0x32` dependence for touch gating:**
   Skip waiting for `0x32` as touch gate, or treat `0x32` as non-blocking mode
   switch, relying on internal frame content (`total_nonzero >= 100`) as the
   sole touch gate.

## Acceptance Criteria (Deployed Driver, Hardware Only)

- [ ] Phase 1 (60s hands off): silent, zero `enroll-retry-scan` lines, no session churn.
- [ ] Phase 2 (60s press-and-hold): stage advances within seconds of touch.
- [ ] Journal shows non-zero content (`nonzero > 0`, `active > 0`).
- [ ] Multi-stage enrollment completes; verify matches.
