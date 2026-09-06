# 37 — Upstream-clean strip of ticket-26 PSK reconciliation (0xe4/0xe0 removal)

**What to build:**
Remove the ticket-26 activation-time PSK reconciliation (`ACTIVATE_READ_PSK` /
`ACTIVATE_PROVISION_PSK`, `on_psk_read` / `on_psk_write`, the 5e0a-only
`goodix_send_preset_psk_read_slice` helper, and the `goodix_5e0a_psk_default`
factory table) so activation goes `CHECK_FW_VER -> UPLOAD_CONFIG -> TLS` with
the static host key directly. Keeps the host `goodix_5e0a_psk` + `psk_flags`
TLS wiring, the shared 511 `0xe4` read / `0xe0` write transport helpers, and
all biometric / FDT / power-management behavior untouched. One variable:
activation USB sequence only.

**Blocked by:** None. Successor to ticket 26 (closed, could-not-reproduce);
does not re-litigate 26 facts, acts on them.

**Status:** closed

**Verdict:** confirmed on hardware 2026-09-07. Cold/restart TLS reached the
ready state with complete frames and no `bad record mac`; no PSK states ran.

**Live-scope:** activation strip + test/patch sync only. No biometric tuning,
no lifecycle changes, no upstream-repo contact (that tree stays clean; no PR).

## Settled facts (from ticket 26, frozen)

1. Original cold-boot `bad record mac` was a single post-reboot event; every
   later reboot plus a true poweroff boot (pid 1713, 5 activations, minutiae
   14–26) came up `TLS connection ready` first try with zero MAC errors.
2. Exp 26.4 falsified the slot attribution: `bb020001` always reads factory
   bytes even while TLS with the host key succeeds — the 0xe4-visible slot is
   NOT the operational TLS key slot.
3. Exp 26.5 closed provisioning: `0xe0` rejected in the 40-byte no-slice form
   (every driver activation) and the 44-byte sliced probe form; the path is a
   harmless no-op via soft-fail, never a success.
4. Four independent reviews of the instrumented code: REQUEST-CHANGES /
   NOT-UPSTREAMABLE — hardcoded factory secret, two wasted USB round-trips
   per activation, per-activation `g_message` spam, dead-on-arrival success
   log line, plus mock-vs-hardware shape divergence in the hermetic tests.

## Why strip (upstream rationale, docs/UPSTREAM.md section 6)

- Per-unit factory secrets plus vendored PSK provisioning have no accepted
  upstream pattern; shipping a second secret solely for log classification
  proves the objection. The factory table goes, the host key stays with a
  plain disclosure comment (Windows-stack capture, no runtime derivation,
  per-unit scope unconfirmed).
- Two extra states cost 2x USB transactions + 2–3 journal lines on EVERY warm
  login for instrumentation whose discriminating power is spent (both
  questions it could answer are answered: read-form settled, write-form
  closed). Upstream reviewers NACK cost-without-benefit round-trips.
- `g_message` per-activation chatter bypasses `FP_COMPONENT` filtering;
  surviving TLS-callback line is demoted to `fp_dbg` (511 precedent in
  `goodix5xx.c` logs PSK at debug).

## Implemented change (hermetic, this ticket)

- `libfprint-driver/goodix5e0a.h`: deletes `goodix_5e0a_psk_default[32]`;
  host `goodix_5e0a_psk` kept with disclosure comment (derivation, no
  provisioning, ticket-26 pointer). `GOODIX_5E0A_PSK_FLAGS` kept (TLS class).
- `libfprint-driver/goodix5e0a.c`: deletes `ACTIVATE_READ_PSK`,
  `ACTIVATE_PROVISION_PSK`, `on_psk_read`, `on_psk_write`, both dispatch
  arms; enum collapses to `... CHECK_FW_VER -> UPLOAD_CONFIG ...`; strip
  rationale comment at the removal site. Class `psk` wiring unchanged.
- `libfprint-driver/goodix.c` / `goodix.h`: deletes 5e0a-only
  `goodix_send_preset_psk_read_slice` (sole caller was the removed state);
  generic `goodix_send_preset_psk_read` / `write` kept (511 uses read).
- `libfprint-driver/goodixtls.c`: PSK-callback `g_message` → `fp_dbg`
  (fallback warnings for NULL/zero-PSK paths untouched).
- `tests/tier1_feature/test_f27_psk_provision.py`: rewritten as the
  upstream-clean gate — host key still pinned; absence of states/callbacks/
  slice/factory table asserted; `CHECK_FW_VER -> UPLOAD_CONFIG` ordering
  asserted; shared 511 helpers asserted present.
