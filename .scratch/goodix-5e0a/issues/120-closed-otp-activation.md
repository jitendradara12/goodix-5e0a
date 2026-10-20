# 120 — Reach OTP on cold activation and preserve verified DAC words

**Status:** closed

**Verdict:** confirmed on deployed driver `ee3ecdf` (maintainer unit).

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

## Deployed-driver result

Guided no-flags run `8f72a31af505296c` at `ee3ecdf2a8b26469665155e67b8ce1afa9ed1b82`, 2026-10-20 18:31:53–18:33:24 IST, confirmed the corrected cold path:
- `OTP DAC calibration: 0x0b0 0x0b2 0x0b0 0x0b1`, followed by `dynamic config applied: standard unit`.
- Hands off 18:31:58 +20s stayed silent; holding 18:32:19 +20s advanced once. Twelve-touch enrollment completed.
- Genuine 5/5 matched; wrong finger 5/5 rejected.
- Storage isolated, original print counts 7/0/7, `store_unchanged: true`, `restored: true`.
- Driver SHA-256: `b056b17a9d9e8fe834a24e64e619f23a3dfb86886004ffe8625f1a8d963208eb`.
- Report: `/var/tmp/goodix-5e0a-reports/goodix-test-8f72a31af505296c.zip`, SHA-256 `16275805ebbf8342f28a5a93e19c9833ebb9d52738e4ce9e0b99cd4ea8429e97`.

The full required Linux suite passed (two existing missing-image-fixture skips), including all 14 native lifecycle/activation cases. Both GitHub checks passed at the tested revision. The independent reviewer rechecked this fix and independently passed F117/F90. This closure only updates documentation; the deployed driver sources are unchanged.

Single next experiment: Jet-Soup's standard no-flags run on the corrected activation path, with the same confirm/falsify signatures above. This remains a unit-specific follow-up; no universal hardware claim is made.
