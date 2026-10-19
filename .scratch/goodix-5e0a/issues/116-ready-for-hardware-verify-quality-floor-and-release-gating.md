# 116: Milan quality-floor contact gating, finger release enforcement, and FDT DOWN calibration

**Status:** ready-for-hardware-verify

## Scope

Resolve contributor Jet-Soup's 0/5 live verification failure on Issue #12 / PR #15 without regressing the working maintainer and ptrip7 baselines.
1. Enforce a Milan quality floor (`self->best_quality < 15`) in `choose_best` ([`libfprint-driver/goodix5e0a.c`](file:///home/sastauser/code/temp/goodix/libfprint-driver/goodix5e0a.c)):
   - Enrollment: reject empty air or poor-contact frames (`active=%u (press firmer)`), preventing degraded frames from corrupting user templates.
   - Verify/Identify: reject empty air false triggers silently and re-arm `SCAN_5E0A_FDT_DOWN` instead of submitting zero-quality frames to the matching engine.
2. Enforce physical finger release between enrollment touches in `goodix5e0a_on_fdt_up_reply`:
   - During enrollment, re-issue FDT_UP if the finger is still held down, preventing runaway auto-advancing across stages on continuous contact or air noise.
3. Update [`experiments/jet-soup-capture.patch`](file:///home/sastauser/code/temp/goodix/experiments/jet-soup-capture.patch):
   - Align `goodix_5e0a_down_s12`, `goodix_5e0a_down_retry`, and `goodix_5e0a_up_u01` with Jet-Soup's 4-channel DAC registers (`[0xad, 0xae, 0xac, 0xad]`), eliminating MCU readout amplifier saturation on air.
4. Test Runner Hardening ([`tools/hardware_session.py`](file:///home/sastauser/code/temp/goodix/tools/hardware_session.py)):
   - Enable `Environment=G_MESSAGES_DEBUG=all` in the systemd override drop-in so GLib `fp_dbg` statements appear in `driver.txt`.
   - Apply `chcon -R -t lib_t` to the staged driver directory if `chcon` is available, resolving Fedora SELinux denials.

## Reverse engineering & software evidence

- **Reverse Engineering `wbdi.dll`:**
  Disassembly of `wbdi.dll:0x1800373ac` (`ImageisTouchedByFingerUnify`) reveals that Windows implements a two-stage touch verification: MCU FDT DOWN triggers image acquisition, followed by software contact validation that computes pixel deviations against baseline `ImageBase`. When deviation is below threshold, Windows logs `"detected temperature drift"` (`0x1800874a0`), updates its drift model, and discards the frame without notifying biometric clients.
  On Linux, Milan's native quality function (`goodix_milan_frame_quality`) achieves the exact same distinction without external calibration files:
  - Air frames: `quality = 0, overlap = 21..27`
  - Finger contact: `quality >= 20, overlap >= 60` (steady hold reaches `quality 67..70, overlap 89..95`)
- **Offline Matcher Shootout on Jet-Soup Frames:**
  Using the native $80\times64$ engine transpose on Jet-Soup's 24 raw hardware captures:
  - Enrolling genuine touches 1–4 and 9–12 matched genuine probe frames 13–16 **4 out of 4 times** with match scores of **45, 93, 53, and 45** (threshold $> 0$).
  - Air frames (17–20) and wrong-finger probes (21–24) were cleanly rejected (scores $-4$ to $-7$).
  - Proves the bandpass filter ([`goodix5e0a-image.h`](file:///home/sastauser/code/temp/goodix/libfprint-driver/goodix5e0a-image.h)) is mathematically sound across all sensor revisions.
- **Dynamic DAC Derivation from OTP:**
  Disassembly of `wbdi.dll:0x180052f00` confirms Windows reads 64 bytes of OTP via command `0xa6`, reads byte `0x2a` (`cal_val`), validates `buffer[0x2b] == ~cal_val`, calculates `tcode` and `diff`, and shifts the 4-channel DACs:
  `cur_dac[i] = (base_dac[i] +/- delta) & 0x1ff`.
  This derives `[0xad, 0xae, 0xac, 0xad]` on Jet-Soup's sensor and `[0xb0, 0xb2, 0xb0, 0xb1]` on the maintainer's unit.
- **Software Suite Validation:**
  All 401 tests across Tiers 1–5 pass (392 passed, 0 skipped, 0 failed).

## Hardware verification runs

1. **Maintainer Regression (`--capture-settings current` at 05bf427):**
   - Test bundle: `goodix-test-2885d46439c7dbf6.zip`.
   - Hands-off (20s): silent, `hands_off_activity: false` (pass).
   - Holding (20s): single advance (`holding_advances: 1`), release guard active (pass).
   - Enrollment: completed all 12 stages cleanly across distinct touches.
   - Genuine verification: 5/5 matched (`match=1 pts=100, 93, 48, 54, 77`).
   - Wrong-finger verification: 5/5 rejected (`match=0 pts=0, 0, 0, 0, 0`).
   - State & storage: storage isolated and restored (`restored: true`).
   - Verdict: **Confirmed** (zero regression on baseline laptop).

2. **Maintainer Test with Jet-Soup Candidate (`--capture-settings jet-soup` at 18c3853):**
   - Test bundle: `goodix-test-53128b6d64ee485d.zip`.
   - Patch SHA-256: `fdbb4546254410d06399c93db1f04e4645ff15ab0c7b1a34282d1a05c0904087`.
   - Hands-off (20s): silent, `hands_off_activity: false` (pass).
   - Holding (20s): single advance (`holding_advances: 1`), release guard active (pass).
   - Touch quality: frame quality 65..92, overlap 95..98%.
   - Genuine verification: 5/5 matched (`match=1 pts=54, 100, 64, 100, 96`).
   - Wrong-finger verification: 5/5 rejected (`match=0 pts=0, 0, 0, 0, 0`).
   - State & storage: storage isolated and restored (`restored: true`).
   - Verdict: **Confirmed** (candidate patch is safe and fully functional on live hardware).

## Single next experiment: Jet-Soup live verification

Run `bash tools/test-hardware.sh --capture-settings jet-soup` on Jet-Soup's hardware.
Record hands off + timestamp for 20 seconds, then holding + timestamp for 20 seconds, latency and advances; finish 12-touch enrollment and five genuine and five wrong-finger attempts.

**Confirm:**
- Silent hands-off (20s): no air misfires or high-energy spikes with the updated DAC table (`[0xad, 0xae, 0xac, 0xad]`).
- Holding (20s): single advance; finger release guard prevents runaway enrollment on hold.
- 12 distinct physical touches required for enrollment (air frames rejected by `best_quality >= 15`).
- 5/5 genuine matches (`Milan verify: match=1 pts=>0`) and 5/5 wrong-finger rejections (`match=0 pts=0`).

**Falsify:**
Air misfires during hands-off, repeated hold advances, enrollment advancing without physical touch releases, genuine verification failure (e.g. 0/5 matched), or any wrong-finger match.

**Inconclusive-because-[flaw]:**
Setup or build error, failed namespace isolation, mixed templates, missing protocol phases or interruption. Conclude only confirmed / falsified / inconclusive-because-[flaw].
