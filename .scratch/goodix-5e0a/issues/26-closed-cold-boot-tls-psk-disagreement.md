# 26 — Cold-Boot / Post-Reboot TLS 1.2 PSK Disagreement & Key Provisioning

**What to build:** 
Resolve the post-reboot / cold-boot TLS 1.2 PSK handshake failure. On machine cold boot or hardware power cycle, the Goodix 27c6:5e0a MCU rejects the TLS Finished record with a bad record MAC (`error:0A000119:SSL routines::decryption failed or bad record mac`), preventing the sensor from entering encrypted session mode and causing all subsequent image captures (`0x20`) to be rejected with `0xd0` (`GOODIX_CMD_REQUEST_TLS_CONNECTION`).

**Blocked by:** None. Supersedes the cold-boot OTP hypothesis from Ticket 20.

**Status:** closed

**Verdict:** closed as intermittent/not reproducible on the current
upstream-clean build. Reopen only on a new pasted `bad record mac` recurrence.

**Verdict (2026-09-05): could-not-reproduce + mechanism dismantled.**
The systematic-cold-failure premise (one post-reboot event) never reproduced
across all later reboots; post-reboot TLS + capture + matching proven working
on the deployed driver (pids 24936, 1674). Experiment record: 8-byte 0xe4
rejected / 16-byte sliced 0xe4 reads factory slot (settled); 0xe0 rejected in
both encodings (provisioning path closed without Windows-trace parity);
bb020001 holds factory even while TLS succeeds (slot-attribution falsified);
fail-fast briefly bricked warm logins, replaced by soft-fail (warm unbrickable
by review enumeration). Shipped driver keeps the 0xe4 read + soft-fail
provision as permanent harmless instrumentation with per-activation journal
diagnostics. Right-finger match confirmation and any future true-poweroff
cold run belong to tickets 19/20 (verify behavior), not here. Reopen only on
a pasted `bad record mac` journal recurrence.

**Experiment 26.3 build (2026-09-05 ~17:45 IST) — implements the plan below.**
- `goodix.c`/`goodix.h`: new `goodix_send_preset_psk_read_slice(flags,length,
  offset)` emitting 16-byte LE `[length,offset,flags,0]` on `0xe4`
  (byte-identical to Exp-26.1 Python bytes
  `20 00 00 00 00 00 00 00 01 00 02 bb 00 00 00 00`; old 8-byte helper
  untouched for 511). Reply parsing unchanged (same layout as Python).
- `goodix5e0a.c`: `ACTIVATE_READ_PSK` uses the slice helper `(FLAGS,32,0)`;
  `on_psk_write` reject/error → warn `continuing with host key` + advance
  (warm can never brick; cold falls through to TLS as before on reject).
- Patch regen `1f5991bf...` synced repo-root + NixOS module; test hash pins
  rolled; full suite 395 green (2 pre-existing skips); driver ninja build
  clean (only pre-existing 511/openssl warnings); 2 independent reviews
  APPROVE (memory/SSM, bytes/tests/warm-safety).

**Hardware verdict on §6 build (2026-09-05 17:30–17:35 IST): FALSIFIED (Falsify A).**
Journal (fprintd pids 14034/14368/14696/15507, pulled by agent via
`journalctl -u fprintd`): every activation logs
`5e0a PSK read: device reports no key, provisioning host key` then
`failed during activation: 5e0a PSK provision rejected by MCU (code: 5)`.
Warm baseline proven minutes earlier on the old driver (pid 13146, 17:30:16):
`5e0a TLS connection ready`, `minutiae_count=29`. Conclusions: (1) the 5e0a MCU
rejects the 8-byte `[flags,0]` 0xe4 form — `length=0` likely means "read zero
bytes" on this firmware (511 treats 0 as read-all); only the 16-byte sliced
form `[len=32,off=0,flags,0]` has hardware evidence (Exp 26.1). (2) The 40-byte
0xe0 write is also rejected (encoding unproven on 5e0a — same doubt as the
read). (3) Fail-fast on provision-reject was wrong: it bricked warm logins.
Next experiment 26.3 (one lane — PSK-reconciliation robustness, same SSM
states, no frozen code): sliced 16-byte 0xe4 read via a new 5e0a-only send
helper (511 helper untouched) + provision-reject becomes soft-fail
(warn + advance to UPLOAD_CONFIG/TLS, so warm can never brick again).

