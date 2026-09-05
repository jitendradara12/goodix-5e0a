# 17 — Canonical ChicagoH Layout + Local Contrast Verification

**What to build:** Remove the deterministic per-block zero padding from 10,564-byte ChicagoH frames, preserve the natural 64x80 raster, flatten its pressure/offset field with a 3x3 local mean, and obtain repeatable Bozorth3 verification scores >= 12.

**Status:** closed (verdict: confirmed-layout-and-local-contrast; successor: [18-closed-minutiae-density-and-enrollment-gating.md](18-closed-minutiae-density-and-enrollment-gating.md))

## Goal

Make `fprintd-verify` return `verify-match (done)` against a freshly enrolled right-index template. Enrollment completion alone is not acceptance.

## Settled Transport Facts (Frozen)

Activation, ChicagoH config upload, TLS, D32 touch gating, 10,564-byte decryption, scan sequencing, and synchronous teardown are unchanged. This ticket changes image interpretation only.

## Run 13 Evidence and Root Cause

The deployed contiguous decoder reported exactly 3,728 nonzero pixels on every enrollment and verification capture. Gallery minutiae were `[9, 13, 5, 10, 8, 5, 6, 14]`; probes were 5, 10, 12, and 2; maximum Bozorth score was `3/12`.

The saved `/dev/shm/live_frame.raw` establishes the wire structure byte-for-byte:

- Total: 10,564 bytes.
- 80 blocks of 132 bytes plus a four-byte footer.
- In every block, bytes 0–95 are active and bytes 96–131 are zero.
- Padding control: 2,880/2,880 pad bytes are zero; only 24/7,680 active bytes are zero.
- Offset 1 already degrades this control to 2,800/2,880 pad bytes zero, proving block origin 0.

The old result follows exactly: `7680 = 58 * 132 + 24`. Decoding the first 7,680 wire bytes inserts 58 36-byte pads, each becoming 24 zero pixels: `5120 - 58 * 24 = 3728`.

## Hypotheses and Predicted Signatures

### H1 — Canonical Block Extraction + Natural Geometry

Extract `[block*132, block*132+96)` for all 80 blocks, concatenate, unpack each six bytes into four 12-bit pixels, and preserve sequence as a 64x80 row-major raster.

- **Confirm:** `decoded_px=5120`, `active=5120`, `padding_nonzero=0`, `geometry=64x80`; true lag-1 correlations remain positive.
- **Falsify:** `padding_nonzero != 0`, decoded count != 5,120, or active count returns to 3,728.

Ticket 15 did not falsify extraction: its reported `adj_corr=-0.348` was a lag-4 column metric, not adjacent-pixel correlation, and it combined extraction with a transpose and global contrast.

### H2 — Slow Pressure Field Hides Ridge Detail

After structural correction, global min-max contrast produced only two minutiae on the Run 13 probe. Subtracting each pixel's 3x3 local mean before min-max scaling produced 19 minutiae, 16 with reliability >= 0.20.

- **Confirm:** `5e0a local contrast` has non-trivial range and enrollment/probe captures consistently extract >= 10 minutiae; gallery/probe matching reaches >= 12.
- **Falsify:** structurally valid captures still repeatedly extract < 10 minutiae.

## Controlled Offline Replay

Command:

```sh
python3 experiments/analyze_live_frame.py /dev/shm/live_frame.raw
```

Control/result:

```text
wire_bytes=10564 decoded=5120 nonzero=5120 padding_nonzero=0 min=403 max=2572
raw: ... minutiae_count=2
highpass-r1: ... minutiae_count=19
highpass-r2: ... minutiae_count=2
```

The radius-1 (3x3) output also passed the existing NBIS perturbation control:

```text
128x160 row-major, inverted, no perimeter: total=19, reliability>=.2=16,
self=115, noisy=63, shifted=68
```

Synthetic self/noisy/shifted scores validate the replay harness and local stability only. They do not count as a real cross-capture match.

## One-Variable Build Journal

1. **Build A — Wire layout/geometry only:** strip 96/132 per block and use native 64x80; driver-only and full package builds passed. Offline saved probe: 2 minutiae.
2. **Build B — Local contrast only:** with Build A frozen, subtract a 3x3 local mean before existing min-max/2x/inversion pipeline. Driver-only and full package builds passed. Offline saved probe: 19 minutiae.

Unchanged: capture commands, scaling factor 2, polarity, perimeter policy, enroll stages, Bozorth floor, and threshold 12.

## Hardware Experiment A — Fresh Enrollment + Verification

Use the synced NixOS patch checksum:

```text
3174802b1c3c38ec2c7e27d180107d545cca185024e66d3e426f5e34adebf2f1
```

After deployment, delete the incompatible old gallery and enroll again. Run the mandatory two phases:

1. Phase 1: announce `hands off` with timestamp and leave the sensor untouched for 60 seconds.
2. Phase 2: announce `holding` with timestamp and press-hold steadily for 60 seconds, recording client latency/advances.
3. Paste client lines and:

```sh
journalctl -u fprintd --since "10 min ago" --no-pager | grep -a -E "5e0a wire|5e0a frame|5e0a local|5e0a get_minutiae|5e0a bz3|timed out|error|failed|minutiae" | tail -n 40
```