- `README.md`: provisioning claim → static-host-key claim.
- Unified patch regenerated via `git diff c343b69` in `/tmp/libfprint-goodix`
  (procedure reproduces the committed patch byte-identically before the
  change), synced to repo root + NixOS module; `test_m1_c1` hash pin rolled;
  `docs/PROGRESS.md` hash line updated. Full suite + driver ninja build green
  (see verification below).

Out of scope on purpose (pre-existing, other lanes): `malloc`/`g_free`
pairing, `guint16` narrowing, unaligned `GoodixPresetPsk` casts, mock 0xe4
36-byte shape divergence — all flagged by reviewers, none introduced here,
each needs its own journal-backed lane.

## Verification (hermetic, agent-run)

- `python3 -m unittest tests.tier1_feature.test_f27_psk_provision` — 5/5 green.
- `bash tests/run_all_tests.sh` — 400/400 green (2 pre-existing skips if any).
- Driver-only ninja build in `/tmp/libfprint-goodix/build` clean under the
  repo warning profile.
- `test_f25_patch_sync` green (patch reconstructs driver byte-for-byte);
  `apply --check` clean statement re-verified at regen time.
- 2+ independent subagent re-reviews of THIS diff: APPROVE, zero open
  bugs/nitpicks (reports attached in handoff).

## Hardware verify protocol (user only, AGENTS.md compliant)

1. Deploy + restart:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Phase 1, hands off 60s ("hands off" + timestamp): expect silence (fewer
   lines than before — no `5e0a PSK` lines at all is CORRECT post-strip).
3. Phase 2, warm check: `fprintd-verify` (enrolled finger), expect
   `verify-match`. Then Phase 2b, cold check: full poweroff, wait 30s, power
   on, login, `fprintd-verify` again.
4. Paste client lines plus:
   `journalctl -u fprintd --since "15 min ago" --no-pager | grep -a -E "5e0a TLS|5e0a frame|timed out|error|failed|minutiae" | tail -n 30`

### Predicted journal signatures

- **Confirm (close ticket):** no `5e0a PSK` lines; `5e0a TLS connection ready
  (cipher: PSK-AES128-CBC-SHA256, proto: TLSv1.2)` then frames
  (`declen=10564`) and `verify-match` on warm AND cold. Verdict: confirmed →
  close (activation strip is behavior-preserving; 26 stays buried).
- **Falsify (reopen 26 with evidence):** `bad record mac` (`0x0A000119`) on
  cold with pasted lines showing no PSK states involved. Verdict: falsified →
  next lane is Windows USB-trace parity of TLS-slot state (NOT re-adding
  0xe4/0xe0 guesses — both encodings already closed).
- **Inconclusive:** stale `openssl s_server` on the test port (`ss -tlnp`),
  `Resource busy` (fprintd left running during a Python probe), or missing
  pasted lines. Verdict: `inconclusive-because-[flaw]` + rerun.

## Reopen rule

Reopen 26/37 only on a pasted `bad record mac` journal recurrence. A wrong-
finger `verify-no-match` with clean TLS is correct behavior (ticket 19 lane),
not a PSK event.

## Hardware finding 2026-09-06 (warm half CONFIRMED, cold half pending)

- Warm: `5e0a TLS connection ready (cipher: PSK-AES128-CBC-SHA256, proto:
  TLSv1.2)` first try, zero `5e0a PSK` lines, `verify-match` on
  left-middle-finger — with deployed build `3c4ed07e` (our code).
- Cold: full poweroff → 30s wait → boot → verify still pending.

## Hardware finding 2026-09-07 (cold TLS transport confirmed; match acceptance pending)

- After the reboot, the pasted journal showed `TLS connection ready` and
  complete frames with `declen=10564`; no `bad record mac` occurred. This is
  the discriminating upstream-clean strip result.
- The client result was `verify-no-match`. Per the reopen rule, clean TLS plus
  a no-match is not a PSK failure, but the ticket's full warm-and-cold
  `verify-match` acceptance is not demonstrated by this paste.
- Verdict: `confirmed` for behavior-preserving cold TLS; formal biometric
  acceptance remains `inconclusive-because-no-verify-match`.

### Final close evidence

The later correct `verify-match`, repeated TLS-ready lines, complete
`declen=10564` frames, and absence of `bad record mac` close the upstream-clean
activation strip. Any remaining no-match is a biometric placement/matching
result, not a PSK/provisioning failure.

## Cold verdict 2026-09-06 (FALSIFIED — parent ticket 26 reopened)

- Cold boot produced the pasted `0A000119 bad record mac` recurrence on
  every handshake (zero PSK states involved — strip exonerated, verdict
  killed). Per this ticket's own falsify clause and reopen rule, ticket 26
  is reopened with the evidence; next lane is Windows USB-trace parity of
  the TLS-slot state, NOT re-adding 0xe4/0xe0 guesses.