---

## 1. Ground Truth Journal Evidence (Post-Reboot Failure)

Following a system reboot (machine cold start), `fprintd-enroll` and `fprintd-verify` consistently fail with `enroll-unknown-error` / `verify-unknown-error`.

**Systemd Journal Signature (`journalctl -u fprintd` at 14:38:08, 14:54:02, 15:30:16):**
```text
Sep 05 15:30:16 sastapc fprintd[60626]: 5e0a PSK callback: using device-specific PSK (32 bytes, identity='Client_identity')
Sep 05 15:30:16 sastapc fprintd[60626]: 5e0a TLS accept failed: error:1C800066:Provider routines::cipher operation failed (0x1c800066, cipher: PSK-AES128-CBC-SHA256)
Sep 05 15:30:16 sastapc fprintd[60626]: 5e0a TLS accept failed: error:0A000119:SSL routines::decryption failed or bad record mac (0xa000119, cipher: PSK-AES128-CBC-SHA256)
Sep 05 15:30:16 sastapc fprintd[60626]: 5e0a TLS accept failed: error:0A000139:SSL routines::record layer failure (0xa000139, cipher: PSK-AES128-CBC-SHA256)
Sep 05 15:33:22 sastapc fprintd[60626]: 5e0a D32 reply: status=0x02 len=16 bytes=[02 00 3f 00 35 01 5c 01 f4 00 0e 01 34 01 17 01 ]
Sep 05 15:33:22 sastapc fprintd[60626]: 5e0a D32 touch confirmed: mask=0x3f energy=1758
Sep 05 15:33:22 sastapc fprintd[60626]: Invalid protocol command: 0xd0
Sep 05 15:33:23 sastapc fprintd[60626]: 5e0a failed to scan: Command timed out: 0x20 (code: 24)
Sep 05 15:33:23 sastapc fprintd[60626]: Device reported an error during identify for enroll: Command timed out: 0x20
```

---

## 2. Chronological Analysis: What Worked vs What Failed

### A. When it was working (Run 15 & Run 16, 02:20–02:36 AM)
- In Hardware Runs 15 and 16, the system achieved consecutive verified biometric matches on physical hardware (`13/12`, `15/12`, `14/12`).
- The sensor was actively decrypting live 10,564-byte wire frames via `SSL_read`, yielding 23–25 minutiae.
- **Critical Context:** The laptop had been running continuously without a cold reboot or USB power loss. The MCU's volatile RAM retained the active session PSK matching `goodix_5e0a_psk` (`d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab`).

### B. What Happened During Reboot
- During machine reboot or power-off, USB VBUS drops and the Goodix Geneva MCU executes a cold reset.
- Volatile SRAM on the MCU is cleared.
- Upon booting Linux, the MCU initializes in an unprovisioned or reset cryptographic state.
- When `libfprint` attempts a TLS 1.2 PSK handshake using `goodix_5e0a_psk`, the MCU's internal crypto engine computes a different message authentication code (MAC) for the Finished record, resulting in OpenSSL error `0x0A000119: decryption failed or bad record mac`.
- The TLS handshake fails, leaving the MCU in unencrypted mode.
- When the user touches the sensor, the MCU sends `0xd0` (`REQUEST_TLS_CONNECTION`) because it requires TLS before it will stream raw fingerprint frames (`0x20`). Libfprint times out waiting for `0x20`, emitting `enroll-unknown-error` / `verify-unknown-error`.

