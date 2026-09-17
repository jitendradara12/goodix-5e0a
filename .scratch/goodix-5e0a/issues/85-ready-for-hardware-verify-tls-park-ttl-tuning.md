# 85: TLS Park TTL Tuning (Eliminate 1s Cold-Start Delay on Repeated Unlocks)

**What to build:** Extend `GOODIX_5E0A_TLS_PARK_TTL_US` from 30 seconds to 300 seconds (5 minutes). This allows subsequent authentication claims (e.g. repeated `sudo` commands, lockscreen prompts, polkit dialogs) to reuse the live, primed TLS session via the lightweight `QUERY_MCU_STATE` health check (< 10ms), eliminating the 800ms–1s activation handshake penalty.

**Blocked by:** None. Ticket 88 now confirms daemon survival and parked reuse at 90s. Full acceptance remains incomplete: <15ms finger-wait target missed, >300s expiry and state-loss recovery untested. Tickets 84 and 87 are closed.

**Status:** ready-for-hardware-verify

## Acceptance Criteria

- [x] `libfprint-driver/goodix5e0a.c`: Update `GOODIX_5E0A_TLS_PARK_TTL_US` from 30s to 300s (`G_USEC_PER_SEC * 300`).
- [ ] Claims initiated within 5 minutes of a prior claim reuse the parked TLS session (`5e0a parked TLS session candidate fresh, health-checking`).
- [ ] Sensor activates and enters capacitive touch wait (`0x32 FDT_DOWN`) in < 15ms instead of ~800ms.
- [ ] If device loses state or sleeps, the existing health check catches any failure and cleanly falls back to the full ladder (`goodix_shutdown_tls` + full handshake).
- [ ] Verified on hardware: Repeated `sudo -v` / lockscreen unlocks feel instantaneous without pre-touch warm-up lag.
- [ ] Rule-7 smoke check passes: zero `timed out|Invalid ACK|verify-unknown-error|failed to`.

## Context & Evidence

- In Ticket 33 & 38: Per-attempt cold driver bring-up takes ~800ms–1s:
  - MCU reset $\rightarrow$ config upload $\rightarrow$ TLS 1.2 PSK handshake $\rightarrow$ chip enable.
  - Ticket 38 implemented persistent TLS session parking, but set the TTL conservatively at 30 seconds (`GOODIX_5E0A_TLS_PARK_TTL_US = 30s`).
- In real-world desktop usage, users frequently invoke `sudo`, polkit, or unlock screens 1–3 minutes apart. With a 30s TTL, every such claim hits the full 1-second cold-start handshake.
- Windows keeps the driver service primed continuously in D2 low-power sleep with instant resume.
- Extending the park TTL to 5 minutes covers ordinary desktop workflows while preserving the safety mechanism: Ticket 38 already includes generation tracking (`tls_parked_gen`) and a 500ms `QUERY_MCU_STATE` probe that safely falls back to the ladder if the device ever desyncs (timeouts clear warmth into the full ladder; crypto-grade misses re-enter the warm ladder while warmth is fresh, ticket 40).

## Implementation (2026-09-16, agent)

One variable: `GOODIX_5E0A_TLS_PARK_TTL_US` value only.

- `libfprint-driver/goodix5e0a.c:158`: `#define GOODIX_5E0A_TLS_PARK_TTL_US (G_USEC_PER_SEC * 300)` with a rationale comment naming the ticket-38 invariant (the 0xae probe, not the TTL, is the guard; suspend never parks; failed probe falls into the full ladder).
- `tests/tier1_feature/test_f38_tls_park.py` (`test_b_ttl_and_health_timeout_macros`): pinned literal updated 30 → 300.
- `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`: regenerated from the synced build tree; flake copy at `/home/sastauser/NixOS-Hyprland/modules/goodix/` byte-identical (sha256 `46d76da6…`).

## Build and Test Verification (agent-run, no hardware)

- Ninja drivers build (`nix-shell -p ninja`): `libfprint-drivers.a` + `libfprint-2.so.2.0.0`, exit 0.
- Full suite: 319 passed / 0 failed / 1 skipped (pre-existing native-harness gate).
- `nix-build` derivation: `/nix/store/zgas80hbwf4lbiqmz9jv50kjlia5wd1m-libfprint-goodix-1.94.5-goodixtls-5e0a`, exit 0.
- No wall-clock improvement claimed — that is hardware-only evidence.

## Hardware Verify Protocol (user-only; agent has no fingers/sudo)

One variable per build: deploy and test ONLY the 300s park TTL. No driver edits between phases.

1. Deploy driver:
   ```bash
   cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd
   sudo systemctl set-environment G_MESSAGES_DEBUG=all
   sudo systemctl restart fprintd
   ```
