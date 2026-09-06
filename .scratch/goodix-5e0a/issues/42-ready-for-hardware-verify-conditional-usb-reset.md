# 42 — Conditional USB reset on open (revive 38/40 or bury them)

**What to build:** Make the `g_usb_device_reset()` in `goodix_dev_init`
(`libfprint-driver/goodix.c`, wired as `img_open` at `goodix5xx.c:633`)
conditional: skip it when the previous session on this USB device closed
cleanly, run it on any dirty close / suspend / re-enumeration. One
variable: reset-on-open (always → when-dirty). Activation ladder, scan
SSM, park/warm logic, thresholds untouched — this ticket only decides
whether the device still needs its cold-state repair on a clean reopen.
Tickets 38/40 need NO code changes under this ticket; if warmth/reuse
lines appear, they re-verify as-is.

**Blocked by:** None (hermetic work is small). Decided by hardware.

**Status:** ready-for-hardware-verify

**Live-scope:** open-path reset gating + clean-close bookkeeping only. No
transport changes, no biometric changes, no suspend-path changes (suspend
always forces reset — sleep safety is not negotiable).

## Settled facts (do not re-litigate)

1. Tickets 38/40 verified falsified-as-implemented on hardware 2026-09-06:
   every claim logs `warm expired: reason=cold-start`, even 4–6s-apart
   claims inside one fprintd PID (e.g. pid 147364, 22:00:36→22:01:41), and
   no `session reused` / `warm taken` line ever appears. Cross-claim
   in-memory/session state never survives.
2. Root cause (code, not speculation): fprintd opens per claim, and
   `goodix_dev_init` unconditionally does `g_usb_device_reset()` plus
   `priv->boot_seq++` on every open (`goodix.c:1298-1326`). The reset wipes
   the device-side TLS key and MCU config BEFORE activate runs (kills any
   38 park — health-check can only fail into fallback), and the counter
   bump guarantees the 40 predicate mismatches (kills any warm path). The
   ticket-40 comment claiming "`img_open` brackets the whole open session,
   not each verify" is falsified by the journal.
3. The reset predates all our work (shared upstream open path) and its
   necessity was never measured — no journal-backed reason exists for OR
   against it on a clean reopen. That is exactly what this ticket measures.
4. 38/40 fallbacks already cover the failure mode: if the device needs the
   reset and doesn't get it, activation/scan fails characteristically and
   falls back to the full ladder. The experiment cannot brick warm logins;
   worst case is one failed claim per dirty state.

## Design sketch (agent refines, journal decides)

- Shared priv (`goodix.c:40-65`): add `gboolean clean_close` (default
  FALSE = reset, safe direction) + whatever device-identity key detects
  re-enumeration (USB port/path comparison via
  `fpi_device_get_usb_device`; if no cheap identity exists, any open after
  a vanish event resets — document the choice).
- Set `clean_close=TRUE` at the single point a session proves clean
  (candidate: end of `goodix5e0a_deactivate` destroy/park completion;
  agent picks the exact site and justifies it). Clear it on every failure
  funnel (activate error, TLS error, scan error), on suspend, on
  `warm_down_reason != clean` states — when in doubt, reset.
- `goodix_dev_init`: `if (!priv->clean_close) { reset; }` + move
  `boot_seq++` to fire ONLY when the reset is actually taken (a clean
  reopen is the same device boot by construction — counting it as a new
  boot fakes coldness; freezing it across a real reset would fake warmth,
  so the counter must follow the reset, not the open).
- `goodix_dev_deinit` (close, `goodix.c:1380`): skip BOTH the gen bump
  and the TLS shutdown on a clean close (nothing in flight to orphan —
  deactivate completed; on a dirty close keep bump + shutdown verbatim).
  The parked host session then survives close in memory; the next
  activate's health-check decides reuse. Suspend path untouched (always
  bump + clear + shutdown + reset).
 - Predicted interaction on success: open skips reset → device key/config
   survive → 38 health-check passes (`session reused`) → chip-enable
   re-stamps 40 (`warm taken` on the following claim). Both revive with
   zero changes to their code.

## Hermetic implementation (agent-run 2026-09-07)

- Implemented conditional reset gating in `goodix_dev_init`: the first/dirty
  open resets and increments `boot_seq`; a clean reopen logs and skips both.
  USB bus/address/port/VID/PID identity changes force the dirty path.
- Clean-close bookkeeping is set only after a successful 5e0a activation has
  a live TLS context and parks it. Activation, TLS, chip-enable, scan,
  suspend, destroy, claim-failure, and re-enumeration paths clear it. Clean
  `goodix_dev_deinit` skips the generation bump and TLS shutdown; dirty close
  keeps both existing teardown actions.
- The park branch also requires the existing successful-chip-enable state, so
  a live host TLS pointer left after a failed chip-enable or scan cannot make
  the next open skip reset.
- `python3 -m unittest tests.tier1_feature.test_f42_conditional_reset
  tests.tier1_feature.test_f38_tls_park tests.tier1_feature.test_f39_multiframe_best_of_n
  tests.tier1_feature.test_f40_warm_activation` — 33/33 green.
- `bash tests/run_all_tests.sh` — 433/433 green.
- `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'`
  — driver compiled and linked successfully. Unified patch and NixOS module
  copy are synchronized (SHA-256:
  `1f4de3f7bb680ed4bebb5cfe5edf59b0f7ad004989eaf1cd772fe0eeb2d4205e`).

## Hardware verify protocol (user only, AGENTS.md compliant)

1. Deploy + restart:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Back-to-back: `fprintd-verify` twice within 30s, then once more after 3
   idle minutes. Paste:
   `journalctl -u fprintd --since "10 min ago" --no-pager | grep -a -E "USB reset|reset skipped|session reu|warm|TLS connection ready|verify-|timed out|failed" | tail -n 30`
   (exact reset log wording is the agent's choice; skipped-vs-taken MUST
   be visible as always-on lines).

### Predicted journal signatures

- **Confirm (revive 38/40):** second run shows reset-skipped + either
  `session reused` or `warm taken`, verifies correctly; third run (3 min)
  shows reset-taken + full ladder. Verdict: confirmed → close (38/40
  re-verify on the same build, no code changes).
- **Falsify (bury 38/40):** reset-skipped runs fail characteristically
  (FDT silence, garbage frames with full `declen`, TLS errors) while
  reset-taken runs pass. Verdict: falsified → restore unconditional
  reset, close 38/40 as infeasible-on-this-MCU per their own falsify
  clauses (delete warm path, keep full ladder + fragile-session
  assumption), do NOT widen any skip set.
- **Inconclusive:** finger-wait dominates, or daemon PID churned between
  runs 1–2 (idle-timeout exit kills in-memory clean flag — check PIDs in
  the paste). Verdict: `inconclusive-because-[flaw]` + rerun faster /
  with finger pre-placed.