### C. Post-Mortem of Failed Attempts

| Attempt | Change Tested | Hypothesis | Actual Hardware Result | Why It Failed |
|---|---|---|---|---|
| **1** | Added `ACTIVATE_READ_OTP` (`0xa6`) | MCU needs OTP registers read before TLS to load PSK into SRAM. | `TLS accept failed: bad record mac` (identical) | CMD `0xa6` is a host read command that returns 128 bytes of OTP info to the host; it does not load or provision the internal crypto keys. |
| **2** | Reverted `ACTIVATE_READ_OTP` | Maybe `0xa6` perturbed the 4-state activation sequence. | `TLS accept failed: bad record mac` (identical) | Removing `0xa6` left the MCU in the same unprimed state. |
| **3** | Prioritized cipher `PSK-AES128-CBC-SHA256:ALL:@SECLEVEL=1` | OpenSSL 3.x negotiated wrong cipher suite or SECLEVEL rejected SHA256. | Cipher logged as `PSK-AES128-CBC-SHA256`, still `bad record mac`. | The cipher suite was never the issue; the failure is cryptographic HMAC verification due to mismatched secret keys between host and MCU. |
| **4** | Pre-TLS MCU Config Upload (`0x90`, 256B) | MCU needs sensor registers / AFE loaded before starting crypto engine. | `TLS accept failed: bad record mac` (identical) | Sensor configuration (`0x90`) sets AFE and touch scan registers, not crypto key registers. |

---

## 3. The Core Unknown & Missing Link

In Goodix TLS devices (511, 52xD, 5e0a), the PSK is not always hardcoded permanently in volatile MCU memory across power cuts.
There are three possible mechanisms:
1. **Host-Provisioned PSK via `0xe0` (`GOODIX_CMD_PRESET_PSK_WRITE`)**:
   - The Windows WBDI driver or Windows Biometric Service writes a pre-shared key to the device on cold boot using CMD `0xe0` before attempting TLS.
   - Sibling driver `goodix511.c` checks the PSK via `0xe4` (`GOODIX_CMD_PRESET_PSK_READ`), and `goodix.c` has `goodix_send_preset_psk_write` (`0xe0`).
2. **Device Key Derivation from Challenge / OTP**:
   - The device reports a key or challenge via `0xe4`, or derives a session key from OTP memory + host nonce.
3. **Prior Windows State Preservation**:
   - Prior to reboot, the machine may have booted into Windows (or ran a Python script that wrote the key), which primed the volatile SRAM. Once rebooted cleanly into Linux without Windows running first, the MCU was blank.

---

## 4. Planned Experiments

### Experiment 26.1: Probe MCU PSK Status via Python Standalone Harness (CONFIRMED ON HARDWARE)
- **Command:** `PYTHONPATH=. nix-shell -p python3Packages.pyusb --run "python3 experiments/test_register.py"`
- **Hardware Run Output (2026-09-05 15:43:30 IST):**
  ```text
  Reg 0x0000: 03a80025
  --- Reading PSK status ---
  preset_psk_read(0xbb020001): success=True, flags=0xbb020001, data=68776fdcf6352a215cc11cd58db2b361eb95a506cb503da68fb01ac1506ff1c9
  ```
- **Finding:**
  - On cold boot, the Goodix 27c6:5e0a MCU returns `flags=0xbb020001` and holds default key `68776fdcf6352a215cc11cd58db2b361eb95a506cb503da68fb01ac1506ff1c9`!
  - Our driver’s hardcoded key `d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab` disagrees completely with this key, explaining the exact `bad record mac` error during TLS accept.

### Experiment 26.2: Test Connecting TLS with the Cold-Boot PSK vs Provisioning
- **Option 1 (Use Hardware Cold-Boot PSK):**
  Configure OpenSSL to use `68776fdcf6352a215cc11cd58db2b361eb95a506cb503da68fb01ac1506ff1c9` when `preset_psk_read` reports it.
