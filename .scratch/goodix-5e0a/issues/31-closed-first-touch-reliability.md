# 31 — First-touch reliability (make it actually usable)

**What to build:** Raise same-finger first-touch match rate from today's
~15–25% (best-score ≥12) to consistent first-try unlocks. Driver changes only
if Experiment 1 fails — gallery hygiene first.

**Blocked by:** None.

**Status:** closed

**Verdict — Experiment 2bis CONFIRMED (2026-09-05 20:51 IST, pid 31163):
3/3 first-try `verify-match`.** 12/12 enroll stages completed; gallery of 12
strong prints; probes 22–23 minutiae; bests 12/12, 12/12, 12/12 coming from
DIFFERENT gallery prints ([11], [0], [0]) — coverage working exactly as
theorized (was 0/3 with 8 prints). Margins are threshold-exact rather than
comfortable — pipeline/exposure headroom stays a future lever, but usability
(firm-press first-try unlocks) is achieved. No further driver change.

## Diagnosis (2026-09-05, agent-quantified from 6h journals, 131 touches)

- Per-touch BEST gallery score: mean 7.2, median 7; ≥12 only 15%, ≥10 25%.
  (Includes wrong-finger noise, but median 7 with probe median 16 minutiae
  shows genuine matching weakness, not just finger confusion.)
- Probe minutiae swing 3–29 (median 16); 18% of touches <12 (weak captures).
- Gallery polluted: 8 prints spanning 12–26 minutiae, including weak
  bring-up-era captures (12–13 floor-scrapers cap every comparison they are
  in — not the max, but they waste coverage).
- Pipeline CAN score: tonight's highs 24/12, 13/12, 12/12 on good touches.
  Disease is consistency, not ceiling.
- Hypothesis rank: (1) gallery pollution + touch variance dominate;
  (2) enrollment floor 12 admits marginal prints; (3) verify passthrough
  (ticket 20) sends faint touches to the matcher instead of re-prompting;
  (4) exposure/pipeline tuning last (ceiling proven fine).

## Experiment 1 (user, ~3 min, no deploy): clean re-enroll

1. `fprintd-delete "$USER"` (wipes the polluted gallery — all fingers).
2. `fprintd-enroll` the ONE login finger: 8 firm, centered, steady presses
   (hold ~1s each, cover the sensor fully, vary roll slightly per prompt).
3. `fprintd-verify` 3× with normal presses; report match/no-match each.
- Confirm: same-finger best-score rate jumps (agent measures from journal:
  median best ≥10, mostly first-try matches). Verdict confirmed → driver
  untouched, ticket closes on gallery hygiene.
- Falsify: still ~15% at threshold with a clean strong gallery → Experiment 2
  (driver-side: verify weak-probe re-prompt vs floor raise vs exposure —
  specified THEN from the new data, one variable).

## Experiment 1 verdict (2026-09-05 ~20:36 IST): FALSIFIED, mechanism found

Fresh right-index gallery (prints 13–24, strong), same finger, 3 touches:
best scores 9 (probe 21), 0 (probe 9, floor trip), 11 (probe 19, one short of
12). Minutiae QUANTITY is fine both sides; MATCHED PAIRS are few — sets don't
correspond. Gallery pollution is NOT the (only) cause. Two sub-findings:
(a) near-misses (11 vs 12) on strong probes → single captures land just
short; micro-placement variance across captures would likely clear it;
(b) weak probes (≤12, 18% of touches) burn whole attempts via the ticket-20
verify passthrough, and libfprint forbids verify-side retry_scan (triggers
deactivate — ticket 19 finding 1), so the retry must live INSIDE the driver.

## Experiment 2 (driver): best-of-N capture selection in verify mode

BLOCKED WITH PROOF (implementer, core state-machine trace): libfprint verify
is single-shot — withholding `image_captured` strands the core in CAPTURE
with no edge to a fresh scan (`fpi-image-device.c` has no
CAPTURE→AWAIT_FINGER_ON edge; `retry_scan` in verify deactivates). Cross-SSM
best-of-N would hang every held-back attempt. Intra-SSM re-read (second 0x20
without the UP pair) may return stale frames — unproven, parked, NOT attempted.
No code changed. Lesson: retry policy truly lives in libfprint here; the
driver gets one capture per attempt, period.

## Experiment 2bis (driver parameter): enrollment coverage 8 → 12 prints

Same-finger near-misses (11 vs 12, strong probe vs strong gallery) say
coverage, not quality, caps the max: verify compares against ALL gallery
prints, so more placement variants directly raise per-touch best. One line:
`dev_class->nr_enroll_stages = 8 → 12` (`goodix5e0a.c`, 511 precedent uses 20;
floor 12 and all enroll logic untouched) + the two Python pins asserting `8`
(`test_m2_driver_refactoring.py:47`, `test_f23_pam_reliability.py:23`).
"8/8 stages" language in closed tickets is history, not a frozen count (frozen
is deadlock-free completion). Upstream-clean: standard driver parameter.
Needs re-enroll (12 presses) to take effect.
Predicted: first-attempt best rises (more variants to match against).
Falsify: no gain with 12 strong prints → pipeline/exposure A/B next (gain
1.0 vs 2.5 rematch on the clean gallery, one variable).

## Experiment 2bis build record (2026-09-05, review APPROVE)

One line `nr_enroll_stages 8→12` + two pin literals + test-name/docstring
rename (`test_enroll_stage_count_is_12`); mock `range(1,9)` loops ruled LEAVE
(self-consistent mocks, no driver assert — follow-up only if end-to-end
fidelity to 12 is wanted). Patch regen `bcbb6183…` synced + pins rolled.
Needs re-enroll (12 presses) to take effect.

(Superseded record: Experiment 2's original best-of-N verify design was blocked
with proof above — withholding `image_captured` strands the core in CAPTURE.
Retained for the reasoning record, do not implement.)

## Upstream note

Reliability evidence (same-finger match rate across reboots/suspends) doubles
as the hardware proof UPSTREAM.md §1/HACKING.md will demand. Keep the
journals; no extra runs needed beyond Experiments 1–2.
