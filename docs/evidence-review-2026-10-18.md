# Project evidence review — 2026-10-18

Reviewed commit: `5bfb69da63201030844ea49f4d4c43961609672b`.
Purpose: determine which explanations for issue #12 survive the code,
development history, archived binaries, and reproducible offline experiments.
No production driver changes or hardware runs were performed.

## Decision

Prioritize a correctly calibrated vendor preprocessing path through Milan.
Use the existing normalization and contributor band-pass implementation as
controls. Preserve the current 64x80 geometry and 12-touch enrollment during
this comparison. Do not start auto-learning integration or change matching
acceptance criteria to address issue #12.

This recommendation now has executable evidence: the archived Windows driver
calls the vendor calibration/preprocessing APIs, and the checked-in engine can
execute those APIs under emulation. Whether this restores reliable matching on
the reporters' actual captures remains an empirical question.

## 1. The early Milan accuracy benchmark used generated images

**Confirmed.** `gen_dense_live.py` generates the two historical
`live_dense_pad*.pgm` files. Regenerating seeds 67 and 68 produces byte-identical
files recovered from `e6f67c7^`:

| File | SHA-256 |
| --- | --- |
| `live_dense_pad.pgm` | `d9f411180017c91a131eee16b80fc1473e7cc54fb09c3e8bd7dd171c8ae8fc58` |
| `live_dense_pad_seed68.pgm` | `e7346cfa9761348c274d65d6444b194200eceffa6229cd12092b973c19004359` |

Ticket 72 labels these as captured frames and different fingers. Its five
positive probes are the original generated image and small perturbations of
it. Ticket 77's offline gallery likewise uses these two patterns. Their results
prove useful engine-call, separation-of-patterns, and serialization properties.
They do not measure cross-touch genuine matching or human false acceptance.

Ticket 67 explicitly describes the synthetic provenance; it was lost in later
interpretations. Separate hardware matches in tickets 74/77/83/104 remain
recorded hardware evidence. This finding does not invalidate those matches.

## 2. The fixed filter is poorly matched to the newly reported ridge scale

**Confirmed mathematically; causal importance supported by contributor tests.**
The generator uses a ridge period of 5 pixels and Gaussian noise sigma 22.
Issue #12 reports approximately 8–10 pixel ridge periods and strong fixed-pattern
noise. The archived synthetic baseline did not exercise that regime.

For an interior axis-aligned sinusoid of angular frequency w, the 3x3 box mean
has response `(1 + 2*cos(w))/3`. The current residual retains its complement.
For the contributor's band-pass control, multiply the 3x3 mean response by
`1 - box_mean_11_response`:

| Ridge period | Current residual amplitude retained | Band-pass retained |
| --- | ---: | ---: |
| 5 pixels | 46.1% | 49.0% |
| 8 pixels | 19.5% | 98.1% |
| 10 pixels | 12.7% | 95.2% |

These values precede gain, clipping, and target-standard-deviation scaling;
finite image borders and ridge orientation also affect the actual output.
At a 10-pixel period the band-pass passes about 7.48 times as much ridge
amplitude before scaling. A fixed gain increase does not selectively recover
the attenuated ridge signal over pixel noise.

The original reporter's 0/96 -> 61/96 -> 75/96 offline results are consistent
with this mechanism. They were reported by the contributor, not rerun here:
[corrected experiment](https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6239570800).
The later contributor reports a different capture/preprocessing combination;
that variability still requires separate controls:
[latest report](https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6248526501).

## 3. `pts=0` does not diagnose extraction failure or a particular negative score

**The unique-diagnosis claim is falsified.** `goodix_milan_verify_image` ignores
`identifyImage`'s return code and clamps negative scores to zero. Both verify
and identify use a positive score plus a valid matched index as the wrapper's
acceptance condition; there is no separate wrapper threshold of 50 today.

Executing the real engine against its archived synthetic template reproduces:

