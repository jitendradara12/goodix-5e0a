# 02 — Refresh the stale test suite

**What to build:** Tier 1–5 assert the proven hardware behavior instead of idealized guesses, so the suite can actually gate tickets 01–07. Known staleness: the vtable test expects a `process_frame` wiring the driver deliberately does not use (it uses raw-frame processing by design), and full-tier discovery fails to import while single-file runs pass.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Every tier runs to completion from its documented runner invocation with zero loader/import errors.
- [x] Assertions match proven behavior (raw-frame pipeline; NOP silence-is-success; real command numbers) — no test contradicts an on-wire verified fact.
- [x] Suite fails if the NOP-timeout-aborts-activation behavior ever returns (regression coverage for ticket 01).
