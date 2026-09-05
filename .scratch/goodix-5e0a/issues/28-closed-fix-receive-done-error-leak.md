# 28 — Fix bounded error leak in receive-done early return (from ticket 21 finding 3)

**What to build:** In `goodix_receive_done` (`libfprint-driver/goodix.c`),
the `!(priv->ack || priv->reply)` early return drops a passed `GError`
without freeing it. Free it on that path (no callback will ever consume it —
the return exists precisely because nobody is waiting). One variable only.

**Blocked by:** None. Split from ticket 21 (which forbids code changes).

**Status:** closed

**Verdict (2026-09-05 19:07–19:08 IST, pid 52054, patch `3c32ee68`):
CONFIRMED.** Same run as 27 (combined run): clean activations, no crashes,
no leaks observable, no behavior delta — error paths never fired on these
clean runs, as expected. Fix verified by review enumeration (all 6 call
sites, mutual exclusion with callbacks).

## Build record (2026-09-05, review APPROVE)

Early return frees non-NULL error; all 6 call sites enumerated, none reuses
the object; early-return and callback paths mutually exclusive (no
double-free). Reviewer-noted pre-existing debt (ack||reply-true +
callback==NULL + error still leaks) left untouched — future ticket if ever.
Patch regen `3c32ee68…` (with 27 above) synced + pins rolled.

## Combined confirm with 27 (diligence note)

Both fixes are proven no-ops on exercised paths (27: same bytes, free timing
only; 28: error paths never fire on clean runs) — one deploy+verify confirms
both: any behavior delta falsifies the proofs (revert both, investigate).

## Settled facts (from ticket 21, do not re-litigate)

- Leak fires only on collision/late-reply paths (a command arriving when none
  is in flight), so it is bounded, not a per-frame bleed. Fix changes no
  success-path behavior by construction.
- Careful point for the implementer: the error parameter is `GError *`
  (single pointer, callee-side); verify no caller uses the error object after
  the call before freeing (the early return means no callback runs, so
  nothing downstream can observe it — but check the timeout and collision
  call sites explicitly).

## Predicted signatures

- Confirm: driver builds clean, full unit suite green, hardware verify run
  byte-identical (success paths untouched), journal shows no new lines.
- Falsify: any double-free crash or behavior delta → revert immediately.

## Acceptance

Standard hardware verify (deploy + hands-off 60s + verify with pasted client
lines + agent-pulled journal grep); conclude only confirmed / falsified /
inconclusive-because-[flaw] + single next experiment.
