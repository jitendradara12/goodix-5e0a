# 13 — Chip provisioning for full-size frames + channel-byte gating

**What to build:** (a) Download the true ChicagoH (GF3658 DN3 / APP_10036) config
blob at activation so image replies grow from degraded 7684B to Windows-grade
10638B; (b) gate touch on D32 channel bytes (not byte0) with paced silent polling;
(c) sequence the UP pair without overlap and guard against concurrent scan SSMs.
Full enroll + double verify off the back of it.

**Blocked by:** None — ready now. (Ticket 12 closed-falsified, history kept.)

**Status:** in-progress

## Settled facts this ticket builds on (do not re-litigate)

- D32 in empty air returns `02` with byte2=`ff` and channel bytes 4–19 all
  zero (`02 00 ff 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`).
  Touch replies (pcap pkt 33) carry byte2 masks (`0f/1f/3f`-family) with
  non-zero 16-bit channel values (e.g. `0x00e3`, `0x013e`, `0x00e8`, `0x011d`, ...).
  **Gating rule: touch = channel-byte energy (data[2] != 0xff && channel_energy > 0),
  never byte0.** The binary 02/80 model is dead.
- The Ticket 12 "UP-pair collision" (`A command is already running: 0x34`) was a
  concurrency race caused directly by the false-touch trigger in empty air:
  empty air triggered GET_IMAGE $\rightarrow$ 7684B zero frame passed to minutiae
  detector $\rightarrow$ 0 minutiae $\rightarrow$ fprintd retry scan requested
  `AWAIT_FINGER_ON` $\rightarrow$ second scan SSM launched while first scan SSM
  was still waiting 5000ms for finger release on `UP_2`. Gating on channel energy
  cuts this chain at the root; an SSM concurrency guard prevents any re-entry.
- 05-payload framing is correct (full pack/proto/TLS parse, declen full).
  Zeros are content/session-state, never framing or payload.
- Reg `0x022c` (all values incl. skip), drv_state (in/out), both old
  configs-as-tried, FDT arming rituals, reset phasing, settle-via-polling:
  all falsified as content causes. Do not retry any of them.

## Blob provenance & analysis (drivers/wbdi.dll reverse-engineering)

Reversing `drivers/wbdi.dll` (v3.0.141.230 for 27c6:5e0a / 5e02) identified 6
config tables in `.rdata` / `.data`:
1. `0x197c50` (VMA `0x180198a50`, byte 0 = `0xb0`): ChicagoH (`chicagoh.c`, `GF3658 DN3`, 80x64)
2. `0x197fd0` (VMA `0x180198dd0`, byte 0 = `0xa0`): ChicagoHS (`chicagohs.c`)
3. `0x198140` (VMA `0x180198f40`, byte 0 = `0x90`): ChicagoT (`chicagot.c`)
4. `0x247960` (VMA `0x180248b60`, byte 0 = `0x30`): MilanG (`milang.c`)
5. `0x247e10` (VMA `0x180249010`, byte 0 = `0x58`): MilanH (`milanh.c`)
6. `0x248a00` (VMA `0x180249c00`, byte 0 = `0x70`): MilanHuHV (`milanhuhv.c` / GF5298)

**Critical findings:**
- `CONFIG_WBDI` previously tried in the driver and experiments was mistakenly
  extracted from table 6 (`0x248a00` / MilanHuHV GF5298).
- `CONFIG_52XD` was taken from an older 52xD Python script (`0x70 0x11 0x60 0x71...`).
- The **TRUE** sensor table for 5E0A (`GFUSB_GM168SEC_APP_10036` on ChicagoH / GF3658 DN3)
  is table 1 at file offset `0x197c50` (VMA `0x180198a50`), byte 0 = `0xb0`!
- **Byte-by-byte diff:**
  - Base ChicagoH vs `CONFIG_52XD`: 50 bytes differ (offset 0x00 is `0xb0` vs `0x70`;
    timing/DAC offsets 0x17, 0x1b, 0x1c, 0x1f, 0x20, 0x23, 0x27, 0x28, 0x2b, 0x2c,
    0x2f, 0x30, 0x3c, 0x40, etc. differ).
  - Base ChicagoH vs `CONFIG_WBDI`: 49 bytes differ.