| Probe | Quality / overlap | Engine return | Signed score | Public pts |
| --- | --- | --- | ---: | ---: |
| Enrolled pattern | 18 / 98 | 0 | 100 | 100 |
| Different generated pattern | 19 / 100 | 0 | -4 | 0 |
| Flat | 0 / 0 | 0x83 | 0 | 0 |
| White noise | 0 / 0 | 0x83 | 0 | 0 |
| Unrelated 10-pixel sine | 100 / 81 | 0 | -4 | 0 |

Thus the existing public log conflates an engine error with a processed
rejection. Historical `pts=0` alone cannot establish the claimed raw `-7` code,
insufficient minutiae, missing coverage, or incorrect normalization.
This audit does not assign undocumented semantic meanings to individual
negative codes beyond the outcomes actually observed.

High `getQuality` also does not establish matching correspondence: the sine
control scores quality 100 and still rejects. Changing quality gating or
lowering an imagined score-50 threshold cannot resolve this ambiguity.

## 4. The vendor calibration/preprocessing path is present and executable

**Confirmed for archived code and an emulated ABI smoke test.** Linux resolves
the matching exports and calls `ppp_param_init(10)`, but never invokes the
calibration/preprocessor exports. `ppp_param_init` sets a sensor parameter
profile; it does not initialize per-pixel calibration.

The archived `wbdi.dll` contains verified direct calls:

| Call RVA | Destination |
| --- | --- |
| 0x36e64 | `preprocess_init_calidata` at 0xc8450 |
| 0x36f0a | `preprocess_load_calidata` at 0xc84f0 |
| 0x371be | `preprocessor_init` at 0xc8d80 |
| 0x31466 | `preprocessor` at 0xc8b10 |

Its `AlgPreprocessInit` code at 0x7c574 attempts to load saved calibration,
falls back to defaults, initializes with a pixel buffer, and saves calibration.
This establishes a vendor code path, not that every device/session takes every
branch. The DLL can bootstrap from defaults and an initialization frame; the
claim that OTP or Windows files are necessarily the only calibration source
is unsupported by this code.

In `GoodixEngineAdapter.dll`, emulated preprocessing returns 0x80 before
calibration. After default initialization plus a synthetic constant 1500
16-bit calibration frame, initialization returns 0 and processing a synthetic
10-pixel sine returns 0 with a nonconstant 8-bit result. The same result has
quality 100 / overlap 91. This is execution evidence, not a fingerprint match.

Partial ABI established for this binary:

- Calibration initializer reads a raw uint16 buffer pointer at +0x18 and
  dimensions at +0x24/+0x28 from its input record.
- `preprocessor` takes source and destination image records with data at +0;
  byte counts at +0x14 must be populated. Source payload is uint16 data;
  destination payload is an allocated uint8 buffer.
- The fifth argument receives two uint32 quality/coverage outputs.

Follow-up prototype work recovered the remaining records: argument two points
to an enrollment-purpose flag; argument three is an optional 0x4c98-byte feature
output and can be NULL. The initial smoke test's 4096-byte placeholder for that
output was too small and could be overrun in the emulated heap. The corrected
audit uses NULL, reproduces the same image statistics, and checks buffer guards.
The initial call was never part of the shipped driver. See
[the prototype and correction](../legacy-experiments/milan-audit/PROTOTYPE.md).

The Linux `has_calibration = FALSE` flag refers to the shared sensor scan
calibration branch. Setting it to TRUE is not equivalent to invoking Milan's
preprocessor, and the 5e0a has its own scan path. It is not the integration fix.

## 5. Auto-learning cannot be bolted on after the existing verify wrapper

**Confirmed lifetime incompatibility; no current-driver study bug claimed.**
After a positive match, the engine stores a pointer to the inner unpacked
template at RVA 0x135c48. `templateStudy` reads that pointer. The current wrapper
then calls `templateDelete` before returning to the driver.

The emulated lifetime check records both template allocations being freed
while the last-match global still references the freed inner allocation.
Consequently tickets 106/107 need an atomic match -> study -> pack -> delete
transaction with a retained template and engine lock. Simply calling study
after today's verify function would use expired state. A packed blob is not
that live template handle. Persistence through fprintd remains a separate
unverified requirement in ticket 107.

