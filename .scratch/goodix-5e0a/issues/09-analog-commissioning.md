# 09 — Analog commissioning (sensor outputs banding, not ridges)

**What to build:** Captures whose live columns carry ridge signal instead of
row-locked noise, proven by metrics below. Everything downstream (gate,
polarity, geometry, enroll) is parked until this lands — it currently has no
signal to preserve.

**Blocked by:** None — hardware experiments + driver init changes.

**Status:** ready-for-agent

## Decisive measurement (09-03, offline on saved live frame, reproducible)

Inter-column Pearson correlation of row profiles across the 19 live columns
(`experiments/fingerprint.pgm`, same family as the live touch frame):
adjacent-column mean **0.80** (min 0.60), ALL-pairs mean **0.80**. Distant
columns (3 vs 75) correlate as strongly as neighbors. A real ridge field
decays with distance; uniform cross-frame correlation = ROW-LOCKED BANDING.
Consequences, all now settled: the "structured frame" premise is void (no
Linux capture has ever shown ridges — only banding + electrode pattern);
polarity/geometry/gate debates are moot; the 52xD-trace payload, config, and
register questions are all back open as *unproven*, not decided.

Reference orientation: `experiments/windows_unpacked.png` shows the electrode
pattern running VERTICALLY (correct). Live frames show energy running
HORIZONTALLY. A capture timing/mode error (reading mid-scan, wrong integration
window) fits better than any value tweak so far.

## Suspect list (test in this order, ONE variable per build)

1. `0x022c` value: tried `05 03` (zeros) and skip (zeros). Untested:
   `0x030a` and the `0x020a/0x030a` toggle schedule from the 52xD reference
   flow (which also interleaves calibration captures between toggles).
2. Missing init sequence from the 52xD flow, all absent in the driver:
   OTP-conditioned writes, POV image check + POV config, calibration captures,
   sleep/query transitions before arming. Port stepwise, not wholesale.
3. Capture timing within the poll loop (integration window vs read moment).
4. FDT/payload pairing (parked, not dead — revisit only after 1–3 fail).

## Method (no eyeballs, no "verified" without numbers)

- Feedback metric per build, press-and-hold: journal `max_v`/range
  (brightness proxy) PLUS a saved PGM per condition for the correlation test
  above (adjacent-mean must DROP toward ridge-like decay AND orientation must
  stop being single-direction before anything counts as signal).
- Keep poll-until-content, logging, frozen transport files, one variable per
  build, rebuild + two-phase verify each step.
- Do not touch `goodix.c/h/proto`, `goodixtls.c`, `tests/`.

## Acceptance criteria (deployed driver, hardware only)

- [ ] Held-finger frames show decaying inter-column correlation (not uniform ~0.8) and multi-direction orientation energy.
- [ ] Daemon journal shows extracted minutiae (count > 0) on held frames.
- [ ] Full enroll completes; `fprintd-verify` matches twice, no restart.

## Rollback criteria

- Any per-step regression (timeouts, unknown-errors, return to all-zero
  `active`) → revert that step only and report numbers. Do not stack changes.
