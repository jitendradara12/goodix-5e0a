# 15 — Canonical ChicagoH Frame Restructuring & Full-Resolution Biometric Verification

**What to build:** Implement the exact Windows `wbdi.dll` frame restructuring pipeline (`0x18004db80` + `0x18004ea50`). Extract the true 96-byte active column data from each of the 80 132-byte column blocks, eliminating the 36-byte padding bands and restoring the full 100% active sensor area (all 80 columns, 5120 pixels). This resolves minutiae starvation and achieves Bozorth3 match scores $\ge 12$ (`verify-match (done)`).

**Blocked by:** None — builds on Ticket 14 (falsified raw column-major and raw linear truncation; established biometric correlation with scores 3–6/12).

**Status:** superseded (successor: [16-minutiae-stabilization-and-verification.md](16-minutiae-stabilization-and-verification.md))

## Hardware Run 11 & 12 (Deployed Driver — Stride-132 Column-Major Falsified)
- **Journal Evidence (2026-09-05 00:35:56):**
  ```text
  Sep 05 00:35:56 sastapc fprintd[158854]: 5e0a row-major frame: active_px=5120 nonzero=5120 min=272 max=2548 geometry=80x64 (WxH)
  Sep 05 00:35:56 sastapc fprintd[158854]: 5e0a frame stats: active=5120, min_v=272, max_v=2548, range=2276, declen=10564, adj_corr=-0.348, all_corr=0.153, dist_corr=-0.102 (native 80x64 WxH)
  Sep 05 00:35:56 sastapc fprintd[158854]: 5e0a get_minutiae: ret=0 minutiae_count=1 (image 160x128 WxH, scan_time=0.0042s)
  Sep 05 00:35:56 sastapc fprintd[158854]: 5e0a bz3 match: gallery[0]_nrows=1 score=0/12 (probe_nrows=1)
  ```
- **Verdict:** FALSIFIED. Inserting 132-byte column strides scrambled horizontal raster scanlines into vertical strips, inverting correlation to -0.348 and starving minutiae to 1. Wire data is contiguous 12-bit words, not stride-132. All 80 columns are active in linear decode. Reverted.


## Settled facts this ticket builds on (do not re-litigate)

- **Chip provisioning & FDT:** Proven and frozen. 100% silent in empty air; wakes up instantly on physical touch.
- **Framing & Decryption:** Proven and frozen. Sensor delivers canonical ChicagoH frames of 10564 bytes (`declen=10564`).
- **Enrollment Flow:** Proven and frozen. Completes all 8 stages without deadlock (`enroll-completed`) and persists template to `/var/lib/fprint/sastauser/goodixtls5e0a/0/7`.
- **Biometric Correlation:** Proven. Bozorth3 achieves non-zero scores (3/12, 4/12, 5/12, 6/12) on physical touches, proving that sensor orientation and NBIS processing are biometrically real.

## Root Cause Discovery: Windows Driver `wbdi.dll` Disassembly

Disassembly of `windows_driver/wbdi.dll` at `0x18004db80` reveals the exact algorithm Goodix uses to decode 10564-byte frames:

```asm
0x18004db80:
   18004db93: mov    DWORD PTR [rsp+0x24], 0x1e00   ; 0x1e00 = 7680 bytes
   18004dba1: call   malloc                         ; malloc(7680)
   18004dbab: mov    DWORD PTR [rsp+0x20], 0        ; col = 0
   ; Loop: 80 columns (0x50 = 80)
   18004dbbf: cmp    DWORD PTR [rsp+0x20], 0x50     ; cmp col, 80
   18004dbc4: jae    0x18004dbfd
   18004dbc6: imul   eax, DWORD PTR [rsp+0x20], 0x84 ; eax = col * 132 (0x84 = 132!)
   18004dbd5: add    rcx, rax                       ; src = raw_10564 + col * 132
   18004dbdb: imul   ecx, DWORD PTR [rsp+0x20], 0x60 ; ecx = col * 96  (0x60 = 96!)
   18004dbe7: add    rdx, rcx                       ; dst = temp_7680 + col * 96
   18004dbed: mov    r8d, 0x60                      ; count = 96 bytes
   18004dbf6: call   memcpy                         ; memcpy(dst, src, 96)
   18004dbfb: jmp    loop

0x18004dbfd:
   18004dc08: mov    rcx, temp_7680
   18004dc0d: call   0x18004ea50                   ; unpack_column_major(temp_7680, out, 7680)
   18004dc17: call   free                           ; free(temp_7680)
   18004dc20: ret
```