- **Option 2 (Provision Windows DPAPI PSK via `0xe0`):**
  Send `preset_psk_write(0xbb020001, d853ad...)` to the MCU before TLS handshake to restore the working DPAPI key.
- **Predicted Outcomes:**
  - *Confirm Signature:* `5e0a TLS connection ready` with zero OpenSSL errors.
  - *Falsify Signature:* TLS still fails record MAC.

---

## 5. Artifacts & References
- Previous working match evidence: `docs/PROGRESS.md` Run 15 & Run 16.
- OpenSSL error logs: systemd journal 14:38:08, 14:54:02, 15:30:16.
- Reverse engineering references: `experiments/test_register.py`, `experiments/test_init_sensor.py`.

---

## 6. Implemented Fix (ready-for-hardware-verify, 2026-09-05)

**One variable:** activation-time PSK reconciliation. TLS cipher/callback, FDT,
image pipeline untouched.

- `libfprint-driver/goodix5e0a.c`: activation SSM grows
  `... CHECK_FW_VER -> READ_PSK (0xe4) -> PROVISION_PSK (0xe0, conditional)
  -> UPLOAD_CONFIG -> TLS`. `on_psk_read`: match → `jump_to_state(UPLOAD_CONFIG)`
  (warm path: one extra 0xe4 round-trip, zero other change); mismatch/no-key/
  transport-error → advance to provision (provision rewrites the host key
  idempotently). `on_psk_write`: MCU reject/transport error → fail fast with
  `5e0a PSK provision rejected by MCU` (TLS would MAC-fail anyway); success →
  `5e0a PSK provisioned`. Mismatch log classifies `factory-default` vs
  `unknown` via `goodix_5e0a_psk_default`; no key bytes ever hit the journal.
- `libfprint-driver/goodix5e0a.h`: adds diagnostic-only
  `goodix_5e0a_psk_default` (`68776fdc...ff1c9`, never used for TLS).
- `libfprint-driver/goodix.c`: fixes `goodix_send_preset_psk_write` wire
  length `sizeof (payload)` (pointer, arch-dependent) →
  `sizeof (GoodixPresetPsk) + length` = 40 (both send sites; identical bytes on
  x86_64, correct everywhere).
- `tests/tier1_feature/test_f27_psk_provision.py` (new, hermetic): header key ==
  `CANONICAL_PSK`, struct-sizeof pins (2 send sites + malloc), SSM ordering,
  mock 0xe4 shape with literals. 9/9 green with f05.
- Unified patch regenerated from `/tmp/libfprint-goodix` (`git diff c343b69`,
  `apply --check` clean on pristine, patched files byte-identical) and synced
  to repo root + `/home/sastauser/NixOS-Hyprland/modules/goodix/`
  (sha256 `0faabe2f90cd7bd5b7f35158ed7647fcc53c2f84f4c9c0d32e810c7bda5379cd`).
  Driver-only ninja build clean; 50/50 focused unit tests green (f25/f27/f05/
  m1/m2/f20/f21/f22).
- Reviews: 5 independent subagent reviews (memory, protocol, tests, + 2
  fix-up re-reviews). Two minors fixed (dead default array → now classifies;
  raw key logging → removed). Open known unknown: the 8-byte `[flags,0]` 0xe4
  request form matches the 511 precedent + Python no-slice form but only the
  16-byte sliced form has 5e0a hardware evidence — read failure degrades to
  provision (no wedge), and the journal discriminates (see signatures).

**Context note:** at implementation time the sensor works after a plain reboot
(warm key retained in MCU SRAM), so the deployed warm run below is a
no-regression gate; the cold run (full power loss) is the discriminating run.

### Hardware verify protocol (user only, AGENTS.md compliant)

