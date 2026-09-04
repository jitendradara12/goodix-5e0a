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

## Hardware Run 1 (2026-09-04 18:57–19:01, Deployed Driver)

### Journal Evidence
- **Phase 1 (18:57:45 – 18:59:02, 77s hands off):** MCU entered state 2 (FDT DOWN) and remained in a blocking hardware interrupt wait for 77 seconds. Zero spurious packets, zero retry loops, completely silent!
- **Phase 2 (18:59:02 – 18:59:35, physical touch):** MCU immediately fired hardware interrupt on touch and returned `len=16` packets:
  `5e0a D32 reply: status=0x02 len=16 bytes=[02 00 3f 00 86 00 cf 00 bd 00 de 00 88 00 ae 00 ]`
  - Active channel mask: `0x3f` (channels 0–5) and `0x3e`/`0x1f`.
  - Channel energy: 1062 to 1514 (non-zero 16-bit LE words across 6 channels).
- **Release (18:59:35 – 19:01:00, 85s hands off):** Sensor went completely silent again for 85 seconds until next touch.
- **Flaw identified:** Driver checked `if (len >= 20 && ...)` which evaluated to false on 16-byte replies. Gating logic corrected to `len >= 4` and dynamic channel sum across `(i + 1 < len)`.
- **Verdict on hardware run 1:** Inconclusive-because-len-check (hardware FDT down interrupt confirmed, touch detection confirmed, gating len bug patched).

## Hardware Run 2 (2026-09-04 19:18–19:20, Deployed Driver)

### Journal Evidence
- **Full-size frame received:** `declen=10564` (canonical ChicagoH sample size `0x2944` verified in `wbdi.dll:GetImageSampleSize`). Degraded 7684-byte frames are gone!
- **Active pixels:** `nonzero=5120` (all 80x64 sensor pixels active!). Pixel values range from 415 to 2948.
- **Active columns:** All 80 columns (0 to 79) active!
- **Correlation:** `adj_corr=0.460 - 0.506` (adjacent column correlation confirms ridge structures).
- **Minutiae detection & stage pass:** Touch 3 passed minutiae extraction!
  `fprintd-enroll: Enroll result: enroll-stage-passed`!
- **Flaw identified:** In `goodix5e0a_on_fdt_up_reply`, `fpi_image_device_report_finger_status(dev, FALSE)` was called before `fpi_ssm_next_state(ssm)`. Libfprint synchronously requested `AWAIT_FINGER_ON`, but the concurrency guard saw the old SSM still active and dropped the new scan request. Patched by clearing `self->scan_ssm = NULL` and completing the SSM before reporting finger off.

## Hardware Run 3 (2026-09-04 19:44–19:46, Deployed Driver)

### Journal Evidence
- **Multi-stage progress confirmed:** 14 touches processed without a single deadlock or crash!
- **5 stages passed in rapid succession:**
  - `Device reported enroll progress, reported 1 of 8 have been completed` (19:45:04)
  - `Device reported enroll progress, reported 2 of 8 have been completed` (19:45:09)
  - `Device reported enroll progress, reported 3 of 8 have been completed` (19:45:14)
  - `Device reported enroll progress, reported 4 of 8 have been completed` (19:45:19)
  - `Device reported enroll progress, reported 5 of 8 have been completed` (19:45:24)
- **Minutiae detection bottleneck identified:** `process_raw_frame` was using a legacy 19-column downsampling and horizontal interpolation from ticket 12 (when frames were degraded). Now that all 80 columns have real pixels (`nonzero=5120`), this downsampling was throwing away 75% of horizontal resolution and causing minutiae detection failures when finger angle changed.
- **Resolution applied:** Mapped all 80 native sensor columns directly into `img->data` at 500 DPI native optical clarity without downsampling or horizontal blur.

## Hardware Run 4 (2026-09-04 20:02–20:03, Deployed Driver)

### Journal Evidence
- **All 8 of 8 enroll stages completed on physical hardware:**
  `Device reported enroll progress, reported 8 of 8 have been completed`!