- **Checksum algorithm (`0x180049b20` in wbdi.dll):**
  Seed is `0xa5a5`. Sum 16-bit little-endian words over words 0..0x7e (bytes 0..253).
  Checksum is `(0 - sum) & 0xffff`.
  Stored at `buf[0xfe] = checksum & 0xff` (LE low byte), `buf[0xff] = (checksum >> 8) & 0xff` (LE high byte).
  For the base ChicagoH table, computed checksum is `0x0e53` (`53 0e`).
- **OTP conditioning (`chicagoh.c:GetChipConfig` at `0x1800512c0`):**
  Queries OTP via CMD `0xa6`. If OTP does not supply custom calibration, falls back to
  defaults: `tcode = 0x80`, `diff = 0x15`, `fdt_offset = 0`.
  In the base ChicagoH template, register `0x005c` already carries `0x0080` (default tcode).

**ChicagoH candidate blob (256 bytes, length 0x100):**
- First 16 bytes: `b0 11 60 71 2c 9d 2c c9 1c e5 18 fd 00 fd 00 fd`
- Last 16 bytes:  `00 54 00 00 01 66 00 03 00 7c 00 01 58 00 53 0e`

## Precise changes (5e0a-gated driver files only; transport frozen)

1. **Blob definition (`goodix5e0a.h` & `goodix5e0a.c`):**
   Replace `goodix_5e0a_config` with the extracted ChicagoH 256-byte blob
   (starting `b0 11 60 71...`, checksum `53 0e`).
2. **Download it once per activation:**
   Upload via `GOODIX_CMD_UPLOAD_CONFIG_MCU` (`0x90`) post-TLS during
   `on_tls_activation_complete` before `goodix_send_enable_chip`.
3. **Channel-byte touch gating & paced silent polling:**
   - In `goodix5e0a_on_fdt_down_reply`:
     Compute channel energy from `data[4..19]` (eight 16-bit LE channel readings).
     Touch condition: `len >= 20 && data[2] != 0xff && channel_energy > 0`.
   - If touch is NOT detected (empty air: `data[2] == 0xff` or zero energy):
     Do NOT advance to GET_IMAGE or minutiae detection.
     Re-sample `0x32` DOWN after a 50ms–100ms GLib timer delay (`g_timeout_add`)
     to avoid saturating USB and MCU in a 10ms tight loop.
   - If touch IS detected:
     Report `fpi_image_device_report_finger_status(TRUE)`.
     Advance SSM to `SCAN_5E0A_GET_IMAGE`.
4. **UP sequence & Scan SSM concurrency guard:**
   - Guard `goodix5e0a_change_state (AWAIT_FINGER_ON)`: if `self->scan_ssm != NULL`,
     do not launch a redundant scan SSM.
   - Up-sequence strictly follows ground truth (pkts 41–53):
     `UP_1 (0x34, noreply)` $\rightarrow$ wait ACK $\rightarrow$
     `UP_AE (0xae, noreply)` $\rightarrow$ wait ACK $\rightarrow$
     `UP_2 (0x34, reply, timeout=5000ms)` $\rightarrow$ await finger release reply.
   - On UP_2 release reply or timeout: report `finger_status(FALSE)`, clear
     `self->scan_ssm`, complete stage.
5. **Frame decoder handling for pack10638:**
   In `goodix5e0a_on_read_img`, support both degraded 7684B and full-size 10638B
   replies; log `declen` and frame statistics.
6. Rebuild with Ninja, refresh unified patch, test `nix-build`, commit.

## Acceptance criteria (deployed driver, hardware only)

- [ ] Phase 1 (60s hands off): silent, zero retry spam, D32 samples silently cycle every ~50-100ms.
- [ ] Phase 2 (60s press-and-hold): touch triggers instantly on channel energy.
- [ ] Replies grow toward pack10638 (`declen` logged in journal).
- [ ] Content frames show non-zero pixels and minutiae count > 0; enroll advances.
- [ ] `fprintd-verify` matches twice, no restart. Then 07 runs.

## Rollback criteria

- Any timeout, crash, or session lockup $\rightarrow$ revert to pre-13 commit, paste journal.

