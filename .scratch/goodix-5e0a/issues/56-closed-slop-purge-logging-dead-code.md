# 56 — Slop purge: logging, dead defines, duplication

**What to fix (no behavior change):**
- `g_message` in library: `goodix5e0a.c:300,315,372,377,429,480,572`, `goodix.c:1084,1087,1093` → `fp_dbg` or gated. `g_warning` vs `fp_warn` at `goodixtls.c:119,195`.
- Per-frame `fp_dbg` x15 in hot path (`:873,:914,:919,:937,:988,:1377,:1410,:1462`) → single `declen/frame-stats` line (ticket 24).
- Dead: `goodix5e0a.h:50-53` `REG_GAIN_EXPOSURE*` zero uses; `:35-36` `SCAN_*` dup of `WIDTH/HEIGHT`; local `GOODIX_CMD_SESSION_D6` vs `goodix_proto.h` authority; typo `Didn't excpect` `goodix.c:307,354`.
- Duplication x3 stale-guard (`goodix5xx.c:628` ~= `goodix5e0a.c:412,340`), generic `goodix.c` logging `5e0a`, `goodix5xx.h:66-84` single-subclass vtable (keep contract, document or fold).
- Forensic diary (`goodix5e0a.c:90,94,106,130,136,145,211,718,760` pcap offsets/pkt numbers) → trim to one parity line. Overlong `on_read_img ~190L`, `process_raw_frame ~150L` → split when touched.
- Magic numbers (`0x01` vs `0x55` `unused_flags`, `data[2]!=0xff`, `2000:5000`, `128.0f`, `500/25.4` x2) → named consts.

**Settled (24/32/36/50):**
- No per-frame disk dumps; LGPL headers stay; `--werror` + `uncrustify` clean; shared `goodix5xx.c` no subclass externs.

**Status:** closed (verdict: confirmed on hardware, gen-158 deployed driver)

**Rescoped Directives (2026-09-11 Audit):**
1. **Telemetry Invariant (AGENTS.md):**
   - Strike the requirement `grep -rn g_message ... empty`.
   - **PRESERVE** `g_message` for the single consolidated `5e0a frame stats:` line: it must remain unconditionally visible in `journalctl -u fprintd` without `G_MESSAGES_DEBUG=all`.
   - **PRESERVE** `g_message` for warm activation lifecycle status (`5e0a warm activation: reusing MCU config...`).
2. **Hot-Path Logging Pruning:**
   - Demote only verbose multi-line raw hex diagnostics (`raw first 16 bytes:`, `wire layout:`) to `fp_dbg`.
3. **Dead Code & Hygiene:**
   - Remove dead defines (`goodix5e0a.h` `REG_GAIN_EXPOSURE*`, duplicate `SCAN_*`).
   - Fix typos (`Didn't excpect` → `Didn't expect` in `goodix.c`).
   - Replace magic numbers (`2000:5000`, `500.0/25.4`, `128.0f`) with symbolic constants.

**Acceptance:**
- `5e0a frame stats:` remains present as `g_message` and appears in regular journal runs.
- Hot-path debug spam reduced; dead defines removed; build clean with `ninja`.

**Agent record (2026-09-11, rescoped directives only):**
- Driver: `wire layout` g_message→fp_dbg (`goodix5e0a.c:997`; `raw first 16` already fp_dbg); removed `SCAN_*` + 4x `REG_GAIN_EXPOSURE*` from `goodix5e0a.h`; added `FDT_UP_GUARD_TIMEOUT_MS (2000)` / `FDT_UP_TIMEOUT_MS (5000)` / `PPMM (500.0/25.4)` / `NORMALIZE_MIDPOINT (128.0f)` with values unchanged; fixed 2x `excpect`→`expect` in `goodix.c`. `frame stats:` + warm lifecycle g_messages preserved.
- Tests repointed (same values via consts): f40/f42 journal budget 24→23; f47 guard/timeout consts; m2 ppmm const; m1/boundary/c2 REG+SCAN now assertNotIn (purge proof), canonical gain pinned via `struct.pack("<H", 0x0305)`.
- Deliberately untouched (out of rescoped scope / frozen): `GOODIX_CMD_SESSION_D6` stays local; `goodixtls.c` g_warning stays; diary comments, function splits, stale-guard dedupe, vtable fold untouched (AGENTS.md R2-R4).
- Evidence: 73 hermetic tests, 71 pass; 2 remaining FAILs pre-existing stale-`/tmp` tree (down_retry array + repo-vs-/tmp sync — both failed at baseline before this change); `gcc -fsyntax-only` with project `-Werror` flags passes for `goodix5e0a.c` + `goodix.c`; `goodix5e0a.c` non-empty LOC 1524 < 1525 budget.
- Flag: `/tmp/libfprint-goodix` tree is divergent (its own `HOLD/IDLE` timeout names, D6-in-proto.h, tickets 52/57/59) — merge will need a name reconcile; repo names rule.

**Predicted journal signatures (confirm / falsify, no behavior change):**
- Confirm: enrolled tap shows `5e0a frame stats:` as g_message without debug env; `wire layout:` absent without `G_MESSAGES_DEBUG=all`, present with it; `grep -E "timed out|Invalid ACK|verify-unknown-error|failed to"` empty on serving-instance match-claim window.
- Falsify: any missing `frame stats:`, any `0x34 timed out` outside the held-finger ticket-47 path, or any new `Invalid ACK`.

**User verify (hands only yours):**
1. `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Phase 1: `echo "hands off $(date -u +%H:%M:%S)"`, idle 60s, `journalctl -u fprintd --since "2 min ago" | grep -c "5e0a frame stats:"` (expect 0, silent).
3. Phase 2: `echo "holding $(date -u +%H:%M:%S)"`, enrolled-tap + press-hold 60s, confirm `5e0a frame stats:` present, `wire layout:` absent, held-wrong-finger shows exactly one `verify-no-match` with ~18s FDT-UP re-issue loop until lift.

**Hardware verdict (2026-09-11, confirmed):**
- Deployed via refreshed unified patch SHA `9cf21a13`, NixOS gen-158 (system-158-link 13:16:28). Note: first test round ran on stale gen-157 (wire-layout x9, debug provably off at both manager and service level) — re-tapped on gen-158 to confirm.
- `journalctl -u fprintd --since "2 min ago" | grep -c "5e0a wire layout:"` → `0` (demotion effective, debug env off).
- `frame stats:` present, healthy: `active=5120, min_v=504-515, max_v=2691-2707, declen=10564` (full frames, real finger, not MCU blanks).
- Smoke grep `timed out|Invalid ACK|verify-unknown-error|failed to` → empty on serving window.
- `fprintd-verify` end-to-end OK (`verify-no-match` on non-matching finger — correct core verdict, frame delivered).
