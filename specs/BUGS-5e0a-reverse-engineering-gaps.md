# Spec: Goodix 27c6:5e0a — Confirmed Reverse-Engineering Gaps & Bugs (Research Only, No Fix)

> Source handoff: `/tmp/handoff.md` (Loops 1–3, Log Findings 1–2).
> Method: read-only comparison of C driver (`libfprint-driver/`) against primary
> Python reference (`/tmp/goodix-fp-dump/goodix.py`, `tool.py`, `driver_52xd.py`)
> and local prototypes (`test_touch_sensor.py`, `test_capture_clear.py`,
> `test_init_sensor.py`, `test_press_and_capture.py`, `scan_finger.py`).
> No code was changed for this spec. No bandaids proposed — only what is SURE
> with a primary-source citation per claim.

## Problem Statement

`fprintd-enroll` either hangs forever at `Enrolling right-index-finger finger.`
(Loop 1), or completes all stages on empty air saving noise (Loop 2), and
`fprintd-verify` then returns `verify-unknown-error`, hangs needing `^C`, or
matches exactly once after a daemon restart then fails (Loop 3). Logs show
`Command timed out: 0xa2` on activation and `Failed to detect minutiae:
No minutiae found` during enroll. The current C driver claims Milestones
M1–M5 DONE (`PROJECT.md`), but the 52xD init/scan sequence from
`driver_52xd.py:run_driver` was never ported, and the transport layer has
single-flight and NOP races that stall the SSM with no timeout.

## Solution

Do NOT fix yet. Complete reverse engineering first, in this order, then
re-spec the driver from the 52xD trace:

1. Capture Windows USB traffic for 27c6:5e0a (Wireshark + `wireshark/goodix_message.lua`)
   for: init, FDT DOWN/UP/MODE, 0x20 image, 0xc4, 0xd2/0xd4, 0xac, 0x022c.
2. Reconcile command numbers (0xd2 vs 0xd4) and missing commands (0xc4, 0xd2 POV,
   0xac, 0x60/0x92) against firmware `GFUSB_GM168SEC_APP_10036`.
3. Re-derive the true per-scan FDT arming sequence and image payload before
   touching `goodix5xx.c` / `goodix5e0a.c` / `goodix.c`.

Out of scope for this spec: any C edit, any threshold tweak, any retry/timeout
bandaid.

## User Stories

1. As an enrolled user, I want `fprintd-enroll` to advance only on real touch,
   so that empty air never creates a template.
2. As an enrolled user, I want `fprintd-verify` to match my finger every time,
   so that I am not forced to restart fprintd.
3. As an enrolled user, I want back-to-back verify to never time out on 0xa2,
   so that PAM/sudo/hyprlock are reliable.
4. As a driver maintainer, I want the 52xD init sequence (drv_state, POV,
   calibration captures) documented from a trace, so that activation matches hardware.
5. As a driver maintainer, I want FDT DOWN/UP/MODE payloads captured from Windows,
   so that touch-wait blocks instead of hanging or instant-triggering.
6. As a driver maintainer, I want the image-request payload and 12-bit unpack
   validated against a Windows ground-truth PGM, so that minutiae extraction gets
   real ridges instead of stretched noise.

## Implementation Decisions

Decisions here are research findings (SURE bugs/gaps), not fix instructions.
Each cites the exact primary source. File paths below are evidence locations,
not change directives.

### B1 (SURE): `TLS_SUCCESSFULLY_ESTABLISHED` uses wrong command number 0xd2, should be 0xd4; 0xd2 is `MCU_GET_POV_IMAGE` on this family

- C defines (`libfprint-driver/goodix_proto.h:50`):
  `GOODIX_CMD_TLS_SUCCESSFULLY_ESTABLISHED (0xd2)`.
- The patch itself flipped it (`0001-...patch`, `goodix_proto.h` hunk):
  `-#define ... (0xd4)` → `+#define ... (0xd2)`.
- Python reference (`/tmp/goodix-fp-dump/goodix.py:32-35`):
  `COMMAND_SET_DRV_STATE = 0xc4`,
  `COMMAND_MCU_GET_POV_IMAGE = 0xd2`,
  `COMMAND_TLS_SUCCESSFULLY_ESTABLISHED = 0xd4`.
- C sends handshake-done via `goodix.c:1089,1095`
  (`goodix_send_tls_successfully_established`), i.e. it sends 0xd2 where the
  MCU expects 0xd4, and 0xd2 where it expects a POV-image request
  (`goodix.py:641-662`).
- Maps to: Loop 3 unknown-error / first-verify-only-matches (TLS session never
  cleanly established, subsequent activations desync).

### B2 (SURE): `SET_DRV_STATE` (0xc4) never sent; claimed in docs but absent in code

- All Python init paths call it: `driver_52xd.py:154`, `test_touch_sensor.py:66`,
  `test_capture_clear.py:62`, `test_init_sensor.py:67`, `goodix.py:611-622`
  (`set_drv_state`: payload `01 00`, command 0xc4, ACK-checked).
