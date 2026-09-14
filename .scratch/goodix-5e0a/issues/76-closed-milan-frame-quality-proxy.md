# 76: Native Milan Frame Quality Proxy & Multi-Touch Best-of-N Gating

**What to build:** Casual, light, or off-center finger taps reliably match on the first touch (90%+ first-touch genuine acceptance rate like Windows Hello) by replacing legacy NBIS Bozorth minutiae-count judging with Milan's native quality evaluation (`getQuality` export).

**Blocked by:** 75 (Back-to-Back Claim TLS Lifecycle & Park/Shutdown Hygiene)

**Status:** closed (verdict: falsified — native `quality` is 0 on all live frames, `overlap` is flat intra-burst; ranking collapses to minutiae order, behavior unchanged)

## Acceptance Criteria

- [x] In `goodix5e0a_keep_best_frame`, the legacy NBIS minutiae count proxy (`goodix5e0a_count_minutiae`) is replaced or augmented with Milan's native quality export (`getQuality(&probe, q)`) or proven dynamic range metric.
- [x] During the 4-frame burst per touch, the frame with optimal ridge clarity according to Milan's engine is selected and submitted.
- [ ] First-touch match reliability on real hardware improves so casual taps (which scored minutiae=13 in Attempt 2) match without requiring slow, deliberate pressing.
- [ ] Zero false accepts: impostor/wrong fingers remain 100% rejected (score 0).
- [x] Ninja build succeeds, test suite passes, and patch is synced to NixOS module.

## Context & Evidence

- In Ticket 74 Hardware Run 2:
  - Deliberate press (Attempt 1) had `minutiae=22`, and matched immediately with PAM `sudo -v`.
  - Casual tap (Attempt 2) had `minutiae=13`, showing lower ridge signal under the current NBIS proxy.
- In Ticket 72 (`experiments/test_goodix_shootout.c`), Goodix's Milan engine explicitly exports `getQuality(GoodixImage *img, u32 q[2])`. Currently, the driver still runs NBIS minutiae extraction to judge frames even though Milan does not use minutiae points.

## Implementation (2026-09-14, agent build, no hardware yet)

One variable: burst-winner ranking only. Enrollment floor (`GOODIX_5E0A_ENROLL_MIN_MINUTIAE = 16`, minutiae-based) intentionally unchanged.

- `libfprint-driver/goodix_milan.h/.c`: new `goodix_milan_frame_quality(pixels, w, h, &quality, &overlap)` wrapping the `getQuality` export. `getQuality` resolves **optionally** (missing export logs `g_debug` and degrades instead of failing engine init). Fixed 64x80 geometry guard; engine/export down returns 0/0. Returns combined rank `(quality << 8) | overlap` (quality primary, overlap breaks ties). Ticket-72 offline ranges: good frames 18-19/98-100, blank/noise/poor 0/0.
- `libfprint-driver/goodix5e0a.c/.h`: `keep_best_frame` measures the native pair on `latest_norm_pixels` (the exact 64x80 buffer verify feeds Milan, never the 128x160 scaled `FpImage`), ranks lexicographically quality → overlap → minutiae. Engine down collapses to exact ticket-39 minutiae order (all pairs 0/0). New `best_quality`/`best_overlap` state, zeroed in reset/init, cleared on claim. Journal lines extended (minutiae kept for old greps):
  - `5e0a frame %u/%u: declen=%u active=%u range=%u minutiae=%u quality=%u overlap=%u score-proxy=%u`
  - `5e0a best frame %u/%u: minutiae=%u quality=%u overlap=%u score-proxy=%u (submitting)`
  where `score-proxy = (quality << 8) | overlap`. No bare `score` outside `score-proxy` (pinned by f39/f40).
- Tests: new `tests/tier1_feature/test_f76_milan_quality_proxy.py` (5 tests); f39 updated to native-pair journal + rank pins; LOC caps 1850→1900 (f13, m2, +41 non-blank lines); patch SHA pin rolled (m1_c1).
- Evidence: ninja drivers-only build links clean; `bash tests/run_all_tests.sh` → 464 passed, 0 failed, 1 env-gated skipped; unified patch regen + byte-identical sync to `/home/sastauser/NixOS-Hyprland/modules/goodix/` (SHA-256 `62325760f8f56c8216a54e686f2edce23cda3c0bd6fe1bc916821001be76e972`); build-tree `diff -q` clean.