### The Mathematical Truth of the 10564-Byte Frame
1. **Frame Geometry:**
   $$\text{Total Frame} = 80 \text{ columns} \times 132 \text{ bytes/column} + 4 \text{ bytes footer} = 10,564 \text{ bytes}$$
2. **Column Structure:**
   - Each column block is **132 bytes**.
   - Active pixel data: $64 \text{ pixels} \times 1.5 \text{ bytes/pixel} = \mathbf{96\text{ bytes}}$.
   - Padding/metadata: $132 - 96 = \mathbf{36\text{ bytes}}$ of trailing sensor dummy bytes per column.
3. **Why Previous Runs Starved Minutiae:**
   - **Hardware Run 3 (Linear 7680B Decode):** Reading the first 7,680 bytes of the 10564-byte stream read only the first 58 columns ($7680 / 132 \approx 58.18$), truncating the last 22 columns (27.5% of the sensor!). Furthermore, every 96 bytes was corrupted by a 36-byte padding band. That is why `active` was always ~3728 ($58 \times 64 = 3712$).
   - **Hardware Run 4 (Stride-165):** Falsely assumed 165-byte horizontal row stride instead of 132-byte vertical column stride.
   - **Hardware Run 5 (Raw Column-Major):** Unpacked column-major directly on raw 7680 bytes without stripping the 36-byte padding bands, scrambling the pixels.

## Implementation: True Windows Pipeline

```c
static void
goodix5e0a_decode_frame (GoodixTls5xxPix *out_row_major, const guint8 *data, guint16 len)
{
  if (!data || len < GOODIX_5E0A_ACT_BYTES)
    return;

  /* Step 1: Extract 96 active bytes from each of the 80 columns of 132 bytes (wbdi.dll:0x18004db80) */
  guint8 packed_7680[GOODIX_5E0A_WIDTH * 96]; // 80 * 96 = 7680 bytes
  for (guint col = 0; col < GOODIX_5E0A_WIDTH; col++)
    {
      guint32 src_offset = col * 132;
      if (src_offset + 96 <= len)
        memcpy (packed_7680 + col * 96, data + src_offset, 96);
      else
        memset (packed_7680 + col * 96, 0, 96);
    }

  /* Step 2: Unpack 80 columns x 64 rows column-major into row-major 80x64 (wbdi.dll:0x18004ea50) */
  guint32 pixel_idx = 0;
  for (guint32 i = 0; i + 6 <= sizeof (packed_7680) && pixel_idx < GOODIX_5E0A_FRAME_SIZE; i += 6)
    {
      const guint8 *c = packed_7680 + i;
      GoodixTls5xxPix pix[4];
      pix[0] = ((c[0] & 0x0f) << 8) | c[1];
      pix[1] = (c[3] << 4) | (c[0] >> 4);
      pix[2] = ((c[5] & 0x0f) << 8) | c[2];
      pix[3] = (c[4] << 4) | (c[5] >> 4);

      for (int p = 0; p < 4 && pixel_idx < GOODIX_5E0A_FRAME_SIZE; p++)
        {
          int row = pixel_idx % GOODIX_5E0A_HEIGHT; // % 64
          int col = pixel_idx / GOODIX_5E0A_HEIGHT; // / 64
          out_row_major[row * GOODIX_5E0A_WIDTH + col] = pix[p];
          pixel_idx++;
        }
    }
}
```

### Normalization Restoration in `process_raw_frame`
Ensure full dynamic range contrast normalization:
```c
int norm = (int) (((val - (float) min_v) * 255.0f) / (float) range);
norm_80x64[r * W + c] = (guint8) CLAMP (norm, 0, 255);
```
Zero-baseline normalization (`val / max_v`) maps capacitive valleys (~800–1200 ADC) to mid-gray (~80–120) which invert to dark gray (~135–175) instead of white (255), collapsing NBIS `mindtct` gradient detection and starving minutiae. Min-max normalization guarantees full [0, 255] gamut.

## Acceptance Criteria (Deployed Driver, Hardware Only)

- [ ] All 80 columns active in journal log (`active_cols: 0 1 2 ... 79`).
- [ ] Active pixel count on firm touch reflects full sensor area ($\ge 4500$ pixels instead of truncated ~3728).
- [ ] Enrollment completes 8/8 stages cleanly with $\ge 25$ minutiae per stage.
- [ ] Probe frame extracts $\ge 25$ minutiae without tripping floor abort.
- [ ] `fprintd-verify` achieves score $\ge 12$ against enrolled gallery.
- [ ] Successful `Verify result: verify-match (done)`.
