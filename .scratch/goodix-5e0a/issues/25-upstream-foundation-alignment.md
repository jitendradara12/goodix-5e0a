# 25 — Upstream foundation alignment (docs, specs, and merge readiness)

**What to build:** Make the documentation layer describe the final upstream
goal from the start — a host-image driver with hardware touch gating and
host matching — with all early hypotheses marked superseded or falsified,
all contradictions corrected, and the merge checklist filed as the
definition of done.

**Blocked by:** None (documentation only; no driver edits in this ticket).

**Status:** ready-for-agent

## Problem Statement

A newcomer reading the repository meets two drivers: the progress notes
describe a fragile prototype that hangs on empty air and templates noise,
while the hardware journals describe full-frame captures gated on real
touch and matched on the host. Early gap lists prescribe changes that would
revert proven work, test totals disagree between notes, and the upstream
path exists only as hints. Without a trusted starting document, every
future agent must re-derive what is frozen, what was falsified, and what
the merge actually requires.

## Solution

Publish a small trusted foundation: a project glossary, three decision
records, a final-goal-first architecture note, an upstream roadmap, and a
gap adjudication — then keep them current as the merge workfront moves.
Future work cites the foundation instead of re-deriving it.

## User Stories

1. As a new contributor, I want one glossary for sensor terms, so that I never confuse the wire frame with the processed image.
2. As a new contributor, I want the driver classification stated first, so that I never design on-chip storage the firmware lacks.
3. As a driver author, I want the frozen behaviors listed, so that I never re-litigate proven transport or gating without new hardware evidence.
4. As a driver author, I want retired approaches named, so that I never reimplement a falsified decoder or payload.
5. As a driver author, I want the active workfront listed, so that I pick up only unblocked merge work.
6. As a reviewer, I want each early gap adjudicated, so that I can see at a glance what is fixed, retired, or still open.
7. As a reviewer, I want known documentation traps corrected in one place, so that wrong command numbers and geometries stop spreading.
8. As an enrolled user, I want enrollment to advance only on real touch, so that empty air never creates a gallery entry.
9. As an enrolled user, I want faint touches retried with guidance, so that weak captures never pollute my gallery.
10. As an enrolled user, I want verification to match on a firm first touch, so that login feels instant.
11. As an enrolled user, I want repeated verifications to succeed without daemon restarts, so that daily auth is reliable.
12. As a PAM user, I want exclusive device claims to release cleanly, so that sudo never reports an already-claimed device.
13. As a PAM user, I want cancelled prompts to free the sensor immediately, so that the next authentication starts fresh.
14. As a laptop owner, I want suspend and resume to re-initialize the sensor, so that the first login after sleep works.
15. As a laptop owner, I want stalled hardware to fail gracefully, so that a login prompt never hangs indefinitely.
16. As a downstream packager, I want the driver behind a clean build option, so that single-driver and all-driver builds both link.
17. As a downstream packager, I want device ids generated into system rules, so that no hand-written rules drift.
18. As an upstream maintainer, I want replay traces for every core operation, so that I can test without owning the laptop.
19. As an upstream maintainer, I want warning-clean builds under the project style checker, so that CI stays green.
20. As an upstream maintainer, I want a plain-language derivation statement, so that I can confirm the work is clean-room.
21. As a future agent, I want evidence ranked above prose, so that journals and traces settle every dispute.

## Implementation Decisions

- The driver is classified as a host-image device with press scan type,
  eight enrollment stages, and host minutiae matching; no on-chip storage,
  enroll, or match interfaces exist.
- The touch gate is sampled channel energy with silent re-polling on idle;
  the status byte is never a gate input and no blocking wait is assumed.
- The wire layout is eighty padded blocks plus a footer decoded in order
  into the natural raster; contiguous-dump and transposed-column decoders
  are recorded as falsified alternatives.
- The image module flattens local offset, maps contrast directly around
  mid-gray at unity gain, upscales twofold with inverted capacitive
  polarity, and tags explicit high resolution; the enrollment floor admits
  only sufficiently detailed touches.
- The transport module owns flush-tolerant startup, reset, identification,
  OTP priming, provisioning, chip enable, and the encrypted session; the
  activation and scan state machines are separate modules with a
  concurrency guard and joint timer cleanup on teardown.
- The test harness keeps its synthetic protocol mocks for regression but
  they are explicitly not verification evidence and not upstream replay
  coverage; the new replay module records real USB traffic per core
  operation.
- Packaging keeps the downstream overlay intact while the upstream
  submission is split into logical commits for transport, driver,
  recordings, and device-table wiring.
- The foundation documents are the glossary, three decision records
  (host matching, wire layout, sampled gating), the architecture note, the
  upstream roadmap, and this ticket; the old research-only gap list stays
  immutable history with a pointer to its adjudication.

## Testing Decisions

- A good test asserts external behavior (journal signatures, match
  outcomes, claim release, teardown silence) rather than internal byte
  tables; a test that passes while hardware loops is a bad test.
- The highest test seam is USB-trace replay driving full
  activate-scan-deactivate cycles; module seams beneath it cover framing,
  decode geometry, and image normalization.
- Prior art: the per-tier hermetic suites for regression shape, the
  hardware verify protocol (hands-off control plus press-hold with pasted
  journal output) for verdicts, and the upstream capture harness as the
  target replay pattern.
- Documentation changes in this ticket need no hardware run; every claim
  about behavior cites the ticket or journal that proved it.

## Out of Scope

- Any driver source change (tickets 21–24 own the hygiene workfront).
- Any new USB capture or hardware verification run.
- Recording replay traces (a later ticket owns the harness and recordings).
- Opening the upstream merge request.

## Further Notes

- Foundation files: project glossary at the repo root, decision records
  under the architecture-docs directory, architecture and upstream notes
  alongside progress notes, gap adjudication alongside the frozen gap
  list, and this ticket in the file-based issue tracker.
- Keep exactly one active workfront list; when tickets 19–24 move, update
  the architecture note in the same change.
- If upstream guidance shifts (style checker, harness layout, secret
  policy), the upstream roadmap note is updated first and the workfront
  re-derived from it.
