# 62 — WhiteBox decrypt hardening (ct block guard, dead check, hex error)

**What to fix:**
In `experiments/goodix_whitebox.py:115-141` `sec_white_decrypt`:
- Add `len(ct) % 16 != 0 → ValueError` before decrypt (truncated/tampered
  blobs currently fall through to a `cryptography` exception).
- Delete dead `134-135` (`if prefix != encrypted[:16]` — always false,
  prefix was sliced from `encrypted` on line 120).
- Include hex in prefix error (`expected {hex}, got {hex}`), not the
  generic `"Prefix does not match derived prefix"`.

**Do not relitigate:**
- PORT-NOTES whitebox KAT (second-hash `hash2`, `WB_CONSTANT
  5cba6e25819518de2d53e96dc0347ab0`, 96B layout, no-auto-erase) stays as-is.
- Tickets 26/37/44: `bb020001 = SHA256(psk)`, cold `0xe4` latch, `0xe0`
  IAP-gated provisioning. This ticket is decrypt-error paths only.

**Source:** /tmp/libfprint `whitebox_crack.py:113,121` (short + `%16`
guards), `whitebox_encrypt.py:128` (hex prefix error). Behavior on valid
inputs identical; invalid inputs fail fast with actionable `ValueError`.

**Status:** ready-for-hardware-verify

**Acceptance:**
- `python3 experiments/goodix_whitebox.py` KAT + 32B round-trip still pass.
- `sec_white_decrypt(KAT[:-1])` and bit-flipped ct raise `ValueError` with
  actionable message (not a `cryptography` traceback).
- `python3 -m unittest tests.tier1_feature.test_f28_whitebox` green.
