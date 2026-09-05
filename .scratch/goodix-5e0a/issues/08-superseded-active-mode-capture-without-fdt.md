# 08 — Active-mode capture without FDT (replaces 05-rest and 06)

**What to build:** Enrollment driven by frames captured in continuous active
mode with no FDT mode-switching at all, advancing only when a polled frame
actually contains finger content. End-to-end: hands-off enroll stays silent,
press-and-hold advances stages to a completed enroll, verify matches.

**Blocked by:** superseded by 10 (Windows USBPcap ground truth) — see 10 for
what survives (polling UX lessons, metrics logging) and what was wrong
(39B tables, 01/45 payloads, 80x64 geometry, no-poll-query).

**Status:** superseded by 10 (retired 2026-09-05 — do not implement; see rationale below)

> Retirement rationale (static, no hardware): this ticket's own header already
> routes succession through 10, and every implementable premise below has since
> been falsified on hardware and frozen otherwise — `01`-first image payload
> (ground truth is `05…`, `goodix5e0a.h:76-78`, pinned by `test_img_payload_exactness`),
> 80x64 geometry (frozen 64x80, `goodix5e0a.h:14-15`, Runs 13–17), and skipping
> the FDT stages (driver retains `SCAN_STAGE_SWITCH_TO_FDT_DOWN`, and
> `test_b16_empty_air_thresholds` gates on it). Applying "Precise changes" as
> written would revert tickets 14–18. The acceptance criteria above remain
> valid as outcome definitions; the prescribed implementation does not.

## Background evidence (all verified, do not re-litigate)

1. The `0x32` reply arrives in ~10ms on empty air on this firmware
   (`GFUSB_GM168SEC_APP_10036`). It acknowledges a mode switch; it is NOT a
   touch event. The driver mistook it for touch, captured instantly in
   low-power comparator mode, got blank frames, tore down the session, and
   repeated every 2–3s forever. Every threshold tweak tuned the wrong thing.
2. The proven working path is `experiments/test_press_and_capture.py`:
   `nop → reset → read-reg → read-otp → TLS → upload-config → enable-chip`
   with FDT never touched, finger held, `0x20` capture with 10-byte
   `01 00…` payload. It produced a live hardware frame with exactly 19 live
   columns at `4k+3` and periodic row modulation (ridge structure), saved as
   `/tmp/touch_test_raw.pgm` + `/tmp/touch_test.pgm` (copies may vanish on
   reboot — re-capture if missing).
3. Disassembly of `windows_driver/wbdi.dll` (`_FpMcuGetImage`) corroborates
   the 10-byte zero-buffer + byte0=`0x01` capture payload. The older
   `45 03…` sequence from APP_10019-era scripts is retired on this firmware.
4. The `+0x18` FDT-threshold experiment (prior commit) is REVERTED by this
   ticket: thresholds were tuning a comparator that is no longer on the
   capture path. Restore the 52xD tables verbatim to minimize diff from the
   reference.
5. The `0x022c` register-write bypass (prior test commit) is KEPT: the proven
   path writes no register. Its true purpose is an open follow-up, not this
   ticket.
6. Settle-time is handled structurally, not measured: polling until content
   absorbs both no-touch waits and any post-enable settling, so no explicit
   delay experiment is needed (option 2 from the proposal, subsumed here
   with rationale).

## Precise changes (all inside `libfprint-driver/goodix5xx.c` + `goodix5e0a.c` only)

- In `scan_run_state`, SKIP `SCAN_STAGE_SWITCH_TO_FDT_MODE`,
  `SCAN_STAGE_SWITCH_TO_FDT_DOWN_ARM`, `SCAN_STAGE_SWITCH_TO_FDT_DOWN`, and
  the release stage (`SCAN_STAGE_SWITCH_TO_FTD_UP`): with FDT never entered,
  no release step exists. Keep `SCAN_STAGE_QUERY_MCU` and `SCAN_STAGE_GET_IMG`.
- Turn `SCAN_STAGE_GET_IMG` into poll-until-content: after each capture, run
  the existing gate (active/range check in `process_raw_frame`). On empty
  frame, wait briefly (~500ms, reuse the existing device-timeout mechanics)
  and re-capture WITHOUT tearing down TLS/session/activation. On content
  frame, proceed exactly as today.
- Keep: `0x20` capture payload `01 00…` (10 bytes), native 80x64 geometry,
  per-frame `g_message` logging (active/min/max/range/declen) until
  acceptance, then remove the log line in the same ticket.
- Do NOT touch: `libfprint-driver/goodix.c`, `goodix.h`, `goodix_proto.h`,
  `goodixtls.c` (frozen proven transport); `tests/` (separate lane);
  activation reg-write bypass (kept as decided above).
- Rebuild derivation with `nix-build`, refresh the unified patch, commit.

