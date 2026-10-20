# 120 — Reach OTP on cold activation and preserve verified DAC words

**Status:** ready-for-hardware-verify

**Verdict:** inconclusive-because-current-driver-hardware-run-pending.

The original PR #15 cold ladder ran NOP → RESET → firmware check, bypassing the new OTP state entirely. Both earlier code reviews missed this; green helper tests and old no-flags hardware reports do not establish automatic calibration.

Changes:
- Cold activation now jumps from RESET to READ_OTP. Warm activation still skips OTP and reuses this boot's packets; a failed warm handshake takes the full ladder and re-reads OTP.
- The native harness compiles the entire production driver against real libfprint SSM, mocks device I/O, and asserts both known profiles reach OTP and upload the selected config. It also covers warm reuse/fallback, malformed reads, and OTP transport failure before TLS.
- A live read-only OTP check found owner flags `OTP[0x13] & 0x0f = 0x0c`, primary/secondary `b0 b2 b0 b1`. Treating the flags as ninth DAC bits produced `01b0 01b2 00b0 00b1`, contradicting the verified Windows wire words `00b0 00b2 00b0 00b1`. Decode the redundant channel bytes without guessing extra bits. A production-C regression fixture checks this observation.

Software evidence: the new native cold-start test failed on the original source with `otp_reads=0`, expected 1. The live-flags fixture likewise failed the old decoder with 432/434 rather than 176/178. These are behavior tests, not callback-presence assertions.

Read-only hardware check: exactly 64 OTP bytes received; only calibration fields were reported. fprintd was stopped briefly and its original active state restored. No fingerprint or matching test was performed in this check.

Single next experiment: deploy the current candidate using `bash tools/test-hardware.sh` on the maintainer unit.
- **Confirm:** journal includes `OTP DAC calibration: 0x0b0 0x0b2 0x0b0 0x0b1` before TLS/config upload; hands-off + timestamp 20s stays silent, holding + timestamp 20s advances once, 12-touch enrollment completes, 5/5 genuine and 5/5 wrong-finger rejections, isolated store and unchanged original contents after restoration.
- **Falsify:** OTP is skipped, wrong DAC/config is selected, hands-off captures or repeated hold advances occur, genuine verification fails, a wrong finger matches, or original storage changes.
- **Inconclusive:** build/service/client failure or interrupted phases prevent those measurements; record the flaw and review that bundle before requesting another run.

Jet-Soup's final no-flags run remains a follow-up on the corrected activation path; earlier no-flags results must not be relabeled as proof of that path.
