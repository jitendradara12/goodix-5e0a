# 81: Enrollment-Side Device-vs-Offline Comparison

**What to build:** An offline enrollment-side comparison, with no driver
change first. Ticket 80 reached its contact ceiling before the
`residual_range`-among-matchable claim could be tested: four-touch live
enrollment still returned `add_res=131`, while the contact gate never reached
`active(>30)>2000`. The next question is why the device enrollment flow can
produce a usable enrollment where one offline live burst cannot.

**Blocked by:** 80 (closed 2026-09-15 — inconclusive-because-contact-ceiling;
the prescribed fuller-contact gate was not reached; successor lane is
enrollment-side).

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Preserve frame provenance: use independently captured bursts identified
  as the same finger, and record each prefix, frame order, capture output, and
  SHA-256. Do not treat a post-overwrite PGM as the earlier attempt.
- [ ] Extend the offline harness only as needed to enroll distinct frames from
  multiple bursts (not the same four frames cycled by `live8`). Compare the
  existing one-burst 4-touch path with combined independent-burst inputs,
  recording every `add_res`, stitched count, progress, pre-enroll quality,
  packed template size, self-match, and impostor/blank/noise rejects.
- [ ] Keep the positive dense control in every run: `add_res=0`, stitched
  progress through completion, a non-degenerate template, self-match 100,
  and negative rejects intact. Keep the enrollment floor unchanged.
- [ ] Compare only one enrollment-side variable per branch: first touch count
  across independent presses; only if that is insufficient, isolate shaping or
  stitching-threshold behavior. No residual-range ranking or minutiae-floor
  change is allowed in this ticket.
- [ ] Conclude only `confirmed`, `falsified`, or
  `inconclusive-because-[flaw]`, with one next experiment. Do not wire a
  driver rank until an offline enrollment-side branch first produces
  `add_res=0` and genuine own-template matches with controls intact.

## Known baseline

- Ticket-79/80 single-burst live inputs: `add_res=131` on every input,
  `stitched=0`, `1443B` degenerate template, and no self-match; dense control
  produced an approximately `22.8KB` stitched template and self-match 100.
- Ticket-79 `live8` repeated the same four press frames and still failed. It
  is not evidence for independent touch-count coverage.
- Ticket-80 third attempt PGM hashes and the exact capture output are in
  `80-closed-fuller-contact-retest.md`; the second attempt's PGM bytes were
  overwritten, so only its pasted capture output is usable.

## Predicted signatures

- **Touch-count explanation confirmed:** each isolated burst remains
  `add_res=131`, but a combined set of independent same-finger bursts begins
  stitching and yields a non-degenerate template with genuine matches;
  controls remain rejected.
- **Touch-count explanation falsified:** combined independent bursts still
  return `131/0` while dense control remains healthy. The next single branch
  is device/offline enroll-time shaping comparison, not a rank or floor
  change.
- **Inconclusive-because-[flaw]:** frame provenance is mixed/unknown, the DLL
  or template path is unavailable, or the controls are polluted by
  post-enroll quality state.

## Guardrails

- Offline first; no deployment or driver wiring in this ticket.
- Keep `GOODIX_5E0A_ENROLL_MIN_MINUTIAE=16`, the device enrollment stages,
  and the ticket-76 rank interface unchanged.
- Cite command output and file bytes. Treat post-enroll `q/ov` columns as
  state-polluted metadata; trust pre-enroll values and match outcomes.
