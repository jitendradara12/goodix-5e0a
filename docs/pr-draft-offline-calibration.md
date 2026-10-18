# Add reproducible Milan replay and Windows calibration export

Issue #12 reports successful capture/enrollment with unreliable matching on
other units. Add offline tools that reproduce the contributor's replay and
journal results, preserve raw engine diagnostics, and extract the Windows
calibration records needed to test the vendor preprocessor. The installed
driver, normalization and 12-touch enrollment behavior are unchanged.

The labeled band-pass baseline reproduces 5/10 genuine and 0/10 wrong-finger
matches. Enrollment-only fixed-pattern correction reaches 7/10 genuine and
0/10 wrong-finger matches on the same saved captures. Vendor preprocessing
with an estimated background does not demonstrate a fix. Real same-unit
Windows calibration is the next input; no release-level accuracy claim is made.

Validation: all seven contributor replay rows reproduce exactly; all 213
saved normalized images match byte for byte; labeled baseline winners,
decisions and match scores reproduce the journal. Native synthetic controls
and calibration-state save/load replay pass. Seven standalone cache-export
tests pass, and the actual archived Windows reader/CRC agree with the
exporter's cache format and reject corrupt inputs. Source archives, raw
biometrics and templates are excluded from the proposed artifacts.

This is a local draft only. No PR, issue comment or push has been published.
