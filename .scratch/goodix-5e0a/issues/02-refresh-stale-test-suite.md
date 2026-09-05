# 02 — Refresh the stale test suite

**What to build:** Tier 1–5 assert the proven hardware behavior instead of idealized guesses, so the suite can actually gate tickets 01–07. Known staleness: the vtable test expects a `process_frame` wiring the driver deliberately does not use (it uses raw-frame processing by design), and full-tier discovery fails to import while single-file runs pass.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Every tier runs to completion from its documented runner invocation with zero loader/import errors.
- [x] Assertions match proven behavior (raw-frame pipeline; NOP silence-is-success; real command numbers) — no test contradicts an on-wire verified fact.
- [x] Suite fails if the NOP-timeout-aborts-activation behavior ever returns (regression coverage for ticket 01).

## Portability follow-up (2026-09-05, `agent/muse-repo-improvements`)
- The "done" above held only on the author's machine: 61 hardcoded
  `/home/sastauser` + `/tmp` paths made tier 1 fail 5+45 on a fresh clone.
  Fixed via `tests/repo_paths.py`; environment-gated tests (build tree,
  NixOS flake, NBIS fixture/harness, nix tools) now skip with reasons.
  Suite is 385/385 green hermetically (`bash tests/run_all_tests.sh`).
- Added F25 patch/source sync test: new-file sections must reconstruct
  `libfprint-driver/` byte-for-byte; `goodixtls.h`, `goodix511.h`,
  `goodix_proto.c` verified byte-identical to upstream `c343b69`.