## Hardware Verify Protocol (user-only; agent has no fingers/sudo)

Deploy then run the two phases exactly as AGENTS.md prescribes:

```
cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd && fprintd-enroll
sudo systemctl set-environment G_MESSAGES_DEBUG=all
# Phase 1: hands off 60s — note "hands off" + timestamp, expect silence (no cycles)
# Phase 2: press-hold steady 60s + casual taps — note "holding" + timestamp
journalctl -u fprintd --since "YYYY-MM-DD HH:MM" | grep -E "5e0a frame|5e0a best frame|Milan verify|timed out|Invalid ACK|verify-unknown-error|failed to"
sudo systemctl set-environment G_MESSAGES_DEBUG=
```

Predicted journal signatures per branch:

- **Confirm** (Milan proxy works): per-touch `5e0a frame` lines show non-zero `quality`/`overlap` with spread across the 4 frames (e.g. ramp 5/40 → settled 18/98); `best frame` submits the settled frame even when its minutiae is lower than an early frame's; casual taps verify-match first touch; held wrong finger still exactly one `verify-no-match` with ~18s FDT-UP re-issue loop until lift; smoke grep empty of `timed out|Invalid ACK|verify-unknown-error|failed to` in the match-claim window (ticket-47/53 tolerant `0x34 timed out` under held-finger excepted).
- **Falsify** (proxy has no dynamic range on live frames): all 4 frames report `quality=0 overlap=0` (or identical pairs) so `score-proxy=0` throughout and winner == old minutiae winner line-for-line; casual taps still need deliberate presses. Next experiment then: log `qout[2]` side-channel + per-frame residual_range correlation to find a proven dynamic-range metric (do NOT re-litigate minutiae removal without that data).
- **Inconclusive-because-flaw**: `getQuality export missing` debug line (wrong DLL on target), or any `timed out|Invalid ACK` noise from a dirty TLS park (re-run after `sudo systemctl restart fprintd`). Conclude only confirmed / falsified / inconclusive-because-[flaw] + the single next experiment.

## Hardware Verdict: FALSIFIED (2026-09-14 ~19:02, fprintd[327032], user-pasted journal)

User report: "works similar, got a few match and a few rejection — normal." No regression; behavior identical to ticket-39 minutiae judging.

Evidence — Burst A (19:02:05): `frame 3/4: minutiae=11 quality=0 overlap=36`, `frame 4/4: minutiae=14 quality=0 overlap=36`, winner `best frame 1/4: minutiae=18 quality=0 overlap=36`. Burst B (19:02:19): all four frames `quality=0 overlap=25` with minutiae 19/19/18/18, winner `best frame 1/4: minutiae=19`. This is exactly the pre-registered falsify signature: `quality=0` on every live frame, proxies tie within each burst, winner == old minutiae winner line-for-line.

Secondary signals for the successor experiment:
- `quality=0` even on frames that went on to verify-match, so the field does not mean "unmatchable" — it carries no rank info for our pipeline as currently fed.
- `overlap` varies *between* touches (36 vs 25) but is constant *within* a burst, so it cannot rank best-of-N either.
- Prime suspect is the normalization mismatch: the ticket-72 offline frames that scored 18-19 went through the shootout's local-contrast path (`gain=1.5`), while the driver feeds `gain=1.0` (`GOODIX_5E0A_CONTRAST_GAIN`) buffers to `getQuality`. `getQuality` may be contrast-amplitude sensitive.
- No `timed out|Invalid ACK|verify-unknown-error|failed to` noise in the pasted window; the `USB reset taken (dirty close)` + `warm expired: reason=cold-start` between claims is the known ticket-75 dirty-close path, not signal.

Successor: ticket 78 (offline `getQuality` contrast-response probe — sweep gain/input variants through quality/overlap/`qout` + `identifyImage` on saved pgm frames, zero hardware risk). Do NOT re-litigate minutiae removal without that data. Ticket 77 is unblocked by this closure (driver behaves as ticket-39; gallery isolation is independent of frame ranking).
