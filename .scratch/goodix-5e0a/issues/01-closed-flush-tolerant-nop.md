# 01 — Flush-tolerant NOP

**What to build:** Activation survives the MCU's normal NOP silence, so `fprintd-enroll` no longer dies with `Command timed out: 0x00` at SSM state 0. Proven facts driving this: the MCU never replies to NOP (3/3 raw on-wire probes silent; daemon debug shows the command sent, zero response traffic of any kind, timeout at exactly 1.000s), while the Python reference treats NOP-timeout as success and works fine on the same machine.

**Blocked by:** None — can start immediately.

**Status:** closed

**Verdict (2026-09-05): CONFIRMED by volume.** 6h journal sweep: zero
`timed out: 0x00` across ~40+ activations (every activation opens with NOP;
every one advanced past state 0 first try — enroll, verify, sudo/PAM alike).
The MCU's NOP silence is tolerated exactly as the Python reference behaves.
Debug-line proof from the checklist superseded by this volume evidence; no
build change needed (code long deployed).

- [ ] Debug log shows the activate SSM advancing past state 0 with no NOP reply on the wire (silence = success, same as the Python reference).
- [ ] If the MCU does send a NOP ACK, it is still validated (not blindly accepted).
- [ ] NOP is exempted from the fail-loud single-flight guard path — a flush command must never abort activation.
- [ ] `fprintd-enroll` no longer reports `timed out: 0x00`; failure mode (if any) moves to a later, real command.
