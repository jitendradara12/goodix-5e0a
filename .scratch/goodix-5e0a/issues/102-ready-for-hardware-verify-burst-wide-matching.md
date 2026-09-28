# 102: Burst-Wide Matching Probes (Ticket 102)

**What to build:** Bank every frame of the per-touch burst and let the Milan
engine probe the *whole touch* — verify, identify and the ticket-84 fast path —
instead of only the single frame the ticket-39/76 ranker picked. The ranker is
demonstrably unable to say which impression of a live touch is matchable; the
engine's own per-frame verdict must decide.

**Blocked by:** none (ticket 101 landed the per-touch burst reset this builds on).

**Status:** ready-for-hardware-verify

**Owns:** `libfprint-driver/goodix5e0a.c` probe path, `tests/tier1_feature/test_f102_burst_probe_matching.py`,
pin rolls in `test_f13`/`test_m2` (LOC cap), `test_f77`/`test_m3` (engine call
site), `test_f84` (fast-path probe). No matcher thresholds, no normalization,
no enrollment-selection change.

## Defect / root cause

`goodix5e0a_deliver_frame` handed the engine exactly one buffer: `best_pixels`,
the frame the best-of-N ranker chose. When that frame is not matchable, verify
reports `verify-no-match` even though the same physical touch contains frames
the engine would accept — and every burst loses the match, producing the
reported "everything gives verify-no-match" behaviour on light or partial
presses.

The ranker cannot be fixed instead of bypassed:

- ticket 76 (closed/falsified): every *live* frame reports `quality=0`, and
  `overlap` is constant within a burst, so the primary key is dead on live data
  and the winner falls through to the tiebreakers.
- ticket 79 (closed/falsified): the residual-range tiebreaker measures
  partial-contact edge energy, not ridge clarity — a casual tap (range 935)
  outranked genuine synthetic dense input (727), i.e. it can prefer the *worst*
  frame. Winner selection was therefore sometimes actively counterproductive.

Enrollment is deliberately unchanged: there the engine already decides (a bad
candidate is rejected with `add_res=131` and the touch retries), so one ranked
candidate per touch is safe. Verify has no such gate — a bad probe is simply a
no-match — which is exactly the asymmetry this ticket fixes.

## Implementation (software complete)

- Struct: `burst_pixels[4][5120]` + `burst_active[4]`, zeroed by
  `goodix5e0a_reset_touch_frames` (touch start, claim entry, SSM completion,
  deactivate, suspend, enroll reject/continue — the ticket-39/101 hygiene sites
  are untouched, reset-call count stays 8).
- `goodix5e0a_keep_best_frame` banks each frame (pixels + raw `active` count)
  *in addition* to tracking the ranked winner in `best_pixels` (still what
  enrollment submits).
- `goodix5e0a_burst_probe_order` returns 0-based probe indexes: ranked winner
  first, then the remaining usable frames in capture order; a frame that failed
  normalization (`active < 64`, zeroed buffer) is never returned.