- C search returns zero hits: `rg 0xc4|SET_DRV|set_drv libfprint-driver/` finds
  only `0xc4` bytes inside the 511 config blob, no command, no function.
- `PROJECT.md:12` Feature 9 claims "Enable … via CMD 0x96 and set driver state
  via CMD 0xc4" — the second half is unimplemented.
- Maps to: Loop 1 hang (MCU never leaves post-config state, FDT never arms).

### B3 (SURE): POV handshake (`mcu_get_pov_image` 0xd2, `set_pov_config` 0xac) entirely missing

- Required order in `driver_52xd.py:151-167`: `upload_config_mcu` →
  `set_drv_state()` → `mcu_get_pov_image()` → FDT_MODE pair → reg 0x022c writes
  → calibration captures → `set_pov_config(DEVICE_POV_CONFIG)` (line 243) →
  sleep/query → FDT_DOWN arming.
- `test_capture_clear.py:61-77` and `test_init_sensor.py:61-77` prove the device
  accepts this order on 5e0a hardware.
- C activation (`libfprint-driver/goodix5e0a.c:120-134`): TLS → upload config →
  enable chip → write 0x022c → activate-complete. No POV call, no 0xac command
  defined in `goodix_proto.h`.
- Maps to: Loop 2 air-enroll + `No minutiae found` (sensor never put in POV/FDT
  capture mode the 52xD flow requires).

### B4 (SURE): Image-request payload hardcoded to calibration value, not finger-capture value

- C (`libfprint-driver/goodix.c:650`, patch hunk): `payload_5e0a = 01 00 00 …`
  (10 bytes) for every `mcu_get_image`.
- 52xD truth (`driver_52xd.py`): clear/calibration frames use
  `01 03 27 01 21…` (line 172), `81 03 27…` (185), `81 03 18…` (198);
  the real finger frame after FDT uses `45 03 a7 00 a1 00 a7 00 a3 00`
  (lines 299-302). `test_press_and_capture.py:52-54` captures with the `45 03…`
  variant; `scan_finger.py:102-104` uses `01 00…` only for the no-touch demo path.
- The trailing `a7 00 a1 00 a7 00 a3 00` bytes are the same exposure block
  embedded in the FDT_DOWN payloads — C ignores them for 0x20.
- Maps to: Loop 2 (noise template) + minutiae failure (wrong exposure/gain frame).

### B5 (SURE): Per-scan FDT arming sequence reduced to a single DOWN; required 00-arm + sleep/query + 01-wait omitted

- 52xD truth (`driver_52xd.py:249-283`): `FDT_DOWN(…00…) reply=False` →
  `FDT_DOWN(…01…) reply=False` → `sleep` → `query_mcu_state(00)` →
  `query_mcu_state(01)` → `FDT_DOWN(…00…) reply=False` → `FDT_DOWN(…01…) reply=True`
  (blocking wait). `test_touch_sensor.py:70-87` shows the same two-step:
  `FDT_DOWN_0` no-reply then `FDT_DOWN_1` blocking with `timeout=None`
  (`goodix.py:217-235` reads with `timeout=None` = infinite).
- C scan (`libfprint-driver/goodix5xx.c:405-418`): single
  `goodix_send_mcu_switch_to_fdt_down(…01…, timeout=0, reply=TRUE)` per scan.
  No 00-arm, no sleep/query (`SCAN_STAGE_QUERY_MCU` is a single
  `goodix_send_query_mcu_state` with `reply=FALSE`, `goodix.c:1022-1044`, which
  never waits).
- C FDT DOWN/UP both use `timeout=0` = no timeout (`goodix.c:703-704,737-738`),
  matching Python's infinite block — but without arming, the block either never
  fires (Loop 1 hang) or returns immediately on stale data (Loop 2 air trigger).

### B6 (SURE): `FDT_UP` (0x34) payload `9c…00…` is invented; 52xD trace never uses 0x34

- `rg fdt_up driver_52xd.py` → zero calls. Post-finger steps are
  `FDT_MODE 0d…8d…00 reply=False` then `FDT_MODE 0d…8d…01 reply=True`
  (`driver_52xd.py:285-295`, 27 bytes), then reg write + 0x20.
- C scan (`goodix5xx.c:425-438`) uses `FDT_UP 9c…00` (`goodix5e0a.h:73-79`) for
  release. No Windows/USB source for that payload exists in-repo; it is DOWN
  with byte 26 flipped (handoff §3). `test_touch_sensor.py` defines only
  `FDT_DOWN_0/1` and `FDT_MODE_0/1`, no UP vector.
- Maps to: Loop 1/Loop 3B (release wait on a command the MCU never expected →
  next activate starts desynced → 0xa2 timeout).

### B7 (SURE): `goodix_send_nop` completes synchronously, racing the next command

- C (`libfprint-driver/goodix.c:619-643`): after `goodix_send_protocol(... reply=FALSE ...)`,
  it immediately calls `goodix_receive_done(dev,NULL,0,NULL)` → `goodix_reset_state`
  → user callback → `fpi_ssm_next_state`. The device ACK arrives later via the
  read loop when `priv->cmd` is already the *next* command.
