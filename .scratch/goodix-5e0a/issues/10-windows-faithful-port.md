# 10 — Windows-faithful steady-state port (replaces 08 and 09)

**What to build:** The enroll/verify scan loop driven exactly like the vendor
Windows driver does it on this firmware (APP_10036), per USBPcap ground truth
(`goodix-27c6-5e0a-re/captures/goodix-win.pcapng`, enroll+duplicate, 1027
packets; subagent briefs on file). End state: touch-gated stages, completed
enroll, double verify — no polling, no FDT-mode command, no per-cycle reset.

**Blocked by:** None — ready now. (Supersedes 08 and 09 with rationale below;
transport/activation/TLS core stays frozen.)

**Status:** superseded by 11 — 35B FDT S12 auto-fires in empty air (`status=0x02 len=20` every 7-8s), falsifying touch-gating on 0x32 for APP_10036. Image payload 05 returned 7684B of pure zeros. Successor: 11 (Active Content Capture).

## Hardware Run Results (2026-09-04 15:22-15:25, deployed driver)

- **Phase 1 (Hands off, 61s: 15:22:45 – 15:23:46):**
  Auto-fires every 7–8 seconds in empty air:
  ```
  Sep 04 15:22:45 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  Sep 04 15:22:53 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  Sep 04 15:23:01 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  Sep 04 15:23:08 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  Sep 04 15:23:16 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  Sep 04 15:23:23 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  Sep 04 15:23:31 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  Sep 04 15:23:39 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  Sep 04 15:23:46 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  ```
  **Verdict**: FALSIFIED. `0x32` with 35B S12 does *not* block on touch; it returns `0x02` in ~10ms on empty air. It is a mode acknowledgement, not a hardware touch gate. The ~7.5s cycle is driven by the 5000ms `0x34` release timeout.

- **Phase 2 (Touch at 15:24:39):**
  Finger placed firmly on sensor:
  ```
  Sep 04 15:24:39 sastapc fprintd[32438]: 5e0a D32 reply: status=0x02 len=20
  Sep 04 15:24:39 sastapc fprintd[32438]: 5e0a scan_on_read_img: declen=7684
  Sep 04 15:24:39 sastapc fprintd[32438]: 5e0a raw first 16 bytes: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  Sep 04 15:24:39 sastapc fprintd[32438]: 5e0a raw_frame: num_px=5120 nonzero=0 min=0 max=0
  Sep 04 15:24:39 sastapc fprintd[32438]: 5e0a active cols: NONE (all 0)
  ```
  **Verdict**: Image payload `05 00 b0 00 b2 00 b0 00 b1 00` returned 7684 bytes of pure `0x00` under firm physical touch.
  Bypassing register `0x022c` write changed nothing (zeros persist both with `0x030a` and without).

## Why this replaces everything (do not re-litigate)

- 39-byte FDT tables are wrong length on this firmware: Windows sends
  35-byte payloads (pack 39) for both `0x32` DOWN and `0x34` UP, zero `0x36`
  anywhere in 193 host commands. The six `80 XX` slots adapt per touch (not
  a fixed table); the `+0x18` experiment is dead.
- `0x32` DOES block for touch with correct bytes (first H32→D32 5814ms vs
  33–419ms steady). All "never blocks" findings used malformed 39B payloads.
- Image payload is `05 00 b0 00 b2 00 b0 00 b1 00` verbatim (37/37 identical),
  reply is B2 pack10638 (~10560px plaintext) — not 7762B/7680px. Current
  geometry assumptions are void; re-derive (below).
- Touch status is explicit: D32 reply byte0 `02` = proceed to image,
  `80` = poor contact → host re-issues DOWN with new params (double-32).
- Steady state needs NO reset/config/reg/TLS-handshake per cycle and no
  per-poll query invention: the loop is `ae → d6(session start only) → 32 →
  20 → 34 → ae → 34 → D34-wait(~500ms) → next`.
- The "proven script frame" banding and all payload/config debates are moot:
  they used wrong lengths against wrong assumptions.

## Precise loop to implement (5e0a-gated; 511/others untouched)

1. Per image, in order with measured gaps (ACKs ~1ms, image reply ~20ms,
   D34 wait is REPLY-driven ~500ms not slept, D32 wait is reply-driven with
   generous timeout — never fixed sleeps):
   `ae(00 01 00)` → [`d6(00 00)` session-start only, expect `ffff`] →
   `32(DOWN-vtable below)` → read D32 reply → if byte0==`0x80`, re-issue DOWN
   once with next params then proceed → `20(05 00 b0 00 b2 00 b0 00 b1 00)` →
   read B2 (expect pack10638) → `34(UP-pair, both identical)` → `ae` →
   `34(same UP)` → await D34 reply → next image.
2. DOWN table (35B): `1c 01 b0 00 b2 00 b0 00 b1 00` + six `80 XX` slots +
   `00 00 00 00` + `b0 00 b2 00 b0 00 b1 00 00`. START with the most frequent
   steady-state variant S12 (pkts 302/328/406/432/792):
   `…80 b7 80 ce 80 aa 80 be 80 b1 80 c2…` (full bytes in capture brief;
   re-read them from the pcap, do not trust memory). Poor-contact retry:
   re-issue (same table first version; adapt slots only if `80` loops).
3. UP table (35B): `0e 01 b0 00 b2 00 b0 00 b1 00` + six `80 XX` slots +
   13×`00`, both U in one image IDENTICAL. START with U01 (pkts 42/50).
   Deactivate path: send `0x60 01 00` (sleep, observed post-enroll).
4. Frame decode: same 12-bit 6B→4px family unpacking into ~10560 px
   (10624-byte TLS plaintext minus 16B IV, 32B MAC, pad). Geometry
   candidates: 80x132 / 88x120 / 64x165 — DO NOT assume 80x64 or 4k+3
   columns. Re-derive the live-column map empirically from the first live
   Windows-sized frames (column-energy scan), then fit gate/demosaic to
   what is measured. Minutiae acceptance picks the winner.
5. Keep from current code: frozen transport (`goodix.c/h/proto`,
   `goodixtls.c`), per-frame stats/corr journal logging (extend to new
   size), tolerant single-flight + NOP behavior, existing activation
   (reset/config/reg/TLS — works, and cold-init bytes are NOT in the warm
   capture; do not churn it).
6. Rebuild derivation, refresh unified patch, commit. Cold-plug capture
   (init bytes) is explicitly OUT of scope unless steady-state acceptance
   fails after this port.

## Acceptance criteria (deployed driver, hardware only)

- [ ] Hands-off enroll: silent, blocked in DOWN wait (no session churn).
- [ ] Touch: stage advances within seconds; full enroll completes.
- [ ] Journal shows content frames with decaying (not uniform) correlation
      and extracted minutiae counts > 0.
- [ ] `fprintd-verify` matches twice, no restart. Then ticket 07 runs.

## Rollback criteria

- Timeouts/unknown-errors/session loops → revert to pre-10 commit, paste
  journal + the exact poll bytes sent. Do not stack fixes.
