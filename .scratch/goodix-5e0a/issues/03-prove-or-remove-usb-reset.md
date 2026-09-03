# 03 — Prove or remove the USB reset

**What to build:** Certainty about whether the patch-added USB device reset at open time wedges the MCU. Neither upstream nor the Python reference resets.

**Blocked by:** 01 — Flush-tolerant NOP (deeper behavior is unobservable until activation passes NOP).

**Status:** ready-for-agent

Verdict so far (2026-09-03, Python probes): reset is HARMLESS on the basic path —
`reset → (True, 2048)`, chip-ID, OTP and firmware reads succeed back-to-back every
run, and activation now passes NOP through register-write with zero journal errors.
Demoted from prime suspect for whole-channel deafness.

Remaining (narrowed): aborted TLS sessions poison subsequent inits — after killing
a session mid-flight, the next init spins forever in the drain/early-handshake
reads while basic commands still work. That is a TLS-teardown problem, not a
reset problem; pursue it under ticket 04 (MCU-side session teardown) and 07
(consecutive-run stability), not here.

- [ ] Repeated open/RESET/basic-command cycles show no reset-correlated failures (already observed; formalize with a bounded loop).
- [ ] If any reset-correlated failure is found, remove the reset with rationale; otherwise keep with an evidence comment.
- [ ] Consecutive activations show no reset-correlated failures.
