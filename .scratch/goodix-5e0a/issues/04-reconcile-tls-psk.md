# 04 — Discover the frame-data key (THE wall)

**What to build:** A clean-room decryption of a live `0x20` reply to structured
sensor bytes. Proven facts (2026-09-03, Python USB probes, no hardware damage):

- Framing is stable and parseable: every `0x20` reply is a valid pack
  (`0xb2`), valid proto (`cmd 0x20`), and exactly ONE complete TLS
  ApplicationData record (`17 03 03`, len 7744 = 7680 plaintext + explicit IV +
  MAC + pad — byte-exact fit, no slicing ambiguity).
- The record does NOT decrypt under the handshake PSK from Windows DPAPI
  (`d853…`, also in `psk.bin`): unbuffered clean-room capture yields 0 bytes
  and the server answers with a fatal (encrypted) alert on the socket.
  Handshake framing completes either way — the scripted flight dance CANNOT
  detect key disagreement, so "TLS-OK" and "upload: True" prove nothing about
  crypto (upload is plaintext).
- The device-reported read-back key (`6877…` via preset-PSk-read) makes
  sessions unstable (early stalls); untested cleanly for decrypt. It may be a
  different slot, not the data key.
- No prototype in the repo ever verified decryption output (all captured via
  an `openssl s_server`-stdout harness whose output method fails its own
  control test in this environment). Treat every historical "decrypt success"
  print as unverified.
- Leads: whitebox/PMK material in the 52xD reference flow, OTP contents,
  Windows `dpapi_*.bin` blobs, fixed-firmware-key hypothesis. Also open:
  whether the C driver's in-process handshake lands in a different (working?)
  session than the scripted Python dance — live-finger C-debug must confirm
  whether `SSL_read` succeeds per capture.

### Analysis & Resolution of the Paradox (2026-09-03):
1. **The C Driver (`libfprint-goodix`)**:
   - Uses in-process OpenSSL C API directly (`SSL_accept`, `SSL_read`) without stdout pipes.
   - Live journalctl logs during `fprintd-enroll` confirmed consecutive invocations of NBIS minutiae detection (`Failed to detect minutiae: No minutiae found`) every 2–3s.
   - If `SSL_read` had failed, `scan_on_read_img` would receive `err_from_ssl()`, mark SSM failed, and abort with an SSL error. Reaching minutiae extraction confirms that `SSL_read` returned >0 decrypted bytes.
   - The empty-air rejection gate (`active < 64 || range < 8`) in `goodix5e0a.c` properly returned a zeroed dim frame when no finger was pressed, causing NBIS to find 0 minutiae and resulting in `enroll-retry-scan`.
   - Logging added to `goodix5xx.c` (`5e0a scan_on_read_img: decrypted %u bytes from SSL_read`) and `/tmp/live_frame.raw` dump will capture the live frame on next touch.

2. **The Python Standalone Harness**:
   - Replaying a captured TLS record (`imgreq.bin`) into a separate `openssl s_server` session fails by design: TLS 1.2 CBC keys are ephemeral and derived from handshake `ClientRandom` + `ServerRandom`.
   - `s.out` inspection confirmed `0 server accepts that finished` (handshake aborted before application data).
   - In addition, standard pipe buffering in `openssl s_server` causes `stdout.read()` in Python to block or yield 0 bytes unless closed/flushed.

**Blocked by:** 01 — Flush-tolerant NOP (TLS is unreachable until activation passes the early commands).

**Status:** ready-for-agent (diagnostics armed, pending live finger press test)

- [ ] A live `0x20` reply decrypts to 7680 bytes with sensor structure (column sparsity, sane 12-bit range) — method must pass its own control test first.
- [ ] The derivation (fixed key, reported slot, OTP/whitebox-derived, or session-bound) is documented with the capture that proves it — no guessing.
- [ ] Driver and capture agree with no silent fallback; MCU-side session teardown on deactivate is defined so consecutive runs don't poison each other.