2. Phase 1 — hands off 60s ("hands off" + timestamp): journal must stay silent (no spontaneous activation cycles).
3. Phase 2 — press-hold steady 60s ("holding" + timestamp): enrolled finger held on sensor; attempts withheld (~18s FDT-UP loop) until lift, exactly one `verify-no-match` per wrong-finger hold.
4. TTL reuse probe (the ticket's own criterion):
   ```bash
   sudo -k                       # clear cached credentials so the 2nd sudo actually claims
   fprintd-verify -f right-index-finger   # touch, authenticates; park stamped at deactivate
   ```
   Wait 90 seconds (past the old 30s TTL, inside the new 300s window), then run `fprintd-verify` again and touch.
5. Inspect journal for health-check reuse and the rule-7 smoke grep:
   ```bash
   journalctl -u fprintd -o short-precise --since "5 min ago" --no-pager | grep -a -E "parked TLS session|health-checking|Enabling chip|full re-handshake"
   journalctl -u fprintd --since "5 min ago" --no-pager | grep -a -E "timed out|Invalid ACK|verify-unknown-error|failed to"
   sudo systemctl unset-environment G_MESSAGES_DEBUG
   ```
   Expected: zero smoke-grep hits. (Scope to the serving instance's match-claim window; tolerant `0x34 timed out` lines during a held-finger test are the designed ticket-47 path.)

## Hardware finding 2026-09-16: prerequisite missing

Correction: the earlier agent note claiming a 90-second gap was unsupported.
The pasted shell comment did not sleep. Full evidence is in
`/home/sastauser/goodix-ticket85-journal.txt`:

- Line 598: 22:46:28.029607 close completion.
- Line 607: 22:46:28.039904 USB reset taken, dirty close, boot_seq=5.
- Line 625: 22:46:28.291130 warm expired, cold-start.
- No parked-session reuse appears. The close path never invokes parking;
  `goodix_dev_deinit` therefore destroys TLS and the next open resets USB.
- Ticket 75 covered open-held orphan shutdown, not this close/reopen path.

Verdict: `inconclusive-because-no-90s-gap-and-close-path-never-parks`.
Next experiment: ticket 87's idle-close routing, keeping the 300s TTL fixed.
No further TTL tuning or claimed latency improvement until parking is observed.

## Follow-up evidence 2026-09-16

Ticket 87 now confirms park/reopen/reuse at 5.1s under PID 30198; see its
closed ticket for pasted journal lines. The 300s TTL remains unverified.
In `/home/sastauser/goodix-ticket87-20260916-233440/journal.txt:354,360`,
PID 21957 parks at 23:39:14.076166, then the service exits successfully at
23:39:44.003460. Next claim starts PID 22494 with a cold context. Extending
the in-memory TTL cannot preserve state across process exit.

### Daemon lifetime mechanism, read-only investigation 2026-09-17

The daemon calls `exit(0)` from its own 30s idle timer. It does not stay
resident by default. systemd's successful deactivation records the result,
not an idle-stop request. A normal client D-Bus disconnect can start the
idle countdown; this is different from the daemon losing its system-bus
connection.

Exact installed-source provenance, command and output:

```text
nix-store --query --deriver /nix/store/8jkiyn4gjry62n92vl6h9cmvbblrklqd-fprintd-1.94.5
/nix/store/h9j09h8wdmdc4s3qz0sx2wb2fi5qddkk-fprintd-1.94.5.drv

nix derivation show /nix/store/h9j09h8wdmdc4s3qz0sx2wb2fi5qddkk-fprintd-1.94.5.drv
# Relevant env fields from the JSON output:
"src": "/nix/store/173497h2nmqysyp6jj0il96fy5hb72vz-source"
"version": "1.94.5"
```

All source references below are relative to that source store path:

- `src/fprintd.h:29` defines `TIMEOUT 30`.
- `src/device.c:298-301` defines busy as clients present OR device
  temperature above cold. `src/device.c:1000-1023` notifies busy when the
  last client vanishes or a new client appears. Thus "30s after release"
  is an approximation to the last client's departure, not a driver TTL.
- `src/manager.c:176-198` removes any pending timer, returns immediately
  if `no_timeout`, otherwise re-arms `g_timeout_add_seconds(TIMEOUT, ...)`
  when no devices are busy. `src/manager.c:532-533` also arms it at startup.
- `src/manager.c:158-164` implements that callback with `exit(0)` and no
  log. It bypasses the normal `main loop completed` log in
  `src/main.c:224-230`, so no "Exiting" line is expected.
- `src/main.c:41,121-124,211` defaults `no_timeout` to FALSE and exposes
  `--no-timeout` / `-t`, described as "Do not exit after unused for a while".
  `strings -a` on the installed `libexec/fprintd` also returned that exact
  description, `no-timeout`, and `fprint_manager_timeout_cb`.
- The installed `etc/fprintd.conf:1-2` contains only `[storage]` and
  `type=file`. `src/main.c:90-119` reads storage configuration, not an idle
  duration. The supported opt-out here is a daemon argument.

The exact stop sequence in
`/home/sastauser/goodix-ticket87-20260916-233440/journal.txt` is:

```text
354 23:39:14.076166 fprintd[21957]: 5e0a parking live TLS session (gen=2)
355 23:39:14.076187 fprintd[21957]: Device reported close completion
356 23:39:14.076242 fprintd[21957]: transfer cancelled, aborting read loop...
357 23:39:14.076250 fprintd[21957]: Completing action FPI_DEVICE_ACTION_CLOSE in idle!
358 23:39:14.076253 fprintd[21957]: Not updating temperature model, device can run continuously!
359 23:39:14.076257 fprintd[21957]: released device 0
360 23:39:44.003460 systemd[1]: fprintd.service: Deactivated successfully.
361 23:40:41.010915 systemd[1]: Starting Fingerprint Authentication Daemon...
362 23:40:41.063269 fprintd[22494]: About to load configuration file '/nix/store/8jkiyn4gjry62n92vl6h9cmvbblrklqd-fprintd-1.94.5/etc/fprintd.conf'
363 23:40:41.063290 fprintd[22494]: Launching FprintObject
364 23:40:41.063356 fprintd[22494]: Initializing FpContext (libfprint version 1.94.9)
365 23:40:41.070285 fprintd[22494]: Preparing devices for resume
```

Park-to-exit is 29.927294s, consistent with GLib's seconds-based timer.
A second instance has last close activity at line 164, 23:35:41.080196,
then successful deactivation at line 165, 23:36:10.979237, a 29.899041s gap.
A case-insensitive grep of this journal for
`Exiting|main loop completed|Failed to get name|Failed to open connection|SIGTERM|Stopping Fingerprint`
returned no matches. `src/main.c:145-153` logs `Failed to get name` on
name loss; that path is not evidenced here. Normal read-loop cancellation
at close is not a daemon D-Bus disconnect.

Read-only `systemctl cat fprintd.service` returned the installed unit with
`Type=dbus`, `BusName=net.reactivated.Fprint`, and bare
`ExecStart=/nix/store/8jkiyn4gjry62n92vl6h9cmvbblrklqd-fprintd-1.94.5/libexec/fprintd`.
Its NixOS drop-in adds only Environment lines. No stop request appears in
the supplied journal. The source and both timings identify self-exit as
the supported explanation; this journal is not a syscall or signal trace.

Verdict for the 300s TTL remains
`inconclusive-because-daemon-self-exits-before-90s-probe`.
Single next experiment: ticket
`88-ready-for-hardware-verify-fprintd-no-timeout-override.md`. Its minimal
service-only override is now implemented in both NixOS module copies and
validated against the actual flake's generated drop-in. Driver code and TTL
stay fixed; the custom fprintd package is unchanged. No deployment, daemon
launch, or hardware claim was performed.

After user deployment, run `bash scripts/verify-ticket88.sh` from repo root.
It captures unfiltered journal, timestamps and daemon PID around a real
`sleep 90`, then a second claim. This targeted protocol supersedes this
ticket's older repeated safety-phase instructions for the next run. Use
AGENTS.md's already-verified exception for ticket 87's prior hands-off,
steady-hold and PAM evidence; do not repeat those phases. A same-PID claim
pair still needs journal proof of parked reuse and measured activation
latency before acceptance. The 300s expiry/fallback criteria remain pending.

## Hardware update 2026-09-17: 90s reuse confirmed, full acceptance incomplete

Evidence: `/home/sastauser/goodix-ticket88-20260917-110502/journal.txt`.
Ticket 88's closed report records the relevant lines verbatim. PID 12821
survived the idle gap and logged `TLS session reused (parked 90.2s)` at
11:06:33.744799, line 228. First claim matched; second completed no-match
and parked again. No transport-error grep hits or second TLS handshake.

Measured from candidate-fresh at 11:06:33.744226 (line 222):
- Chip enable complete: 11:06:33.757996 (235), 13.770ms.
- FDT_DOWN sent: 11:06:33.771981 (251), 27.755ms.

Thus reuse beyond the old 30s TTL is confirmed. The literal <15ms FDT_DOWN
criterion is falsified by this run, not satisfied by the chip-enable timing.
Do not close the entire ticket or claim all five-minute gaps are verified.
>300s expiry, state-loss recovery and desktop PAM latency remain untested.
The earlier daemon-lifetime blocker is resolved by ticket 88.

Overall verdict: inconclusive-because-expiry-and-recovery-untested, with
the <15ms finger-wait subcriterion falsified. Single next experiment if
continuing: a >300s idle claim pair on the unchanged build, checking lazy
expiry and clean full-handshake recovery. No performance tuning is proposed.

## Predicted Journal Signatures

- **Confirm:**
  - Second claim at 90s logs: `5e0a parked TLS session candidate fresh, health-checking (gen=...)` followed immediately by sensor ready; no full handshake (`Uploading MCU config` or TLS PSK negotiation skipped); pre-touch bring-up latency < 15ms.
  - After > 300s idle, logs: `5e0a parked TLS session unhealthy (expired), full re-handshake` and recovers cleanly.
- **Falsify:**
  - Sensor fails health check at 90s due to internal MCU timeout, forcing repeated fallbacks.
- **Inconclusive-because-[flaw]:**
  - fprintd was restarted between claims, clearing in-memory park state.
