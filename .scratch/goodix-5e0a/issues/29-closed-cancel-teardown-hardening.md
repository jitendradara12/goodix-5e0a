# 29 — Cancel-path teardown hardening (from ticket 19 analysis R1+R5)

**What to build:** Two same-lane cancel-teardown hardenings in
`libfprint-driver/goodix5e0a.c`, both proven no-ops on success paths:

1. **Disarm-before-free reorder** in `goodix5e0a_deactivate`: destroy
   `down_timeout` FIRST, then `goodix_reset_state` (disarms `priv`
   callback/user_data so late USB replies take the early-return path), and
   only then `fpi_ssm_free(scan_ssm)`. Today the SSM is freed while `priv`
   still points at it, so a reply in flight lands on freed memory (R1 UAF).
   New order: `session_started=FALSE` → timeout destroy+NULL → reset_state →
   ssm free+NULL → shutdown_tls → stop_read_loop → complete. Nothing else
   reordered; no logic added.
2. **CANCELLED branch** in `goodix5e0a_on_fdt_down_reply`: today's
   `G_IO_ERROR_CANCELLED` sub-branch returns silently (parks the SSM forever
   AND leaks the error). Change to `fpi_ssm_mark_failed (ssm, err)` like every
   other error branch in that function.

**Blocked by:** None. Analysis (not hardware) is the evidence; hardware
confirm is "no delta".

**Status:** closed

**Verdict (2026-09-05 20:04–20:05 IST, pid 12250, patch `fb439ee9`, debug on):
CONFIRMED.** Cancel test: `stopping it` → `Deactivating image device` →
`Stopping read loop` → `Image device deactivation completed`, same second;
immediate re-claim + `verify-match`. Teardown runs the new order cleanly;
no delta on success paths (frames/scores identical across the evening).
The 19 wedge runs never reached this teardown (no `Deactivating` line) —
separate daemon-side question, owned by 19.

## Build record (2026-09-05, review APPROVE)

Reorder is pure move; disarm-then-free closes the late-reply UAF window;
CANCELLED→mark_failed fixes park+leak. Patch regen `fb439ee9…` (with 30,
rationale below) synced + pins rolled.

## Combined confirm with 30 (diligence note)

30 is provably unobservable on exercised paths (frees otherwise-leaked errors
nothing observes). One deploy + single-cancel→reclaim test confirms 29; any
behavior delta falsifies 29's no-op proofs (30 cannot cause one) → revert 29
first, investigate.

## Predicted signatures

- Confirm: builds clean, suite green, cancel test (single Ctrl+C →
  immediate re-claim) works, normal runs byte-identical. Any behavior delta
  on success paths falsifies the no-op proofs → revert.
- Falsify: any new hang/crash/timeout vs current build → revert both,
  investigate.

## Acceptance

Deploy + single-cancel→reclaim test (the discriminating run) + agent-pulled
journal; conclude only confirmed / falsified /
inconclusive-because-[flaw] + single next experiment.