1. Deploy + restart:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Phase 1, hands off 60s ("hands off" + timestamp): silent vs cycles.
3. Phase 2, warm check: `fprintd-verify` (enrolled finger), expect
   `verify-match`. Then Phase 2b, cold check: full poweroff, wait 30s,
   power on, login, `fprintd-verify` again.
4. Paste client lines plus:
   `journalctl -u fprintd --since "15 min ago" --no-pager | grep -a -E "5e0a PSK|5e0a TLS|5e0a frame|timed out|error|failed|minutiae" | tail -n 30`

### Predicted journal signatures

- **Confirm warm (no regression):**
  `5e0a PSK status: device key matches host key, skipping provision` then
  `5e0a TLS connection ready` then `verify-match`. Verdict: warm-confirmed.
- **Confirm cold (fix works):**
  `5e0a PSK mismatch: device has factory-default key (...), provisioning host key`
  then `5e0a PSK provisioned` then `5e0a TLS connection ready` then
  `verify-match`. Verdict: confirmed → close ticket.
- **Falsify A (read form rejected):** `5e0a PSK read failed (...), attempting
  provision` on a known-warm device, or `provision rejected by MCU`, followed
  by the old `bad record mac`. Verdict: falsified → next experiment is the
  16-byte sliced 0xe4 form (`length=32, offset=0`) and/or post-write
  verify-read (one variable).
- **Falsify B (write not latched):** `5e0a PSK provisioned` yet TLS still
  `bad record mac`. Verdict: falsified → next experiment is post-write
  verify-read + Windows-trace parity for the 0xe0 payload.
- **Inconclusive:** stale `openssl s_server` on the test port (verify with
  `ss -tlnp`), missing pasted lines, or `Resource busy` (fprintd left running
  during a Python probe). Verdict: `inconclusive-because-[flaw]` + rerun.

### Predicted journal signatures — Experiment 26.3 build (patch `1f5991bf`)

Protocol: same 4 steps above (deploy → hands-off 60s → warm `fprintd-verify`
→ cold poweroff+`fprintd-verify`). Agent pulls the journal itself.

- **Confirm warm (must hold — regression gate):**
  `5e0a PSK status: device key matches host key, skipping provision` (or, if
  the sliced read is also rejected: `... continuing with host key ...`) then
  `5e0a TLS connection ready` then `verify-match`. Either PSK line is fine —
  the requirement is TLS + match. Verdict: warm-confirmed.
- **Confirm cold (fix works):**
  `5e0a PSK mismatch: device has factory-default key (...), provisioning host
  key` then `5e0a PSK provisioned` then `5e0a TLS connection ready` then
  `verify-match`. Verdict: confirmed → close ticket.
- **Partial (read fixed, write rejected):**
  sliced read shows `factory-default`/`unknown` mismatch, then
  `5e0a PSK provision rejected by MCU, continuing with host key`, then cold TLS
  still `bad record mac` — but warm still matches. Verdict: read-form
  confirmed, write-form falsified → next experiment is the sliced 0xe0 write
  form (one variable). Warm stays working throughout.
- **Falsify (sliced read also rejected):**
  `5e0a PSK read failed` or `device reports no key` even with 16-byte form,
  warm still matches via soft-fail. Verdict: falsified → next experiment is
  USB-trace parity of the 0xe4 request against Windows (one variable).

### Experiment 26.3 verdict (2026-09-05 ~17:54 IST): PARTIAL (warm)

