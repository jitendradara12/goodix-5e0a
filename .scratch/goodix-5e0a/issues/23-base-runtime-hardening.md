# 23 — Base runtime hardening: activation error completion + subtract floor

**What to build:** Two sequenced single-variable fixes in the shared base
(`libfprint-driver/goodix5xx.c`), B first, C only after B is confirmed.
No hardware specific to 5e0a behavior changes on the verified path.

**Blocked by:** None (hardware verify slots as specified per experiment).

**Status:** ready-for-agent

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
