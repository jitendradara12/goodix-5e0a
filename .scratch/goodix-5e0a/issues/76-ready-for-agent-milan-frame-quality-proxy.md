# 76: Native Milan Frame Quality Proxy & Multi-Touch Best-of-N Gating

**What to build:** Casual, light, or off-center finger taps reliably match on the first touch (90%+ first-touch genuine acceptance rate like Windows Hello) by replacing legacy NBIS Bozorth minutiae-count judging with Milan's native quality evaluation (`getQuality` export).

**Blocked by:** 75 (Back-to-Back Claim TLS Lifecycle & Park/Shutdown Hygiene)

**Status:** ready-for-agent

## Acceptance Criteria

- [ ] In `goodix5e0a_keep_best_frame`, the legacy NBIS minutiae count proxy (`goodix5e0a_count_minutiae`) is replaced or augmented with Milan's native quality export (`getQuality(&probe, q)`) or proven dynamic range metric.
- [ ] During the 4-frame burst per touch, the frame with optimal ridge clarity according to Milan's engine is selected and submitted.
- [ ] First-touch match reliability on real hardware improves so casual taps (which scored minutiae=13 in Attempt 2) match without requiring slow, deliberate pressing.
- [ ] Zero false accepts: impostor/wrong fingers remain 100% rejected (score 0).
- [ ] Ninja build succeeds, test suite passes, and patch is synced to NixOS module.

## Context & Evidence

- In Ticket 74 Hardware Run 2:
  - Deliberate press (Attempt 1) had `minutiae=22`, and matched immediately with PAM `sudo -v`.
  - Casual tap (Attempt 2) had `minutiae=13`, showing lower ridge signal under the current NBIS proxy.
- In Ticket 72 (`experiments/test_goodix_shootout.c`), Goodix's Milan engine explicitly exports `getQuality(GoodixImage *img, u32 q[2])`. Currently, the driver still runs NBIS minutiae extraction to judge frames even though Milan does not use minutiae points.