Journal (fprintd pid 24936, pulled by agent): 4 consecutive activations, all
`5e0a PSK mismatch: device has factory-default key (flags=0xbb020001 len=32),
provisioning host key` → `5e0a PSK provision rejected by MCU, continuing with
host key` → `5e0a TLS connection ready (PSK-AES128-CBC-SHA256, TLSv1.2)` with
real frames (`minutiae_count=11,14,17,18,21`). User confirms login works.
Settled: (1) the 16-byte sliced 0xe4 form WORKS on 5e0a (8-byte form dead —
Falsify A closed); (2) soft-fail restores warm logins; (3) the 40-byte 0xe0
write IS rejected (write-form falsified for this encoding).
New finding: the MCU reports the factory key in slot `bb020001` WHILE TLS
with the host key succeeds — so slot `bb020001` is likely NOT the TLS key
slot (candidate: another flags slot, cf. 511's `bb020003`; `test_register.py`
already probes `bb020001/bb020003/bb020007`). This reopens Exp-26.1's
attribution: the cold-boot `6877…` report may never have been the TLS key,
and the original cold MAC failure may be a different slot/state. No cold boot
happened in this run (switch only), so the original cold failure is still open.

### Experiment 26.4 result, warm (2026-09-05 ~18:00 IST): slot survey via
`experiments/test_register.py` (fprintd stopped, user-run, pasted):
- `bb020001`: success, factory key `6877…` (as always).
- `bb020003`, `bb020007`: MCU error reply (Python `NoneType` unpack failure =
  `(False, None, None)` error path).
So the ONLY 0xe4-readable slot always reports factory — even while TLS with
the host key succeeds. The 0xe4-visible slot is NOT the TLS key (two-area
theory: 0xe4 reads factory/OTP area; the operational TLS key lives elsewhere
— SRAM slot cleared on power loss, which still explains the original cold MAC
failure; or another flags value). Exp-26.1's attribution ("bb020001
disagreement explains the MAC failure") is FALSIFIED as stated; the cold
mechanism is now "operational key lost on power loss, 0xe0 re-provision
encoding unknown".

### Experiment 26.5 verdict (2026-09-05 ~18:10 IST): REJECTED, both encodings

User-run `experiments/probe_psk_write.py` (fprintd stopped, pasted):
`WRITE_0xe0_SLICED: accept=False`, re-read still factory (`VERDICT:
still-factory`). Combined with the driver run: 0xe0 is rejected in the
40-byte no-slice form AND the 44-byte sliced form. The 0xe0-provisioning path
is closed pending Windows-trace parity — no more encoding guesses.
Standing facts: only `bb020001` is 0xe4-readable (always factory); TLS with
the host key works regardless; provision attempts are harmless no-ops.
Driver keeps read + soft-fail provision as permanent instrumentation (one
extra round-trip per activation, journal documents MCU slot state each time).

### Status of the original cold-boot theory: UNPROVEN single event

Evidence audit: the systematic-cold-failure premise rests on ONE post-reboot
event. Since then every reboot works, and Exp 26.1–26.5 show the cited
mechanism (bb020001 disagreement) cannot explain it — that slot reads factory
even while TLS succeeds. The remaining gate is a TRUE cold boot (full
poweroff, 30s wait, power on, `fprintd-verify`, agent pulls journal): if it
matches, close this ticket as could-not-reproduce (keep instrumentation);
if it MAC-fails, the mechanism is something other than 0xe4/0xe0 key
provisioning (suspect TLS-slot state or session ordering — Windows USB trace
parity becomes the next and only lane).

### True cold boot (2026-09-05 19:41 IST, pid 1713, first boot after poweroff):
5 activations in the first minute, ALL `TLS connection ready` first try,
healthy frames (`minutiae 14–26`, `h_corr 0.921–0.970`), zero MAC errors,
zero failures. The original single event is now outnumbered by warm reboots
AND a true power-loss boot, all clean. Case closed for good.

### Post-reboot run (2026-09-05 18:03 IST, pid 1674): TLS FINE, legitimate no-match