- `goodix5e0a_verify_burst` (new, the ONLY `verifyImage` call site) probes that
  order and returns the engine's verdict on the first accepted frame
  (`*out_pts` = that frame's points). The ticket-84 fast path now calls this
  helper instead of keeping a second copy of the engine call.
- `goodix5e0a_identify_best_frame` probes the same order against the gallery
  (still the ONLY `identifyImage` call site). The bounds check and fail-closed
  behaviour are unchanged.
- Deliver verify/identify gate on `probes == 0` (no usable burst frame) with the
  pre-existing `no usable frame, reporting ... no-match` journal lines.
- Journal: per-probe lines are `fp_dbg` (`5e0a verify probe %u/%u (frame %u)`,
  `5e0a identify probe %u/%u (frame %u)`); the always-on `g_message` budget
  stays at 25 and the `5e0a Milan verify: match=%d pts=%d` /
  `5e0a Milan identify: ...` verdict lines are unchanged (ticket-89 parser
  contract).

Counter-arguments considered:

- **FAR**: the per-frame decision is untouched (`matched_idx == 0 &&
  match_score > 0` inside `goodix_milan_verify_image`/`identify_image`); the
  burst only offers more impressions of ONE touch. Offline evidence has
  impostor scores at exactly 0 (ticket 77: 3/3 rejected, FAR 0%), and ticket 89
  keeps thresholds unchanged. A 4x probe count per touch is the open FAR
  question and is exactly what the hardware run measures (wrong-finger checks).
- **Latency**: an unambiguous touch still costs one engine call (winner first);
  only bursts whose winner fails pay up to 3 more.
- **CPU**: identify unpacks the gallery per probe; with 1-2 enrolled fingers
  this is milliseconds, and only on a would-have-been no-match.

## Acceptance Criteria

- [x] Driver: burst banked per frame, zeroed per touch; probe order; shared
      `goodix5e0a_verify_burst`; identify probe loop; `probes == 0` gates.
- [x] Tests: new `tests/tier1_feature/test_f102_burst_probe_matching.py`
      (bank/reset, probe-order shape + behavioural model, one engine call site
      each, no-usable-frame gates, journal budget, no bare `score`).
- [x] Pin rolls, intent preserved: `test_f13`/`test_m2` LOC cap 2000 → 2150
      (+85 non-blank lines); `test_f77`/`test_m3` assert one engine call site
      per operation instead of `(self->best_pixels,` at it; `test_f84` asserts
      the fast path uses the shared helper.
- [x] Software suite: `GOODIX_NATIVE_TESTS=skip bash tests/run_all_tests.sh` →
      380 passed, 0 failed, 8 skipped (nix/native lanes unavailable here).
- [x] Abstract compile check of the changed functions with stub types under
      `gcc -std=gnu99|gnu11 -Wall -Wextra -Werror` (no glib in this
      environment, so the full libfprint build is a deploy-time gate).
- [ ] Ninja/libfprint build + deploy on the target.
- [ ] Hardware verify (protocol below).

## Hardware verify protocol

Deploy, `sudo systemctl restart fprintd`, re-enroll both fingers (templates
from the pre-101 driver must not be reused), then per AGENTS.md:

1. Phase 1, hands off 20s ("hands off" + timestamp): silent vs cycles.
2. Phase 2, press-hold steady 20s + casual taps ("holding" + timestamp):
   latency, advances.
3. 10 normal verifies per finger, 5 wrong-finger checks per finger; record
   match rate and `pts=`/probe lines.

Journal collection: `G_MESSAGES_DEBUG=all` (probe lines are debug-level), then
`journalctl -u fprintd --since "YYYY-MM-DD HH:MM" | grep -E "5e0a verify probe|5e0a identify probe|5e0a Milan verify|5e0a Milan identify|5e0a frame|5e0a best frame|verify-no-match|failed to"`.

Predicted signatures (pre-registered):

- **Confirm**: bursts whose ranked winner fails log `verify probe 1/N ... match=0`
  followed by `verify probe 2/N (frame K): match=1 pts=<n>` and the touch
  reports `verify-match`; journal shows `2/4`..`4/4` probes on the previously
  failing light taps; wrong fingers log every probe `match=0` and exactly one
  `verify-no-match`; verify latency unchanged for settled presses (single
  probe).
- **Falsify**: still `verify-no-match` on every deliberate press with all four
  probes `match=0` (→ the burst content itself is unmatchable: next experiment
  is enrollment-side, comparing `enrollAddImage` acceptance against the verify
  probe frames), or casual light taps now `verify-match` while a wrong finger
  also starts matching (→ per-burst FAR blow-up: next experiment caps the probe
  count or requires 2-frame agreement).
- **Inconclusive-because-[flaw]**: dirty TLS park noise (`Invalid ACK`,
  `timed out` outside the known held-finger 0x34 case), missing
  `G_MESSAGES_DEBUG` so probe lines are absent, or templates not re-enrolled
  after ticket 101/102.

## Notes

- Supersedes nothing; tickets 76/79 stay closed/falsified and are cited as the
  evidence that ranking cannot be repaired. Do NOT re-litigate gain 1.5
  (ticket 78/101) or minutiae floors here.
- The single next experiment after a falsified hardware run: compare the same
  banked burst frames offline through `legacy-experiments/` against a live
  template, then decide enrollment-side selection. No third matcher/vendor
  change without that data.
