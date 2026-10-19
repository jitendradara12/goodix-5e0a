# 115: Linux-only PSK recovery and separate Jet-Soup capture candidate

**Status:** closed (verdict: maintainer confirmed, Jet-Soup candidate falsified on hardware; successor: 116)

## Scope

Integrate Jet-Soup's Linux-only PSK recovery from issue #12, hardening record
discovery, Python compatibility, verification and output publication. Prefer
the Linux route in setup documentation while retaining the DPAPI fallback.
Keep their wire-only capture settings in an explicit temporary test candidate;
do not globally replace settings already working on the owner's/ptrip7's units.

Contributor source: https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6263682686

## Software evidence

- Patch reviewed against `690cc75`; import failure reproduced with Python
  3.12, payload-only overread rejection reproduced, and forced-write failure
  shown to delete the previous key in the original contribution.
- Recovery now derives the candidate offset from bounded DPAPI parsing,
  reuses the existing whitebox decryptor and requires a same-sensor SHA-256.
- Output is published with mode 0600, atomic replacement/no-clobber behavior,
  no default key printing and cleanup on failure. Python vendor annotations
  are deferred to support the documented Python 3.10+ route.
- The temporary hardware runner reuses the earlier isolation/recovery design
  with the merged matching pipeline. Current settings are the default; the
  separate Jet-Soup patch changes only capture data and preserves both payload
  definitions. Normal driver sources and matching policy are unchanged.

## Hardware verification runs

1. **Maintainer Regression (`--capture-settings current` at 09e78f1):**
   - 5/5 genuine matches, 5/5 wrong-finger rejections.
   - Quiet hands-off (20s), single holding advance, storage isolation and restoration verified.
   - Live PSK extraction verified against sensor hash.
   - Verdict: **Confirmed** for baseline driver.

2. **Jet-Soup Candidate Hardware Run (`--capture-settings jet-soup` at 186f32d):**
   - Test bundle: `goodix-test-0f643487c98e906e.zip` (Fedora 44, USB passthrough).
   - Hands-off: silent (pass).
   - Holding: single advance (pass).
   - Enrollment: completed 12 touches in 9s without finger releases.
   - Genuine verification: **0/5 matched (falsified)**.
   - Wrong-finger verification: 0/5 matched (rejected).
   - Driver log: every verify frame scored `quality=0 overlap=21..36 range=1300..1620`.

## Reverse engineering findings & root-cause verdict

Disassembly of Windows binaries (`wbdi.dll`, `GoodixEngineAdapter.dll`, `goodix.dat`):
1. **The bandpass filter works on Jet-Soup's hardware:** Replaying Jet-Soup's 24 raw frame captures with native $80\times64$ transpose through the Milan engine matched genuine probes 4 out of 4 times (scores 45, 93, 53, 45).
2. **Four driver flaws caused the 0/5 live failure:**
   - `goodix_5e0a_down_s12` was left with maintainer DACs `[0xb0, 0xb2, 0xb0, 0xb1]`, saturating Jet-Soup's readout amplifiers and reporting `energy=1800` on air.
   - Driver contact gating (`best_active < 64`) was blind because air ADC is ~1400 (> 30), so `best_active` was always 5120. `best_quality` was never checked before submitting.
   - Enrollment lacked finger release enforcement, advancing 4 stages in 963 ms on empty air, packing a template that was 75% air noise.
   - Verify probes were rapid tap lift-off frames (quality decaying from 20 to 0) matching against air noise.

Successor: **116: Milan quality-floor contact gating, finger release enforcement, and FDT DOWN calibration**.
