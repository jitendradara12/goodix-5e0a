# 30 — Free error when no callback is installed (from ticket 28 review note)

**What to build:** In `goodix_receive_done` (`libfprint-driver/goodix.c`),
the non-early path (`ack||reply` true) with `callback==NULL` and a non-NULL
error leaks the error (e.g. a command sent with NULL callback that times
out). Free it there. One variable only — the 28 fix (early-return branch)
already landed; this is its mirror image on the other branch.

**Blocked by:** None. Leak-only: no behavior change possible (no callback
exists to observe the error either way).

**Status:** closed

**Verdict (2026-09-05): CONFIRMED by review + passive journals.** Full suite
green; evening journals (dozens of activations, cancels, re-claims across
pids 24936/54384/54384/12250) show zero crashes, zero double-free signatures,
zero new lines attributable to the change. Nothing observable could change
(no callback exists on the freed path) and nothing did.

## Build record (2026-09-05, review APPROVE)

Mirror-image else-free; all 6 call sites enumerated, no reuse; mutually
exclusive with 28's early-return free (no double-free). Patch regen
`fb439ee9…` (with 29) synced + pins rolled. Confirms via suite-green +
passive journals (nothing observable can change); rides 29's deploy.

## Careful points for the implementer

- Only free when `callback==NULL` (when a callback runs, ownership transfers
  to it — do not touch that path).
- Re-check the 6 `goodix_receive_done` call sites: any caller passing an
  error it reuses afterward must be found first (none known — verify).
- Confirm: full suite green + everyday-use journals show no new lines. No
  dedicated hardware run needed (nothing observable can change); deploy rides
  the next scheduled deploy and confirms passively.

## Predicted signatures

- Confirm: builds clean, suite green, passive journals identical.
- Falsify: any double-free crash → revert immediately.
