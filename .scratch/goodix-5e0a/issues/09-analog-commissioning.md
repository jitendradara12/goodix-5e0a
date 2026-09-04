# 09 — Analog commissioning (sensor outputs banding, not ridges)

**What to build:** Captures whose live columns carry ridge signal instead of
row-locked noise, proven by metrics below. Everything downstream (gate,
polarity, geometry, enroll) is parked until this lands — it currently has no
signal to preserve.

**Blocked by:** None — hardware experiments + driver init changes.

**Status:** superseded by 10 — capture ground truth (35B FDT, 05-payload,
10638B replies, touch-gated 0x32, D32 status byte) answers the analog
questions structurally. Suspect list retired, not merely parked.

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

0. STATUS 09-03 late: Suspect 1 (CONFIG_52XD + reg `0x030a` + live corr
   metrics) deployed — frames still banding (`adj≈0.83`, `dist≈0.89`),
   minutiae zero. CONFIG eliminated (WBDI and 52XD fail identically); reg
   value eliminated (05 03 / skip / 0x030a all identical); polarity frozen
   OFF (511-match, do not flip-flop — moot until ridges exist). New key
   realization recorded below: the "proven script frame" carries the SAME
   banding signature (uniform ~0.8 corr), so script-vs-driver was never a
   content contrast — both paths band. The sensor has never verifiably
   produced ridges on Linux.

1. `0x022c` value and toggle schedule — DONE, eliminated (see 0).
2. Exposure pairing (Experiment E, NEXT): the 52xD trace pairs FDT DOWN
   trailing `…05 03 a7 00 a1 00 a7 00 a3 00 00` with image payload
   `45 03 a7 00 a1 00 a7 00 a3 00` — trailing bytes echoing each other. The
   driver has never run this exact pairing (only `01`+39B-FDT and
   `45`+39B-FDT without stats). Test: per poll, 39B DOWN fire-and-forget
   (tolerant, never wait/block), then `45`-payload capture, reg `05 03`,
   config 52XD. Read `max_v`/corr on hold. Brighter/decaying corr =
   confirmed. Identical banding = falsified, move to 3.
## Suspect 3 (ACTIVE): full analog bring-up as one experiment

Experiments B–E falsified one variable at a time with zero movement. What
has never run in the driver is the 52xD bring-up *sequence* (its elements
only work as a pipeline): POV image check + POV config, calibration captures
with `0x022c` toggles, sleep/query transitions — then the finger wait. Add
the sequence with a journal marker per stage so partial progress is visible
in `5e0a frame`-style lines. Rationale for one unit instead of stepwise:
each element alone is not expected to function. If content appears, bisect
for minimality afterwards; if zeros persist with the full pipeline, escalate
to capture-timing/inter-command-gap analysis with the stage markers as
evidence. Do not touch transport/activation-TLS core, tests, or frozen files.
4. Capture timing within the poll loop (integration window vs read moment)
   and inter-command gaps (driver fires in ms; scripts always had 100ms+
   Python overhead between commands).

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
