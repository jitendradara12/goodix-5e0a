# 93: Explain pre-touch activation time

**What to build:** A measurement of where the ~28ms between park reuse and finger-wait goes, plus a written conclusion; no code change in this ticket.

**Blocked by:** None.
**Status:** closed — confirmed software/offline analysis; not hardware-verified
**Owns:** An offline timing-analysis tool over existing journals; nothing else.

- [x] Attribute the reuse-to-finger-wait window across commands and waits from saved journals; include per-command estimates and margins.
- [x] Compare cold and warm paths to bound the possible win from further optimization.
- [x] Close with an explicit recommendation: either name a worthwhile target for a follow-up ticket or state that measured gains are not worth the risk.

**Evidence:** Confirm with consistent command timing across multiple claims; falsify if the window is dominated by unlogged transport waits (then recommend logging, not tuning).
**Done:** Report committed; no timing, ordering or protocol changes made here.


## Software closure, 2026-09-17

- Report: `.scratch/goodix-5e0a/93-activation-latency-report.md`.
- New offline tool: `scripts/analyze_activation_timing.py`.
- Tests: `python3 -m unittest tests.tier1_feature.test_f93_activation_timing -v`, 11 passed.
- Seven saved journals parsed into ten explicit-action pre-touch intervals: seven cold-start, one TTL-expired full activation, two actual parked reuse.
- Actual reuse to first 0x32 send marker: 27.182–27.616 ms. Candidate freshness precedes actual reuse by 0.547–0.573 ms and is reported separately. Chip-enable and D6 envelopes account for 97.45–97.56% of the post-reuse interval; only 0.037–0.075 ms lies outside the three command envelopes.
- Cold action start to send: 429.046–431.343 ms. Warm action start to send: 27.771–28.176 ms. These are journal envelopes, not USB readiness or measured physical-touch latency. Transport/device costs inside them cannot be separated with these logs.
- Recommendation: measured remaining gains do not justify changing protocol timing/order. If internal transport costs must be explained, add monotonic command/transfer logging in a separate follow-up before tuning.
- Single next experiment: analyze ticket 95's combined saved batch journal with this tool. Confirm repeated complete actual-reuse command envelopes; falsify if complete timing puts most of the delay outside them; missing markers are inconclusive. Details and configurable CLI are in the report.
- No driver, existing script, master runner, or other ticket edits by this task. No privileged operations, hardware claims, suspend, staging, or commits. The original committed-report criterion is deferred to the parent integration session because delegation explicitly prohibited commits. Software deliverables are in the shared working tree.