- Every other `reply=FALSE` sender (`enable_chip`, `fdt_mode`, `query_mcu_state`)
  waits async for the ACK (`goodix_receive_none`). Python `goodix.py:179-200`
  (`nop()`) writes then reads with 0.1 s timeout and checks the ACK.
- Consequence: NOP's ACK is later classified `Invalid ACK command` / `Invalid
  protocol command` (`goodix.c:300-356`) and dropped, while the overlapped RESET
  (0xa2) loses its ACK/reply → Log Finding 1 `Command timed out: 0xa2`.

### B8 (SURE): Single-flight guard drops commands silently → SSM hangs with no timeout on FDT paths

- Guard (`goodix.c:586-593`): `if (priv->ack||priv->reply||priv->timeout)
  { warn("A command is already running"); return; }` — no callback, no
  `fpi_ssm_mark_failed`, no timeout installed. The SSM step never advances.
- FDT DOWN/UP install `timeout_ms=0` = no timeout, so a single collision hangs
  enroll/verify forever (Loop 1 `Enrolling…` hang; Loop 3B `^C` hang).
- Trigger sources already in tree: B7 NOP race, stale TLS records
  (`goodix.c:400-413` discards unless `cmd==0x20||0xd0`), and `dev_deactivate`
  tearing down TLS while the MCU is still blocked in FDT_UP.

### B9 (SURE): `process_raw_frame` always full-range stretches, so air noise becomes a template; no finger-present gate

- C (`libfprint-driver/goodix5e0a.c:204-266`): collects 19 columns at `4k+3`,
  ignores `v<=30`, then `norm=(val-min)*255/range` over the whole 160×128 output.
  Any noise frame is amplified to full contrast.
- `bz3_threshold=12` (`goodix5e0a.c:305`) vs 511's 24 (`goodix511.c:328`) with no
  trace justification lowers the minutiae bar further.
- Matches Loop 2 symptom 1 (8 stages complete on air) and Log Finding 2
  (`No minutiae found` when stretch produces ridge-less flats, or false minutiae
  when it amplifies noise). `test_real_capture.py:71-76` already shows how to
  distinguish (per-column non-zero counts) — that gate was never ported.
- The 19-column `4k+3` geometry itself is unproven: no Windows PGM comparison
  (`windows_unpacked.pgm`, `dense_19x64.pgm`, `clear-0.pgm` never diffed in-tree).

## Testing Decisions

- No new unit/e2e tests in this spec — the existing Tier 1–5 suite
  (`tests/run_all_tests.sh`) asserts idealized payloads (e.g. `test_f11_fdt_down`,
  `test_f12_fdt_up`, `test_f16_demosaicing`) without a hardware/Windows trace
  oracle, which is why it passes while hardware loops. Do not extend it until
  B1–B6 are re-derived from captures.
- Correct seams when re-testing (for the future fix spec, not this one):
  `goodix_send_protocol` single-flight, `goodix_receive_pack` TLS dispatch,
  `goodixtls5xx_decode_frame`, `process_raw_frame` — all need USB-trace replay
  harnesses, not synthetic assertions.
- Prior art to reuse as oracles: `driver_52xd.py:run_driver` (full init→scan),
  `tool.decode_image` (`tool.py:36-46`), `test_touch_sensor.py:68-87` (blocking
  semantics), Windows `WBDI.log` / `wireshark/` dissectors.

## Out of Scope

- Any edit to `libfprint-driver/*.c|*.h`, the NixOS patch, or test tiers.
- Timeout/retry increases, threshold tweaks (`bz3_threshold`, `v>30`), or
  reinstall/restart workarounds for 0xa2.
- PSK rotation, firmware flashing (`driver_52xd.py:update_firmware`), or
  whitebox/DPAPI handling (`psk.bin`, `dpapi_*.bin`).

## Further Notes

- Higher-priority unknowns needing captures before any fix: true 0xd2 vs 0xd4
  behavior on FW `GFUSB_GM168SEC_APP_10036`; real 0x34 payload if any; POV config
  bytes for this unit (`DEVICE_POV_CONFIG` in `driver_52xd.py:38-41` is for
  `APP_10019`, not necessarily `APP_10036`); 0x022c `05 03` vs `0a 03`/`0a 02`
  schedule; 80×64 vs 19×64 sensor geometry vs `windows_unpacked.pgm`.
- `goodix_send_mcu_switch_to_fdt_mode` frees `mode` before sending it
  (`goodix.c:756-770`); harmless today (`free_fn=NULL` for static tables) but
  must be fixed when dynamic configs return.
- `goodixtls5xx_decode_frame` header heuristic (`goodix5xx.c:467-487`) disagrees
  with `tool.decode_image` (no header skip); validate against the same 7684-byte
  frame before trusting either.
- Keep this file as the gate: no driver PR should land until each B-item is
  either confirmed by a cited USB trace or struck with trace evidence.
