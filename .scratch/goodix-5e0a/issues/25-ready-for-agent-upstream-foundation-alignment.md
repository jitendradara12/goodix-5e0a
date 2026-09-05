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

Publish a small trusted foundation: a final-goal-first architecture note,
an upstream roadmap, and a gap adjudication — then keep them current as the
merge workfront moves. Future work cites the foundation instead of
re-deriving it.

## User Stories

1. As a driver author, I want frozen behaviors, retired approaches, and each
   early gap adjudicated in one place, so that I never re-litigate proven
   transport, reimplement a falsified decoder, or quote a wrong command
   byte or geometry.
2. As an enrolled user, I want enrollment to advance only on real touch and
   faint touches retried with guidance, so that empty air and weak captures
   never create a gallery entry.
3. As an enrolled user, I want verification to match on a firm first touch
   and repeat without daemon restarts, so that login feels instant and
   daily auth is reliable.
4. As a PAM user, I want exclusive device claims to release cleanly and
   cancelled prompts to free the sensor immediately, so that sudo never
   reports an already-claimed device.
5. As a laptop owner, I want suspend/resume to re-initialize the sensor and
   stalled hardware to fail gracefully, so that post-sleep login works and
   a prompt never hangs indefinitely.
6. As a downstream packager, I want clean build flavors and generated
   device ids and system rules, so that single-driver and all-driver builds
   link and no hand-written rules drift.
7. As an upstream maintainer, I want replay traces for every core operation,
   warning-clean builds under the project style checker, and a plain-language
   clean-room derivation statement, so that I can test without owning the
   laptop and confirm the work merges cleanly.
8. As a future agent, I want evidence ranked above prose, so that journals
   and traces settle every dispute.

## Implementation Decisions

- The driver is a host-image device with press scan type, eight enrollment
  stages, and host minutiae matching; match threshold twelve with the
  in-tree floor of ten; no on-chip storage, enroll, or match exists.
- The touch gate is sampled channel energy with silent re-polling on idle;
  the status byte is never a gate input and no blocking wait is assumed.
- The wire layout is eighty padded blocks plus a footer decoded in order
  into the native raster; contiguous-dump and transposed-column decoders
  are recorded as falsified alternatives.
- The image module flattens local offset, maps contrast directly around
  mid-gray at unity gain, upscales twofold with inverted capacitive
  polarity, and tags explicit high resolution; the enrollment floor admits
  only sufficiently detailed touches.
- The transport module owns flush-tolerant startup through the encrypted
  session; the activation and scan state machines are separate modules with
  a concurrency guard and joint timer cleanup on teardown.
- The test harness keeps its synthetic protocol mocks for regression but
  they are explicitly not verification evidence and not upstream replay
  coverage; the replay module records real USB traffic per core operation.
- Packaging keeps the downstream overlay intact while the upstream
  submission is split into logical commits for transport, driver,
  recordings, and device-table wiring.
- The foundation documents are the architecture note, the upstream roadmap,
  the gap adjudication, and this ticket; the old research-only gap list
  stays immutable history with a pointer to its adjudication.

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

- Foundation files: the architecture and upstream notes alongside the
  progress notes, the gap adjudication alongside the frozen gap list, and
  this ticket in the file-based issue tracker.
- Keep exactly one active workfront list; when tickets 19–24 and 26 move, update
  the architecture note in the same change.
- If upstream guidance shifts (style checker, harness layout, secret
  policy), the upstream roadmap note is updated first and the workfront
  re-derived from it.
