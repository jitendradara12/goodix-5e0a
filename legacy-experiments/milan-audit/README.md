# Milan evidence audit, 2026-10-18

Runs the checked-in x86-64 engine under Unicorn on ARM or x86 hosts. No USB,
fprintd, Windows installation, root access, or deployed driver is involved.
The inputs recovered from Git are **synthetic patterns and their template**.
The archived Windows driver is inspected in memory for direct call targets;
it is neither installed nor executed.

From the repository root:

```sh
uv venv /tmp/goodix-milan-audit
uv pip install --python /tmp/goodix-milan-audit/bin/python -r legacy-experiments/milan-audit/requirements.txt
/tmp/goodix-milan-audit/bin/python legacy-experiments/milan-audit/run.py --out /tmp/milan-audit.json
```

`results.json` records the completed run against repository commit
`5bfb69da63201030844ea49f4d4c43961609672b`. The DLL SHA is checked before any
binary-specific addresses are used. A shallow clone needs the parent of
`e6f67c7` in its local Git history.

The runner checks:

- Regeneration of both historical fixtures produces byte-identical files.
- Saved ticket-72 quality/overlap and successful self-match results reproduce.
- Signed mismatch scores and engine errors collapse to the same public `pts=0`.
- Deleting a matched template frees the allocation retained by the DLL for study.
- Vendor preprocessing rejects an uncalibrated call, then runs successfully
  after synthetic flat-field initialization.
- Archived Windows code contains direct calls to the calibration and preprocessing exports.
- The current and proposed filters' interior sinusoidal frequency responses.

The corrected preprocessor call uses the recovered enrollment-purpose flag
and disables the optional feature output with NULL. Guards check input/output
buffers. Its output establishes execution and a scoped ABI contract, not a
production integration contract. `quality=100` on the sine input is also not
a fingerprint accuracy result. The initial placeholder-buffer mistake and its
correction are recorded in [PROTOTYPE.md](PROTOTYPE.md).

The emulator executes algorithm instructions. It replaces imported heap and
memset operations with explicit shims, bypasses the diagnostic logger and stack
cookie verification, and does not run DllMain. Unknown imports and instruction
limits fail the run. The exercised cases use malloc, free, and memset imports.
Free calls are recorded but guest memory remains mapped; the lifetime check
establishes the retained reference to a freed allocation, not an observed native
crash. Golden results constrain this emulator's validity to the exercised paths.

At the initial audit, no real enrollment/probe dataset was present in this
checkout or the reachable PGM/raw/capture history examined for the review.
The synthetic audit checks above are not hardware verification or a release gate.

See [the evidence review](../../docs/evidence-review-2026-10-18.md).

For the new native Linux owner check and real-capture comparison, see
[the preprocessing prototype](PROTOTYPE.md).

The native production-loader controls passed on `sastapc` on 2026-10-18;
see [native results](linux-results.json). They exactly match the emulated
controls apart from the backend label. The first bundle's missing C source
was repaired, and a fresh corrected-bundle extraction also passed. Use
`make_bundle.py` for future handoffs so required sources are checked.

## ptrip7's subsequently supplied real captures

The updated issue #12 ZIP now supplies 213 real raw frames, labels, journal,
and the contributor's replay source. The original replay reproduces exactly;
the labeled band-pass baseline reproduces the journal's 5/10 genuine and 0/10
wrong-finger matches. Enrollment-only FPN correction reaches 7/10 genuine
and 0/10 wrong-finger matches. The vendor path with an explicitly estimated
background matches 0/10; there is still no measured vendor calibration.

See [the real-capture report](../../docs/ptrip7-replay-2026-10-18.md),
[native replay runner](ptrip7_replay.py), and [saved results](ptrip7-results/summary.json).
The source archives and raw biometric images stay in a locally excluded
dataset directory; the result artifacts contain hashes/metrics, not templates
or image pixels. No driver was installed and no public message was posted.

The Windows initialization/cache path is now recovered. See
[calibration acquisition](../../docs/windows-calibration-2026-10-18.md) and
[the standalone export helper](../../tools/CALIBRATION.md). The actual archived
reader/CRC checks and native saved-state replay checks pass; an affected-unit
cache export is still needed.