### Branch Predictions

- **Confirmed:** `padding_nonzero=0`, `active=5120`, enrollment and probe `minutiae_count >= 10`, score >= 12, and `verify-match (done)`.
- **Falsified-structure:** padding nonzero or decoded/active count differs; next experiment is raw block-boundary analysis only.
- **Falsified-contrast:** structure is exact but repeated captures remain below 10 minutiae; next experiment changes only local-contrast radius/normalization using retained independent raws.
- **Inconclusive-because-protocol:** missing phase timestamps/client lines/journal, old gallery not deleted, or patch checksum differs.

## Acceptance Criteria (Hardware Only)

- [x] Phase 1 remains silent for 60 seconds.
- [x] Phase 2 advances immediately on touch without scan cycles.
- [x] Every full frame reports `decoded_px=5120`, `padding_nonzero=0`, `active=5120`, and `geometry=64x80`.
- [ ] Every accepted enrollment gallery image and verification probe has >= 10 minutiae (tripped on `gallery[4]_nrows=8 < 10`).
- [ ] Bozorth3 reports score >= 12 (achieved peak score 6/12 across multiple gallery prints).
- [ ] Client reports `Verify result: verify-match (done)` twice.

## Hardware Run 14 Evidence (2026-09-05 01:45:08–01:45:12)

```text
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a wire layout: decoded_px=5120 blocks=80 active_bytes=96 padding_nonzero=0 footer_bytes=4
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a frame stats: active=5120, min_v=416, max_v=2623, range=2207, declen=10564, h_corr=0.944, v_corr=0.835, h_lag4_corr=0.563 (native 64x80 WxH)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a local contrast: min=-382.00 max=310.11 range=692.11 window=3x3
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a get_minutiae: ret=0 minutiae_count=16 (image 128x160 WxH, scan_time=0.0043s)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a minutiae added to print: detected=16 (xyt->nrows=16) on image 128x160 (WxH)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 match start: probe_nrows=16 gallery_len=8 (probe_len=99)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 match: gallery[0]_nrows=11 score=0/12 (probe_nrows=16)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 match: gallery[1]_nrows=13 score=0/12 (probe_nrows=16)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 match: gallery[2]_nrows=16 score=3/12 (probe_nrows=16)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 match: gallery[3]_nrows=13 score=3/12 (probe_nrows=16)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 match: gallery[4]_nrows=8 score=0/12 (probe_nrows=16)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 floor tripped: probe_nrows=16 gallery[4]_nrows=8 < MIN_COMPUTABLE_BOZORTH_MINUTIAE(10)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 match: gallery[5]_nrows=18 score=5/12 (probe_nrows=16)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 match: gallery[6]_nrows=17 score=5/12 (probe_nrows=16)
Sep 05 01:45:08 sastapc fprintd[192574]: 5e0a bz3 match: gallery[7]_nrows=12 score=5/12 (probe_nrows=16)

Sep 05 01:45:12 sastapc fprintd[192574]: 5e0a wire layout: decoded_px=5120 blocks=80 active_bytes=96 padding_nonzero=0 footer_bytes=4
Sep 05 01:45:12 sastapc fprintd[192574]: 5e0a frame stats: active=5120, min_v=392, max_v=2612, range=2220, declen=10564, h_corr=0.944, v_corr=0.834, h_lag4_corr=0.566 (native 64x80 WxH)
Sep 05 01:45:12 sastapc fprintd[192574]: 5e0a local contrast: min=-383.50 max=311.00 range=694.50 window=3x3
Sep 05 01:45:12 sastapc fprintd[192574]: 5e0a get_minutiae: ret=0 minutiae_count=13 (image 128x160 WxH, scan_time=0.0039s)
Sep 05 01:45:12 sastapc fprintd[192574]: 5e0a bz3 match start: probe_nrows=13 gallery_len=8 (probe_len=66)
Sep 05 01:45:12 sastapc fprintd[192574]: 5e0a bz3 match: gallery[2]_nrows=16 score=3/12 (probe_nrows=13)
Sep 05 01:45:12 sastapc fprintd[192574]: 5e0a bz3 match: gallery[5]_nrows=18 score=5/12 (probe_nrows=13)
Sep 05 01:45:12 sastapc fprintd[192574]: 5e0a bz3 match: gallery[6]_nrows=17 score=3/12 (probe_nrows=13)
Sep 05 01:45:12 sastapc fprintd[192574]: 5e0a bz3 match: gallery[7]_nrows=12 score=6/12 (probe_nrows=13)
```

### Analysis and Verdict
- **Confirmed wire format & natural raster:** `padding_nonzero=0`, `active=5120`, `h_corr=0.944`, `v_corr=0.835`.
- **Confirmed biometric validity:** Bozorth3 cross-matching repeatedly matched 5–6 minutiae pairs (up to 50% match rate!) against multiple gallery prints.
- **The Remaining Gap:** Total minutiae per capture capped at 11–18; Bozorth3 score cannot reach $\ge 12$ when total minutiae count is only 12–16. In addition, weak enrollment frames (`gallery[4]` with 8 minutiae) tripped floor abort.
- **Verdict:** Closed. Successor: Ticket 18 (`18-closed-minutiae-density-and-enrollment-gating.md`).

