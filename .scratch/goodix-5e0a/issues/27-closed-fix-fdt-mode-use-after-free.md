# 27 — Fix use-after-free read in FDT-mode sender (from ticket 21 finding 1)

**What to build:** In `goodix_send_mcu_switch_to_fdt_mode`
(`libfprint-driver/goodix.c`), stop calling `free_func(mode)` BEFORE passing
`mode` into `goodix_send_protocol` (which synchronously reads it in
`goodix_encode_protocol`'s `memcpy`). Pass `free_func` through to
`goodix_send_protocol` instead — exactly as the sibling FDT_UP sender
(`goodix_send_mcu_switch_to_fdt_up`) already does. One variable only.

**Blocked by:** None. Split from ticket 21 (which forbids code changes).

**Status:** closed

**Verdict (2026-09-05 19:07–19:08 IST, pid 52054, patch `3c32ee68`):
CONFIRMED.** 5 fingerprint unlock cycles: clean activations, TLS ready every
time, healthy frames (`active=5120`, `h_corr 0.906–0.966`), minutiae 9–18,
zero errors/timeouts/crashes. No behavior delta, as proven (same bytes, free
timing only).

## Build record (2026-09-05, review APPROVE)

Early `free_func(mode)` removed; send passes `free_func` through (FDT_UP
idiom). Copy-before-free proven synchronous (`goodix.c:627-630` encode then
free; `goodix_proto.c:79` memcpy inside encode). NULL callers identical
(guarded both paths). Patch regen `3c32ee68…` (with 28 below) synced + pins
rolled.

## Settled facts (from ticket 21, do not re-litigate)

- Live path `goodix5xx.c:404` passes heap `cfg.data` + real `cfg.free_fn`,
  so the early free is a genuine heap-use-after-free READ, masked in practice
  by allocator behavior (freed memory usually still mapped at memcpy time).
- All other senders pass `free_func` through; FDT-mode is the odd one out.
- No behavior change expected on any path (freed-then-read bytes are the same
  bytes when the read wins the race, which it always has so far).

## Predicted signatures

- Confirm: driver builds clean, full unit suite green, hardware verify run
  shows byte-identical activation/scan behavior (FDT modes arm as before),
  zero new journal lines (same calls, same order — only ownership timing
  changes).
- Falsify: any behavior delta → revert immediately (would mean something was
  relying on the early free, which would itself be a finding).

## Acceptance

Standard hardware verify (deploy + hands-off 60s + verify with pasted client
lines + agent-pulled journal grep); conclude only confirmed / falsified /
inconclusive-because-[flaw] + single next experiment.
