# 12 — Sampled touch-gated loop (02/80) + full-size frames

**What to build:** The scan loop exactly as the vendor driver runs it:
sample `0x32` DOWN repeatedly; `80`-replies mean idle (re-issue silently),
`02`-replies mean finger present (capture immediately). Full enroll off
touch-gated stages, double verify. No blocking-forever waits, no blind
polling, no fixed sleeps.

**Blocked by:** None — ready now. (Supersedes 10 and 11, which used the
wrong gating model and wrong payload. Transport/activation/TLS frozen.)

**Status:** in-progress

## Decisive evidence (USBPcap ground truth, do not re-litigate)

- DOWN (35B, `1c 01…` skeleton + six adaptive `80 XX` slots) returns
  QUICKLY either way: `80…`-status reply (~34ms, idle/finger-off, often
  doubled with no image after) vs `02…`-status reply (finger-present →
  image within ~1ms). Touch anchors (17:27:30 dup-fail, 17:27:57 start,
  17:28:05 success) confirm mapping; enroll state itself is host-side (no
  field changes at anchors). Gating rule: issue DOWN → `80` ⇒ re-issue
  silently; `02` ⇒ send image. No reply-timeout semantics needed.
- Image payload `05 00 b0 00 b2 00 b0 00 b1 00` verbatim every time; reply
  B2 pack10638 (~10560px plaintext). Our 7684B replies for any payload are
  a degraded-session symptom (see open question below), not a payload
  debate — payload is settled.
- Loop order per image (reply-driven gaps: ACKs ~1ms, image ~20ms, D34
  ~500ms): `ae(00 01 00)` → `32` → [`80`⇒re-DOWN | `02`⇒`20`] → B2 →
  `34(UP-pair, identical)` → `ae` → `34(same UP)` → D34 → next. `d6(00 00)`
  at session start only (expect `ffff`). Deactivate: `0x60 01 00`.
- DOWN/UP starting tables: S12 / U01 from the capture briefs; keep the
  pair locked per image; re-issue same table on `80` first version.
- Geometry: re-derive live-column map empirically from first 10638B frames
  (candidates 80x132 / 88x120 / 64x165); keep corr metrics; minutiae
  acceptance picks the winner. Do NOT assume 80x64 or 4k+3.

## Open question inside this ticket (not a blocker to start)

Our sessions yield 7684B replies where Windows' yield 10638B. Both warm
captures start mid-provisioned-session, so the provisioning bytes (boot
`fetch psk → start tls → download chip config` per the pipeline strings)
were never captured and cold capture is unavailable on that box. If the
loop above runs correctly yet replies stay 7684B zeros, the remaining
suspects in order are: (a) missing boot-time config download (blob bytes
unknown — do NOT re-upload the APP_10019-era 52XD blob blindly; extract a
candidate from `drivers/wbdi.dll` data sections first); (b) OTP-conditioned
writes (read OTP via `a6`, compare against pipeline expectations);
(c) PSK slot (handshake completes under d853 but the data session may bind
a different slot — the read-back key is on file). Report which was tried
with journal evidence either way.

## Acceptance criteria (deployed driver, hardware only)

- [ ] Hands-off: `80`-samples cycling silently, zero retries, zero churn.
- [ ] Touch: `02` within seconds, stages advance, full enroll completes.
- [ ] Content frames with decaying correlation + minutiae counts > 0.
- [ ] `fprintd-verify` matches twice, no restart. Then 07 runs.

## Rollback criteria

- Timeouts/unknown-errors/session loops → revert, paste journal + poll
  bytes. Do not stack fixes.