No study call exists in the current production path, so this is a flaw in the
proposed integration sequence, not the cause of today's genuine misses.

## 6. Linux-only key extraction needs transport integration, not new cryptography

**Confirmed for the existing cryptographic implementation; hardware extraction
remains contributor evidence.** `goodix_whitebox.py` already implements the
reported two-hash AES/HMAC construction and the 0xbb010003 record layout.
Its known-answer check and 16/32/48/64-byte round trips pass. The five existing
whitebox unit tests also pass in this review.

The new part in the latest report is accessing the stored record by offset on
that device. Turn this into a bounded read-only extractor with record validation
and device-hash verification. A round trip alone does not establish that the
record is readable on every firmware. Keep this work separate from matching;
the original #12 reporter already completed TLS using a verified key.

## Reproduction and boundaries

[Runner and instructions](../legacy-experiments/milan-audit/README.md),
[machine-readable results](../legacy-experiments/milan-audit/results.json).
The engine SHA-256 is
`9990ab24af01b8c5c575c73cf7a95a7d675655adfb4183b6c030de2912ec23de`.
The emulator reproduces ticket 72's exact 18/98 and 19/100 quality results,
successful score-100 self-match, and mismatch/blank/noise rejection controls.
It omits DllMain and bypasses logging/cookie verification. These are scoped
offline checks, not complete Windows-process or Linux-loader validation.

The reachable Git history contains the two synthetic PGM files and their
template; the real captures cited under /tmp and /dev/shm were not committed.
This checkout contains no actual probe dataset. The archived calibration module
does include a 10,240-byte background image, but its existence does not supply
labeled enrollment and probe touches. No hardware run was attempted on this
ARM macOS host, so there is no new deployed-driver verification claim.

## Single next experiment

Complete the vendor preprocessor's auxiliary-record and calibration-frame
contract from Windows call sites, then compare current filtering, contributor
band-pass, and vendor preprocessing on the same labeled raw capture set.
Keep geometry, enrollment count, matching engine and decision rule fixed.
Preserve signed engine return/score/index in the offline output.

The purpose flag and optional-output contract have since been implemented in
the offline prototype. Its full synthetic enrollment/verify controls pass under
emulation and through the production native Linux loader on `sastapc`. Native
and emulated results are identical apart from the backend label. A fresh
corrected-bundle extraction also passed after fixing an omitted C source file.
The immediate next checkpoint is a valid same-unit calibration and affected-unit
capture set. The laptop's saved old striped captures and generated fixtures do
not supply that dataset.

Predictions:

- **Confirm preprocessing integration as the missing step:** vendor path
  initializes on the unit's own valid calibration frame and improves genuine
  held-out-touch matching over controls while rejecting wrong-finger/blank/noise
  inputs. Final hardware deployment must reproduce that behavior.
- **Falsify that implementation as a fix:** correctly initialized vendor output
  does not improve final matching, corrupts expected geometry, or worsens
  wrong-finger outcomes. A higher quality score alone is not confirmation.
- **Inconclusive-because-invalid-ABI-or-calibration:** unsupported metadata,
  unverified calibration source, missing independent probes, or engine errors
  prevent attribution. Do not reinterpret these as coverage failure.

For the eventual deployed-driver run, save `hands off` and timestamp for 20s
(predicted silence, no capture cycles), then `holding` and timestamp for 20s
(predicted capture/advance and explicit final match outcome). Conclude confirmed,
falsified, or inconclusive-because-[flaw], with one next experiment.

## Subsequent real captures supersede the missing-dataset checkpoint

ptrip7 supplied and then updated the archive with replay source. The complete
comparison is in [the real-capture report](ptrip7-replay-2026-10-18.md).
All seven published replay rows reproduce, all 213 saved normalized images
match byte for byte, and the labeled baseline exactly matches the journal.
Enrollment-only FPN correction improves genuine-touch matches from 5/10 to
7/10, with 0/10 wrong-finger matches for both. The vendor path with an
estimated background reaches only 0/10 on available labeled genuine touches;
there is still no measured same-unit vendor calibration. Software execution
therefore remains distinct from a demonstrated vendor matching fix.