- **Teardown collision identified:** When stage 8 completed, libfprint called `deactivate` while the scan SSM's finger-release sequence was still in-flight. `goodix5e0a_deactivate` attempted to send an asynchronous sleep command (`0x60`), triggering `A command is already running: 0xae`, which caused `fpi_image_device_deactivate_complete` to never be called.
- **Resolution applied:** Streamlined `goodix5e0a_deactivate` to match standard `goodix5xx` behavior: immediately cancels all timeouts, resets driver USB state via `goodix_reset_state`, shuts down TLS, stops read loop, and calls `fpi_image_device_deactivate_complete` synchronously.
- **Verdict on hardware run 4:** All 8 enrollment stages proven. Teardown fix deployed to complete session exit and persist template.

## Hardware Run 5 (2026-09-04 20:19–20:20, Deployed Driver)

### Journal Evidence
- **Enrollment completed successfully:** All 8 stages passed and template was committed to `/var/lib/fprint/sastauser/goodixtls5e0a/0/7`.
- **Verify symptom:** First press returned `Verify result: verify-retry-scan (not done)`, followed by timeout `Verify result: verify-no-match (done)`.
- **Journal diagnosis:**
  `Sep 04 20:20:03 sastapc fprintd[61090]: Failed to detect minutiae: No minutiae found`
  `Sep 04 20:20:03 sastapc fprintd[61090]: verify_cb: result verify-retry-scan`
  Bozorth3 matcher was never reached! Probe frame extracted 0 minutiae.
- **Root causes identified:**
  1. **Missing `FPI_IMAGE_COLORS_INVERTED`:** Capacitive sensor ADC produces higher counts on finger contact (ridges = high ADC ~2800, valleys = low ADC ~600). Without `FPI_IMAGE_COLORS_INVERTED`, normalized image has white ridges on black valleys. NBIS `mindtct` (`detect.c`) explicitly expects 0 = black pixel (ridge) and 255 = white pixel (valley). Looking for ridges in inverted valleys caused minutiae detection to frequently fail.
  2. **Sub-500 DPI physical sensor area:** Sensor native size is 80x64. With `FPI_IMAGE_PARTIAL`, NBIS trims `PERIMETER_PTS_DISTANCE = 10` pixels from all borders, leaving only 60x44 pixels. Against a 24x24 analysis window (`MAP_WINDOWSIZE_V2 = 24`), an unscaled print has barely 4-5 ridges and easily produces 0 minutiae.
  3. **Bozorth3 metric scaling:** Bozorth3 distance metric `DM = 125` assumes 500 DPI pixel coordinates. At native 80x64, inter-minutiae distances are compressed by 2x.
- **Resolution applied:**
  - Added `FPI_IMAGE_COLORS_INVERTED` flag to `img->flags` so libfprint normalizes ridges to black (0) and valleys to white (255).
  - Applied 2x bilinear upsampling via `fpi_image_resize (img, 2, 2)` (matching `elanspi`, `aes3k`, `egis0570`, and `vfs7552`), producing 160x128 images at standard 500 DPI ridge frequency.
  - Enforced empty air rejection gate: `if (active < 64 || range < 8) return NULL;` fallback to 160x128 zero-filled image.
  - Full rebuild and patch refresh completed. Requires re-enrollment to populate 160x128 gallery templates.

## Acceptance criteria (deployed driver, hardware only)

- [x] Phase 1 (60s hands off): silent, zero retry spam, MCU stays in hardware interrupt wait.
- [x] Phase 2 (60s press-and-hold): touch triggers instantly on channel energy, advances to GET_IMAGE.
- [x] Replies grow toward pack10638 / 10564 (`declen=10564` logged in journal).
- [x] Content frames show non-zero pixels and minutiae count > 0; enroll advances (`enroll-stage-passed`).
- [x] Complete full 8-stage `fprintd-enroll` (all 8/8 stages passed).
- [ ] Successful completion exit and `fprintd-verify` double match.

## Rollback criteria

- Any timeout, crash, or session lockup $\rightarrow$ revert to pre-13 commit, paste journal.


