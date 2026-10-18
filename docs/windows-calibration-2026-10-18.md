# Windows calibration acquisition and the next input

**The next missing input is specific:** the affected laptop's Windows
calibration cache, normally `C:\ProgramData\Goodix\goodix.dat`.
Use the new read-only helper to export only `ImageBase` and `CaliData` from it.
No additional finger captures, parameter tuning, driver installation or
Windows re-enrollment is needed for this attempt.

This is a recovery path established for the archived `wbdi.dll`, SHA-256
`ce541d886983e628914aa7317f90711a363a5008ce250bceb40b64de9a45ce92`.
It is not yet proof that the contributor's installed Windows driver wrote
that cache or uses exactly this format. An absent file or rejected format is
useful information; do not fabricate a replacement calibration.

## What the archived Windows code actually does

- `UpdateAllBase` and `_UpdateImageBase` obtain a sensor image via a hardware
  callback, compare it with the previous base through
  `ImageisTouchedByFingerUnify`, and conditionally copy the accepted image into
  the logic context's image-base buffer at `context + 0x128`.
- At RVA `0x892bc`, `_UpdateImageBase` calls `AlgPreprocessInit` (`0x7c574`).
  That function passes this image-base pointer to `PreprocessorInit` at
  `0x7c72d`; the wrapper calls `preprocessor_init` at `0x371be`.
- `AlgPreprocessInit` also has a conditional saved-calibration path:
  `_LogicLoadBaseFromFile` -> `ReadBaseFromFile` -> the `CaliData` record ->
  `preprocess_load_calidata`. Defaults are used if loading fails. It then
  initializes from the image base and serializes the resulting state.
- The file path builder combines the Windows system-drive letter,
  `:\ProgramData\`, and the UTF-16 string `Goodix\goodix.dat` at RVA
  `0x1982d0`. The cache contains named records `Otp`, `FdtBase`, `NavBase`,
  `ImageBase`, and `CaliData`.
- The Windows loader checks the cached sensor identity against its current
  sensor and checks the image-base byte count. Our offline exporter cannot
  independently establish sensor identity or freshness; the contributor must
  confirm the cache comes from the laptop that produced the dataset.

The device capture wrapper supports different request flags and sensor DAC
values. In the reviewed F-series branch a nonzero background parameter clears
bit 2 of request byte 0 (`0x01` rather than `0x05`), with DAC values supplied
from the device context. This is static code evidence, **not** a validated
recipe for changing the Linux wire configuration. Recover the existing cache
first instead of asking contributors to try a new acquisition sequence.

## Cache format and independent checks

The NLVF file is not a flat image and must not be guessed by byte offset:

| Part | Representation |
| --- | --- |
| File magic | Four bytes `NLVF` |
| Record header | 136 bytes (`0x88`) |
| Record name | 64 UTF-16LE code units, NUL-terminated; lookup is case insensitive |
| Payload length | Little-endian uint32 at header + `0x80` |
| Payload CRC | Little-endian uint32 at header + `0x84` |
| Payload | Immediately follows the header, then the next record |

The CRC is non-reflected CRC-32/MPEG-2: polynomial `0x04c11db7`, initial
`0xffffffff`, no final XOR. The actual archived function at RVA `0xc2c80`
returns `0x0376e6e7` for `123456789` and `0x494a116a` for bytes 0..255.

[calibration_contract.py](../legacy-experiments/milan-audit/calibration_contract.py)
executes the **actual Windows record reader and CRC** on an in-memory synthetic
cache. The reader agrees with the exporter on the image payload and
case-insensitive key, and rejects CRC damage, truncation and a missing key.
Only stdio, ASCII `_wcsicmp` and errno are shimmed; the record-reader and CRC
instructions are unchanged. Logger/security-cookie calls are bypassed at
this binary's verified addresses. Output buffers are guarded.

This proves agreement with the reviewed binary's record contract, not that
we have received a real Windows cache. See
[saved contract results](../legacy-experiments/milan-audit/calibration-contract-results.json).

The standalone [extractor](../tools/extract_goodix_calibration.py) requires only
Python's standard library. It validates file/record boundaries and CRCs,
rejects duplicate keys and non-12-bit/wrong-sized image bases, preserves the
source, refuses to overwrite an existing export, and exports no OTP/FDT/Nav
payloads. Tests also check PGM endian conversion and output selection.

## Replay is ready for cached calibration

The reviewed engine expects a `0x224b0` (140,464-byte) calibration state.
The offline prototype now supports the Windows sequence: sensor profile,
defaults, optional saved-state load, then initialization with the image base.
It checks state length before calling the DLL, preserves guarded input bytes,
and stops on a vendor version/CRC rejection. There is no silent fallback from
an incompatible state to a claimed calibrated result.

The native Linux check passes a generated-image state save/load round trip;
restoring the state reproduces output and full enrollment/verification results.
The native DLL rejects a wrong-size state and damaged CRC/version data.
These are software checks using synthetic inputs, not new real-finger results.
See [native results](../legacy-experiments/milan-audit/linux-calibration-state-results.json).

After extracting a contributor's export ZIP into a directory, run:

```sh
python3 legacy-experiments/milan-audit/ptrip7_replay.py \
  --dataset /path/to/ptrip7-dataset \
  --native-library /path/to/libgoodix-milan-probe.so \
  --windows-calibration /path/to/extracted-calibration-export \
  --out-dir /path/to/results
```

The extra `vendor-windows-cache` method verifies the exported file hashes and
records source/export hashes and whether saved state was loaded. Current,
band-pass and enrollment-only FPN controls remain available. A generic replay
manifest also accepts `calibration_state` alongside the raw `calibration` PGM.
Same sensor and compatible acquisition settings must still be established;
the cache alone is not a promise of improvement.

## Request to relay, not posted

Ask ptrip7 to use the prepared helper on the Windows cache from their Realme
Book Prime and return only the resulting `goodix-calibration.zip`, confirming
it is from that same laptop. If the file is missing or the tool rejects the
format, ask for that fact/error instead. Do not ask for another scan yet.

The helper's read-only command on Linux is:

```sh
python3 extract_goodix_calibration.py /path/to/windows/ProgramData/Goodix/goodix.dat \
  --out goodix-calibration.zip
```

The next experiment is still the fixed saved-capture comparison, now with an
actual Windows background/state instead of an estimated proxy. Confirm a
candidate only with improved genuine matching, preservation of baseline
successes and negative-control rejection. Valid compatible calibration with
no improvement falsifies that candidate; missing, incompatible or unbound
calibration makes attribution inconclusive. The default driver remains
unchanged, and no hardware verification or public posting has occurred.
