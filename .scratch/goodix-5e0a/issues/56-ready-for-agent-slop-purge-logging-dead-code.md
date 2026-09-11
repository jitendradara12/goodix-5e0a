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

**Status:** ready-for-agent

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
