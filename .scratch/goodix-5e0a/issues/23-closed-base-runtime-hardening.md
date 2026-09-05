# 23 — Base runtime hardening: activation error completion + subtract floor

**What to build:** Two sequenced single-variable fixes in the shared base
(`libfprint-driver/goodix5xx.c`), B first, C only after B is confirmed.
No hardware specific to 5e0a behavior changes on the verified path.

**Blocked by:** None (hardware verify slots as specified per experiment).

**Status:** closed

**Verdict B + C (2026-09-05 18:43–18:44 IST, pid 42120, patch `6d3612ab`):
BOTH CONFIRMED.** Same run as ticket 24's confirm (combined run, rationale in
24): 5e0a behavior identical — clean activations, TLS every time, healthy
frames, no hangs. B's fixed path never fires on 5e0a (511-only, parity fix);
C's fixed line never executes on 5e0a (`has_calibration=FALSE`, synthetic
7-vector proof passed). No 5e0a delta possible by construction, none observed.

## Experiment B build record (2026-09-05, +2 lines, review APPROVE)

`tls_activation_complete` error branch now derives `image_dev` (mirroring the
success line) and calls `fpi_image_device_activate_complete (image_dev,
error)` before returning. Ownership: forward-once + return, matching
`goodix5e0a.c:191`, `goodix511.c:213` convention. 5e0a provably unaffected:
the fixed function is file-static, only called via `goodixtls5xx_init_tls`
from `goodix511.c:207`; 5e0a wires its own `on_tls_activation_complete`
(`goodix5e0a.c:218`), which already had this pattern. So the confirm run is
"normal 5e0a verify behaves byte-identically" — no fault injection needed.
Patch regen `9d9309e2…` synced + pins rolled. Experiment C NOT in this build
(per ticket: only after B confirmed).

## Experiment B confirm (2026-09-05 18:26–18:27 IST, pids 26918/27221)

Deployed `9d9309e2` (22+23B), enroll + verifies by user. Journal (agent-pulled):
5 clean activations, TLS ready every time, full `declen=10564` frames,
healthy stats (`h_corr 0.938–0.973`, `active=5120`), zero hangs/timeouts/
failures, scores up to 12/12. Behavior identical to pre-23B as predicted
(5e0a never takes the fixed path). Verdict: B CONFIRMED. Experiment C next.

## Experiment C build record (2026-09-05, review APPROVE + synthetic proof)

One body line in `linear_subtract_inplace`: floored subtract
`src[n] = (src[n] > by[n]) ? (src[n] - by[n]) : 0;` (int-domain by promotion,
no wraparound on any input — proved by cases in review). Dead
`const guint16 max = -1;` removed same-function (reviewer-ruled part of 23C;
kills the -Wunused-variable the body fix would otherwise introduce).
Synthetic proof: throwaway `/tmp` C harness, `gcc -Wall -Wextra`, all 7
vectors pass new expression, old expression reproduces ticket's broken values
(65435 / trunc-99 / 65535). 5e0a provably never executes it
(`has_calibration=FALSE` → guard never taken). Patch regen `6d3612ab…`
synced + pins rolled.

## Experiment B: complete activation with error instead of hanging
- Fact: `tls_activation_complete` (`goodix5xx.c:~570-579`) logs a TLS-leg
  error and returns WITHOUT `fpi_image_device_activate_complete` — activation
  hangs instead of failing cleanly. The sibling `dev_init` just above passes
  `error` through `fpi_image_device_open_complete (img_dev, error)` (`:546`),
  which is the codebase convention.
- Change (one variable): call
  `fpi_image_device_activate_complete (image_dev, error);` on the error
  branch before returning. Nothing else in the build.
- Predicted signatures — confirm: forced TLS-failure activation now
  completes-with-error promptly (journal shows the fp_err line then a clean
  failure, no hang); normal activations byte-identical in behavior.
  Falsify: any change to successful-activation behavior → revert.
- Validate first without hardware fault injection if possible: code review
  that no caller depends on the hang (none can — a hang has no consumers).

## Experiment C (only after B confirmed): fix `linear_subtract_inplace` floor
- Fact (pure arithmetic, no hardware needed to prove): with
  `max = (guint16)-1`, `max - ((max - src) - (max - by))` simplifies to
  `max - (by - src)`, which stays in `[0, 65535]` for all in-range pixels —
  so `MAX(0, …)` never selects 0 and `src < by` yields `~65435` instead of 0,
  corrupting `raw_frame` before `process_raw_frame`. Verified vectors
  (src,by → old,new): (100,200 → 65435,0), (200,100 → 65635→99 truncated,100),
  (0,0 → 65535,0), (3000,3000 → 65535,0). Broken in every case except by
  truncation luck. Intended result is `src - by` floored at 0.
- Scope note: the call site (`goodix5xx.c:362-363`) runs only
  `if (priv->calibration_img)`, and `has_calibration` is FALSE for 5e0a
  (`goodix5e0a.c:840`) but TRUE for 511 (`goodix511.c:313`) — so 5e0a is
  provably unaffected and this experiment needs a calibrating (511-family)
  device, or at minimum synthetic unit proof plus 5e0a no-change confirmation.
- Change (one variable): `src[n] = (src[n] > by[n]) ? (src[n] - by[n]) : 0;`
  Nothing else in the build.
- Predicted signatures — confirm: 5e0a frames/scores byte-identical
  pre/post (path never executes there); synthetic vectors
  (src<by → 0, src>by → difference) pass; 511 calibration frames lose the
  wraparound artifacts. Falsify: any 5e0a behavior delta → revert.

## Packaging (both experiments)
Regenerate the unified patch from base + re-sync deployed copies per ticket
19 §5 after EACH accepted build; F25 + SHA pin fail until then (expected).
Never combine B and C in one build.

## Acceptance (hardware verify protocol per experiment, no exceptions)
Standard 60s hands-off + press-hold with pasted client lines and journal
grep per AGENTS.md; conclude only confirmed / falsified /
inconclusive-because-[flaw] + the single next experiment.