After a reboot + `fprintd-verify` with the WRONG finger: activation clean
(no PSK errors in window), TLS session up, full capture + Bozorth runs
(`probe_nrows=20`, `gallery_len=8`, scores mostly 0–10/12). Client verdict
`verify-no-match` is CORRECT behavior for the wrong finger, not a failure.
Note: one touch in the multi-touch session scored 13/12 vs gallery[3], but
the client decides on the claimed finger's deciding touch — user-reported
rejection rules. The original cold MAC failure did NOT reproduce across this
reboot. (Side note: 17:48:13 pid 18278 still shows §6 fail-fast strings —
the bricked build was live until the 26.3 deploy; failures in that window
were the brick, not hardware.)
Remaining optional gates: (a) one `fprintd-verify` with the RIGHT finger
post-reboot to close the warm loop with a match; (b) a true poweroff+wait
cold boot if the single-event theory is ever to be fully buried.

## Recurrence 2026-09-06 (reopened — 37's reopen rule triggered)

Pasted `bad record mac` recurrence, no PSK states involved (37's strip is
deployed: zero `5e0a PSK` lines anywhere). Fresh boot (~22:25, uptime 17m
at 22:42), deployed build `3c4ed07e`. EVERY handshake since boot fails:

```
Sep 06 22:29:00 fprintd[1675]: 5e0a TLS accept failed: error:1C800066:Provider routines::cipher operation failed
Sep 06 22:29:00 fprintd[1675]: 5e0a TLS accept failed: error:0A000119:SSL routines::decryption failed or bad record mac
Sep 06 22:29:00 fprintd[1675]: 5e0a TLS accept failed: error:0A000139:SSL routines::record layer failure
```

Repeated identically 22:28→22:40 across pids 1675/3727/6465 (hyprlock +
4× `fprintd-verify`, all `verify-unknown-error`; cascade `failed to scan:
Command timed out: 0x20` = MCU_GET_IMAGE with no session, not a separate
signal). NOT a single transient: failing for 12+ minutes, never one
`TLS connection ready`. This breaks the "single post-reboot event"
theory — second event, and this one is persistent, not self-clearing
within the boot.
Strip-independence: the original event ran PRE-strip code (with 0xe4/0xe0
reconciliation), this one runs POST-strip code (37) — identical signature
both ways. The strip neither causes nor prevents it; 37's code stands,
37's cold-close verdict is what's falsified.
Open questions for the reboot test: (a) was this boot a reboot or a cold
poweron (user to confirm — second post-reboot event vs first post-poweroff
failure); (b) does a warm reboot clear it (26 pattern) or does it persist
(new territory → poweroff-drain test); (c) 0xe4 slot bytes in the failing
state (`experiments/test_register.py` before rebooting — banks the
failing-state evidence even if the reboot clears it).

## Banked failing-state data + reboot verdict 2026-09-06

- Slot read in failing state (fprintd stopped, pre-reboot):
  `bb020001: success=True, flags=0xbb020001,
  data=68776fdcf6352a215cc11cd58db2b361eb95a506cb503da68fb01ac1506ff1c9`
  — factory bytes (`68 77 6f` = "hwo" prefix, matches the deleted factory
  table). 26.4 showed factory-bytes-while-TLS-succeeds; this shows
  factory-bytes-while-TLS-fails. Decoupled in BOTH directions: the
  0xe4-visible slot is definitively not the operational TLS key slot.
  `bb020003`/`bb020007` reads crashed in script parsing (`NoneType` reply)
  — harness limitation, void as device signal.
- Reboot CLEARED it: post-reboot `fprintd-verify` → no-match then
  `verify-match` on left-middle-finger (TLS healthy again). Third
  reboot-linked event, same shape as the original: failure stuck for the
  whole boot (here 12+ min), gone after reboot.
- PENDING: boot type of the failing boot (reboot vs cold poweron) — user
  to confirm in one word.
- Banked hypothesis (NOT tested, needs a live failure): on some reboots
  the device fails to load its real key and falls back to the factory-slot
  key → host static-key handshake MAC-fails. Probe if it recurs: one
  verify with the factory key swapped in as host PSK. Do NOT pre-build —
  one build under test at a time.
