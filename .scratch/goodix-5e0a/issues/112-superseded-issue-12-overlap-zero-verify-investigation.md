# 112: Investigate Issue #12 Headline Symptom: Overlap=0 Leading to Verify No-Match

**What to build/investigate:**
Investigate why Issue #12 reporter experiences consistent `verify-no-match` despite successful enrollment (`overlap=0`, `quality=0` during verification candidate ranking):
1. In Ticket 111, `legacy-experiments/capture_live_burst.py` was hardened with `--psk` and `/etc/libfprint/goodix-5e0a.psk` support, giving users a working, reproducible frame capture tool using their machine's decrypted key.
2. Request a 4-frame live burst (`capture_live_burst.py --out-prefix user_burst`) from the reporter to analyze raw sensor dynamic range, ambient noise floor, and contrast on their hardware.
3. Compare the reporter's raw sensor PGM histograms against canonical benchmarks (`legacy-experiments/fingerprint.pgm`, `clear-0.pgm`).
4. Validate whether the standard 3x3 local-mean residual normalization (midpoint 128, gain 1.5 calibrated in Ticket 104) suppresses minutiae on their specific glass/sensor revision, or whether candidate ranking score thresholds / Milan `identifyImage` reject the candidate due to spatial displacement or lack of template auto-learning (Tickets 105–108).

**Blocked by:** User hardware burst capture using hardened `capture_live_burst.py`.

**Status:** superseded

**Successor:** [113: Vendor preprocessing and real-capture comparison](113-in-progress-vendor-preprocessing-prototype.md).

## Context & Rationale

- In Issue #12, the user reported:
  > "Device is enrolled successfully (12 touches), but verification always fails: 'verify-no-match (retry=0)'. Candidate logs show quality=0, overlap=0."
- Contrast gain was calibrated to `1.5f` in Ticket 104 (`GOODIX_5E0A_CONTRAST_GAIN` at `goodix5e0a.h:47`), and manual clamp gating was removed.
- Quality and overlap rank verification candidates (`goodix5e0a.c` lines 1214–1428), while `identifyImage` (lines 1117, 1486) performs final gate matching.
- Now that `capture_live_burst.py` can be executed by end users with their own extracted PSK, raw PGM frames can be analyzed offline against the Milan engine.

## Predicted Signatures

- **Confirm (Sensor calibration / contrast mismatch):**
  - Reporter's burst PGMs show mean pixel intensity or dynamic range significantly different from dev unit (e.g. baseline clear frame average far outside nominal range).
  - Normalization outputs saturated or suppressed ridge contrasts under 1.5 gain.
- **Falsify (Template geometry / learning issue):**
  - Offline matching with Milan engine against user-provided burst frames shows high quality scores when aligned, indicating the issue is gallery coverage or alignment rather than raw sensor frame acquisition.

## Evidence correction, 2026-10-18

The plan and blocker above predate the reporter's real-driver dumps and offline
experiments. Preserve them as history; do not ask the reporter to repeat the
failed standalone capture procedure as the next step. High quality does not
establish gallery coverage, so the original falsify branch is not a valid
discriminator.

[Offline evidence review](../../../docs/evidence-review-2026-10-18.md) and
[reproducible runner](../../../legacy-experiments/milan-audit/README.md) now establish:

- The early Milan accuracy fixtures are generated patterns, byte-identical to
  the saved generator, not two real fingers.
- `pts=0` conflates negative match scores and engine errors; it does not prove
  the repeatedly cited raw score -7 or insufficient feature extraction.
- Archived Windows code calls calibration/preprocessing APIs absent from the
  Linux bridge. The engine executes a calibrated preprocessing smoke test.
- The 3x3 residual strongly attenuates the newly reported 8–10-pixel ridge scale.
- Auto-study after the existing verify wrapper would encounter freed template
  state; that proposed sequence needs redesign and is not the present fix.

No deployed-driver hardware run occurred. This ticket stays ready-for-agent.
The single next experiment and revised confirm/falsify predictions are in the
review: reconstruct the remaining vendor ABI/calibration contract and compare
final matching on held-out touches, rather than treating quality as proof.

## Superseded after the real-capture replay, 2026-10-18

The original capture blocker and overlap-only investigation plan are obsolete.
ptrip7's updated ZIP supplies the raw frames, labeled touches and replay code.
The report now reproduces the contributor's published rows and exact labeled
journal baseline. FPN correction improves labeled matching from 5/10 to 7/10,
with 0/10 wrong-finger matches; vendor preprocessing with an estimated
background is not a demonstrated fix. Continued calibration/integration work
belongs to successor 113. This supersedes the earlier ready-for-agent note;
it is not a hardware-verified closure.

[Real-capture report](../../../docs/ptrip7-replay-2026-10-18.md).
