# 95: Integrate results and prepare one final hardware batch

**What to build:** One short checklist using the tools from 89–94, so the user tests the merged work once at the end.

**Blocked by:** User's final hardware batch only. Software work in 89–94 is complete; ticket 90's disposal acceptance deviation remains documented.
**Status:** ready-for-hardware-verify
**Owns:** Integration report and batch checklist; no driver changes.

- [x] Record the combined software suite and unresolved defects, reusing the prior passing integration run rather than rerunning it for documentation-only changes.
- [x] Provide configurable commands for labeled matching samples, resume recovery, activation timing and idle resource sampling. Keep privileged operations, fingerprint claims and suspend user-only.
- [x] Reuse existing tools, isolate idle sampling from claims, and save evidence together. No per-ticket user checkpoints or hardcoded finger required.

**Evidence:** Apply each ticket's confirm/falsify signatures to the final evidence. Missing or interrupted samples are inconclusive, not failures or passes.
**Done:** Integration checks pass and the checklist is ready. Then mark ready-for-hardware-verify; the user's eventual run records hardware verdicts without blocking earlier implementation tickets.

## Integration handoff, 2026-09-17

Checklist: `scripts/README-final-batch.md`. No new tool or driver change.

Prior integration evidence, not a run by this documentation task: ticket 90 records
`bash tests/run_all_tests.sh` with 368 passed, zero skipped. Tickets 89–94 are
closed for their stated software scopes; closure does not imply hardware success.
Ticket 90 explicitly falsifies unconditional idle parked-TLS disposal because
public idle suspend bypasses the driver hooks. Green characterization is not a
fix, and health-probe ACK does not establish safe encrypted recovery. This defect
remains unresolved.

The user runs one batch at the end with configurable enrollment slot, anonymous
labels and output directory. Each claim has isolated client/journal evidence and
an explicit done/cancelled/incomplete disposition. Saved files feed ticket 89's
collector/report and ticket 93's timing analyzer. Optional ticket 94 sampling runs
separately from claims and sleep; non-root PSS denial is acceptable incomplete
evidence, not a reason to add privilege.

The recovery scenario requires a real pre-sleep park, manual desktop suspend,
pre/post timestamps and PID/start identity, then a post-resume claim without any
restart in between. `verify-ticket88.sh` cannot serve as the post-resume probe
because it restarts fprintd. Disposal and operational recovery have separate
confirm/falsify/inconclusive signatures in the checklist. Unknown historical
results stay unknown. Prior ticket 87/88 safety phases use the already-verified
exception; no repeated mandatory hold phases or per-ticket checkpoints.

Validation performed here: read closed tickets 89–94 and relevant 87/88 evidence,
reviewed existing verification source and CLI definitions, ran the three offline
analysis tools' top-level `--help`, and passed `bash -n` for all eight Markdown
Bash blocks individually and combined. Shell blocks were syntax-checked only.
No hardware, sudo, claims, suspend, rebuild, deployment or commits were executed.
Cleanup instructions use noninteractive sudo with an explicit failure warning;
unsetting manager debug environment does not restore the running daemon's state.

## Final integration review

The orchestrator reran the local suite: 368 passed, zero skipped. A clean
validation clone at `/tmp/opencode/goodix-clean-ziq7v9ax` passed 366 tests,
with two explicit skips for absent `clear-0.pgm` and `fingerprint.pgm` images.
Both native lanes ran. This used the existing Nix store and host environment,
not a fresh machine or hosted CI run. Cleanup fixtures passed all 59 mocked
runs there. Logs: `/tmp/opencode/clean-checkout-suite.log`,
`/tmp/opencode/clean-tier5.log`, `/tmp/opencode/clean-checkout-cleanup.log`.

Review fixes: cleanup fixtures use the platform temp directory; the integrated
runner clears inherited suspend binaries and makes the shared native skip mode
apply to suspend tests unless explicitly overridden. CI explicitly requires both
native lanes and runs the cleanup fixture. No driver, patch or service changes.

Hardware verdict remains pending. Single next experiment: the user runs the
checklist once on the unchanged deployed driver and reviews the saved evidence.