## Acceptance criteria (ALL require the deployed driver on hardware — script
runs do not count; lesson learned from prior false "verified" marks)

- [ ] 60s hands-off `fprintd-enroll`: silent, zero `retry-scan` (polling stays internal, no session churn).
- [ ] Press-and-hold: first stage advances within ~10s of touch.
- [ ] Full multi-stage enroll completes on a real finger.
- [ ] Daemon journal shows content frames (`active>0`) followed by extracted minutiae (no `No minutiae found` on held frames).
- [ ] `fprintd-verify` matches the enrolled finger, twice in a row, no daemon restart.

## Rollback criteria

- Any `timed out`, `unknown-error`, or session-teardown loop during the above
  → revert this ticket's commit and report the exact journal lines. Do not
  pile further tweaks on a failing shape.

## FDT semantics, definitively mapped 09-04 (raw-USB 4-run matrix, no touch ambiguity)

- DOWN without prior MODE: ACK instantly, no reply in 20s, held or not.
- MODE pair + DOWN, untouched: ACK + 28B status reply
  (`a0 18 00 b8 32 15 00 02 00 ff …`) in 0.01s.
- MODE pair + DOWN, held: byte-identical instant reply.
Conclusion: `0x32` is a mode-switch status reply, never touch-gated on
APP_10036. Do not revisit blocking-FDT on this firmware without a Windows
USB traffic capture showing otherwise.

(Experiment D record: D1 fire-and-forget DOWN + D2 QUERY-skip both deployed;
zeros persisted. Per-poll path now matches the script loop modulo TLS impl.
Pre-capture ritual closed as a lead.)

`set_drv_state` skipped, activation/polling healthy, frames still zero under
hold. drv_state neither blanks nor enables content. (Side note: enroll client
going fully silent with no retries is the designed poll-until-content
behavior, not a regression — retries only return when content frames reach
minutiae stage.)

## Experiment C (next): upload CONFIG_WBDI instead of CONFIG_52XD

Experiment A result: per-poll 00-arm sends cleanly (zero journal errors —
no arm-replies exist to clog the queue), captures flow, but frames stay
all-zero under held finger. FDT-arming does not enable content. Eliminated
with it: stale-arm-reply as the always-fire mechanism (no clogging observed).

Remaining structural diffs vs the one proven script frame
(`experiments/test_press_and_minutiae.py`, which used CONFIG_WBDI, no
drv_state, no reg-write, 01-payload): (1) driver sends `set_drv_state`
(absent in proven path); (2) driver uploads CONFIG_52XD instead of
CONFIG_WBDI. Test ONE variable at a time, this order:

- B: skip `set_drv_state` in activation (keep the callback chain flowing to
  `enable_chip`, same bypass pattern as the reg-write). Rebuild, two-phase
  verify. Nonzero on hold = confirmed → remove permanently.
- C (only if B fails): upload CONFIG_WBDI bytes in place of CONFIG_52XD and
  re-test. Do not combine B and C in one build.

(Experiment A record: per-poll 00-arm hypothesis falsified 09-03 — arms send
cleanly with zero journal errors yet frames stay zero under hold. Payload
question stays parked: both payloads return identical framing.)

## Critical implementation context & edge cases (Must-Know)

1. **Register 0x022c Factual Correction**:
   - Background point 5 states the proven script wrote no register. Note that `experiments/test_press_and_capture.py` (line 50) *did* execute `device.write_sensor_register(0x022c, b"\x05\x03")`. While empty air reads 0 either way, this analog gain/exposure register was active during the successful finger capture. If frames under finger remain too dark, restore this write in `on_chip_enabled`.

2. **Finger-Release Cycle for Multi-Stage Enrollment (`FP_SCAN_TYPE_PRESS`)**:
   - `libfprint` requires `fpi_image_device_report_finger_status(img_dev, FALSE)` to transition between enrollment stages (stages 1 through 8).
   - With FDT UP skipped, the driver must report finger release when the finger is lifted.
   - Flow: (a) Poll frames until `active >= 64` → report `finger_status = TRUE` → pass image to `fpi_image_device_image_captured()`; (b) Poll frames until `active < 64` (finger lifted) → report `finger_status = FALSE` → advance SSM to complete stage.

3. **Subclass Isolation in Shared `goodix5xx.c`**:
   - `goodix5xx.c` is the shared base class for 511, 52xd, and 5e0a. Ensure the FDT bypass is gated (e.g. via `cls->has_fdt` flag or `cls->process_raw_frame != NULL`) so non-5e0a devices sharing the base driver are unaffected.

4. **GLib Event Loop / Polling Re-arm**:
   - In `goodix5xx.c`, do NOT block the GLib main loop with `g_usleep()`. On empty frame (`active < 64`), use an async timeout (`g_timeout_add_once` or `fpi_ssm_next_state_delayed`) to re-trigger `goodix_tls_read_image` without blocking D-Bus.
