# 57 — Dynamic FDT thresholds via FDT_MANUAL (port from goodixtls RE)

**What to do:**
In `libfprint-driver/goodix5e0a.{c,h}` (scan path only): add a
`SCAN_5E0A_READ_FDT_BASE` step that sends FDT_MANUAL (cmd `0x36`,
`[0x0d, 0x01, DACx8, 0x00x4]`) and parses 6x u16LE raw base from response
bytes `[4..15]`, then builds the 35B DOWN/UP payloads per the formula in
`goodix5e0a.h` (DOWN `((raw>>1)<<8)|0x80`, UP `(((raw>>1)+delta)<<8)|0x80`,
prefixes `0x1c/0x0e/0x0d`). Keep static S12/retry/U01 as fallback on
short/error response. Read DAC `[2..9]` from live OTP (`0xa6`) instead of
hardcoded `b0/b2/b0/b1` when OTP data is available.

**Do not relitigate:**
- Tickets 12/13: channel-energy gating, 50-100ms sampled re-poll, UP
  sequence `34(noreply)→ae→34(reply)→FALSE` stay as-is.
- Ticket 45: `0xa2` never sent. Ticket 50: `0xd4` timeout is success.
- Header reference block (prefix defines + formula) is already in place;
  this ticket is the scan-SSM wiring only.

**Source:** /tmp/libfprint `RE_FDT_PAYLOAD_DETAIL.md` (SwitchToFdtMode
@0x1800585c4, CalcFdtDownBase @0x1800632a0, 3x `gf_get_fdtbase`), driver
`SCAN_READ_FDT_BASE` + `build_fdt_payload()` + `on_fdt_manual_response()`.
Their DAC `a6/a7/a6/a7` vs ours `b0/b2/b0/b1` proves DAC is per-unit.

**Status:** closed (verdict: falsified / rejected)

**Acceptance:**
- Cold + warm claims on the ChicagoH unit show dynamic thresholds in
  `fp_dbg` matching `((raw>>1)<<8)|0x80` for the live base; static fallback
  logged when used.
- 60s hands-off air-silence + press-hold run per AGENTS.md verify protocol;
  no regression vs static tables (latency, false DOWN on air, missed touch).
- Falsify condition: dynamic thresholds cause air-trigger or miss where
  static S12 succeeds → keep static, close as falsified with journal.

## Fix (2026-09-10, hardware-caught contamination)
- Symptom: second of two back-to-back claims (no lift between) waited
  ~13s for DOWN although the finger was down the whole time; unlock
  landed on lift+retouch. Journal: claim-2 MANUAL base read low
  (00d6-00f7/ch) vs claim-1 air base (0150-019b/ch) — the 0x36 read
  sampled the still-held finger and tuned DOWN to it.
- Fix: air reference (`fdt_air_ref`, adopted on clean reads); a fresh
  base deviating > 0x30 on any channel (finger shifts every channel
  >= 0x6b) is rejected to static S12 fallback without touching the
  reference. First read ever is adopted (nothing better). Safe direction:
  worst case is static tables, i.e. pre-ticket behavior.
- Regression test: `test_f57::test_g` pins reject path + threshold.

## Final Audit & Closure (2026-09-11)
- Verdict: CLOSED (falsified / rejected).
- Findings:
  1. Sending `0x36` (FDT_MANUAL) dynamically at scan start creates an incurable hardware race condition: if the user's finger is already touching or resting near the sensor, `0x36` samples the finger as "baseline air".
  2. The resulting `FDT_DOWN` threshold is tuned to the pressed finger, completely eliminating any capacitive delta. The sensor fails to detect touch, hanging for ~13 seconds until the finger is lifted or the client times out.
  3. Static tables `goodix_5e0a_down_s12` and `goodix_5e0a_up_u01` were extracted from clean Windows captures on ChicagoH and are hardware-proven over 60s+ hands-off tests with zero air-triggers and zero touch misses.
  4. Falsify condition met: dynamic baseline calculation rejected; static S12/U01 tables remain authoritative.
