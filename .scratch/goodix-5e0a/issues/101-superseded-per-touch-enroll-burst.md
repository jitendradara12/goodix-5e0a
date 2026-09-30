# 101: Per-Touch Enrollment Burst Reset (Ticket 101)

**What to build:** Reset the best-of-4 burst state on the enroll-continue path
of `goodix5e0a_on_read_img` — `goodix5e0a_reset_touch_frames (self)` before
`fpi_ssm_next_state (ssm)` — so each of the 12 enrollment touches banks its
own 4-frame burst.

**Blocked by:** none.

**Status:** superseded (by ticket 102)

## Defect (code-level, independent of live data)

`reset_touch_frames` ran at claim entry, `scan_start` (once per operation — it
early-returns while the SSM is live), SSM completion, deactivate, suspend and
both enroll rejection paths. The enroll-continue branch was the one missing
site. Consequences on touches 2..12 of an enrollment:

- `frame_count` is already `>= GOODIX_5E0A_FRAMES_PER_TOUCH`, so
  `keep_best_frame` stops after ONE frame (journal: `frame 5/4 ... 11/4`).
- That single frame competes against touch 1's banked winner; unless it beats
  it on the quality proxy, the stale touch-1 pixels are submitted again
  (journal: same `best frame 3/4` with identical range/overlap every touch).
- A read error / short read on the next touch takes the `best_frame_no > 0`
  fallback and resubmits touch 1's winner instead of failing the touch.

Net effect: templates can be built from far fewer distinct impressions than
12, which plausibly raises FRR on verify. **Existing templates enrolled with
the pre-fix driver should be re-enrolled.**

## Rejected from the original PR #7: contrast gain 1.0 → 1.5

PR #7 also raised `GOODIX_5E0A_CONTRAST_GAIN` to 1.5. That part was dropped:

1. **It broke CI.** The native suspend harness
   (`tests/tier5_adversarial/test_suspend_recovery_c.c`,
   `/goodix/frame/normalization`) pins gain-1.0 values
   (`115 == 119` at the first edge pixel). The PR's "375/375 passed" was
   measured with `GOODIX_NATIVE_TESTS=skip GOODIX_SUSPEND_TESTS=skip`, so the
   one test that exercises the normalizer never ran.
2. **It re-litigates a closed, falsified hypothesis without addressing it.**
   Ticket 78 verdict (2): "Gain mismatch falsified as the live cause (do NOT
   re-litigate)". Ticket 79 then showed live partial-contact frames fail to
   enroll (`add_res=131`) at gain 1.0 AND 1.5. PR #7's "second-order" claim
   that 1.5 activates `getQuality` on live frames is the exact claim ticket 78
   falsified.
3. **The evidence was synthetic and not reproducible as written.** Every
   probe was a transform of the same synthetic frame the template was built
   from (12 pixel-shifted copies), which is the dense-synthetic regime ticket
   78/79 showed does not represent live frames. The committed harness opened
   `dense_%d.pgm` from the CWD while its instructions wrote them to
   `legacy-experiments/` and ran from the repo root, and its build line lacks
   glib flags. Internal numbers also disagreed (header "down to 40%" vs doc
   "down to 30%"; test "5-finger gallery" vs harness 4).
4. `pts=0` on light taps is long-known behaviour (ticket 77: "all `match=0
   pts=0` including the enrolled touch: light-tap variance again — same
   template scored 54 on a deliberate press"), not proof of a contrast floor.

If gain is revisited, it needs live burst captures (ticket 79/80 lane), and
the native normalization test must be updated with it.

## Acceptance Criteria

- [x] Driver: `goodix5e0a_reset_touch_frames (self)` in the enroll-continue
      branch, after the deliver tail, before `fpi_ssm_next_state` (+1 line;
      `goodix5e0a.c` 1999/2000 non-blank lines, `test_f13`).
- [x] Tests: `tests/tier1_feature/test_f101_per_touch_burst_reset.py`
      (placement, hygiene sites, gain untouched). Fails on ec5723d, passes here.
- [ ] Hardware: see protocol below.

## Hardware verify protocol

1. Deploy, restart fprintd, delete all enrolled fingers, re-enroll two.
2. Enrollment journal: every accepted touch logs `5e0a frame 1/4 .. 4/4` then
   its own `best frame N/4` — no `5/4+` numbering, no identical stats repeated.
3. 10 normal verifies per finger, 5 wrong-finger checks per finger. Record
   match rate and `pts=` per attempt.
4. Verdict: confirmed / falsified / inconclusive + single next experiment.
