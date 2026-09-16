# 85: TLS Park TTL Tuning (Eliminate 1s Cold-Start Delay on Repeated Unlocks)

**What to build:** Extend `GOODIX_5E0A_TLS_PARK_TTL_US` from 30 seconds to 300 seconds (5 minutes). This allows subsequent authentication claims (e.g. repeated `sudo` commands, lockscreen prompts, polkit dialogs) to reuse the live, primed TLS session via the lightweight `QUERY_MCU_STATE` health check (< 10ms), eliminating the 800ms–1s activation handshake penalty.

**Blocked by:** 84 (Optimistic Verify Fast-Path).

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

## Predicted Journal Signatures

- **Confirm:**
  - Second claim at 90s logs: `5e0a parked TLS session candidate fresh, health-checking (gen=...)` followed immediately by sensor ready; no full handshake (`Uploading MCU config` or TLS PSK negotiation skipped); pre-touch bring-up latency < 15ms.
  - After > 300s idle, logs: `5e0a parked TLS session unhealthy (expired), full re-handshake` and recovers cleanly.
- **Falsify:**
  - Sensor fails health check at 90s due to internal MCU timeout, forcing repeated fallbacks.
- **Inconclusive-because-[flaw]:**
  - fprintd was restarted between claims, clearing in-memory park state.
