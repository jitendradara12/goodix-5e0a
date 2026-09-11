# 63 — Pin intermediate WhiteBox vectors (hash1/prefix/hash2/key)

**What to do:**
In `experiments/goodix_whitebox.py:188-198` (`__main__` KAT) and/or
`tests/tier1_feature/test_f28_whitebox.py:test_b`: assert the intermediate
vectors from /tmp, not just the final 96B:
- `hash1 = ec35ae3a…088f0`, `prefix = …cc0`, `hash2 = b7e7f234…ad7f`,
  `key = b7e7f234…acad2`, `IV = prefix` (`RE_WHITEBOX_EXACT.md:131-139`).
- `test_b` currently asserts only lengths (16/48/32), never values.

**Do not relitigate:**
- Final KAT (`32 zeros → ec35ae3a…6a756c5` 96B) and second-hash derivation
  stay authoritative (PORT-NOTES). This ticket adds intermediate pins only.
- No driver change; hermetic asserts (~10 lines).

**Source:** /tmp/libfprint `RE_WHITEBOX_EXACT.md:131-139`,
`whitebox_encrypt.py:40-46`. Recomputed `hash1`/`hash2` from the algorithm
byte-match the doc. This is the exact regression class PORT-NOTES cites
(single-hash variant passes structure, fails values).

**Status:** ready-for-hardware-verify

**Acceptance:**
- `python3 experiments/goodix_whitebox.py` asserts `hash1/prefix/hash2/key`
  hex; swapping in the old single-hash derivation fails.
- `test_f28` green.
