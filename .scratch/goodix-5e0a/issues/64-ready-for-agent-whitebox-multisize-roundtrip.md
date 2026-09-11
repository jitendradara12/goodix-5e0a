# 64 — WhiteBox non-32B round-trip coverage (16/48/64B)

**What to do:**
In `experiments/goodix_whitebox.py:194-198` and
`tests/tier1_feature/test_f28_whitebox.py:test_c`: extend round-trip
coverage beyond 32B to 16/48/64B with expected total lengths (80/112/128B).
Code claims the general formula `16 + ceil((len+1)/16)*16 + 32` but never
exercises the PKCS7 edge (48B → extra padding block → 112B total).

**Do not relitigate:**
- 32B KAT + `CANONICAL_PSK` round-trip stay pinned. This ticket adds sizes
  only; no behavior change (~6 lines).
- Provisioning safety (no-auto-erase, IAP-gated `0xe0`) untouched.

**Source:** /tmp/libfprint `whitebox_crack.py:178-186` (round-trip loop
over `[16,32,48,64]`). Hermetic, no hardware/Windows needed.

**Status:** ready-for-agent

**Revert note (2026-09-11):** prior two-hash port attempt discarded as buggy —
`experiments/goodix_whitebox.py` is still single-hash and fails the KAT
(prefix matches, ct/HMAC don't). Retry from scratch from
`/tmp/libfprint/RE_WHITEBOX_EXACT.md` + `whitebox_encrypt.py`; line refs below
assume the corrected module.

**Acceptance:**
- Round-trips for 16/48/64B pass with expected total lengths
  (80/112/128B); 32B KAT unaffected.
- `test_f28` green.
