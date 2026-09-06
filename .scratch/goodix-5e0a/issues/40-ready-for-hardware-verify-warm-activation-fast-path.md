# 40 — Warm activation fast path (skip redundant reset/config when warm)

**What to build:** When the previous activation on this boot completed
cleanly and recently (warm window, proposed 60s), skip `ACTIVATE_RESET`
and config re-upload and go straight to firmware-check → TLS. Any
deviation (failed last activation, suspend/resume since, TTL expired,
health-check miss) takes today's full ladder. One variable: ladder length
on warm re-entry. Ticket 38 owns cross-claim session reuse; this ticket
owns the cold-session-but-warm-device shortcut — the two compose (38-hit
skips everything, 38-miss-but-warm lands here, else full ladder).

**Blocked by:** None. Smaller win than 38 by construction (saves reset +
config round-trips, not the handshake); do 38 first if forced to order.

**Status:** ready-for-hardware-verify

**Live-scope:** ladder-skipping logic + warm-state bookkeeping only. No
transport changes, no biometric changes, no suspend-path changes (suspend
always resets warm state — sleep safety is not negotiable).

## Settled facts (do not re-litigate)

1. Ticket 33 measured ~1s activation; reset + config upload are pure
   round-trips with no discriminating power on a device that just proved
   itself seconds ago. Their only function is cold-state repair.
2. Config drift is the falsifier to watch: if the MCU ever needs the
   re-upload to behave (firmware quirk, partial state), warm attempts will
   fail characteristically (FDT silence, decode garbage) while full-ladder
   attempts pass. The fallback MUST be automatic on first warm failure,
   not a user-visible retry.
3. Update-3/4 constraint applies: warmth is about the HOST's recent
   success, never a claim about device key state — the TLS handshake (kept
   in this path) plus the new accept-failure gating remain the key-state
   arbiters. This ticket never skips the handshake.

## Hardware verify protocol (user only, AGENTS.md compliant)

1. Deploy + restart:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Back-to-back: `fprintd-verify` twice within 30s (second SHOULD take the
   warm path), then once more after 3 idle minutes (SHOULD take full
   ladder). Paste:
   `journalctl -u fprintd --since "10 min ago" --no-pager | grep -a -E "warm|ACTIVATE|Reset|config|TLS connection ready|verify-" | tail -n 30`

### Predicted journal signatures

- **Confirm (close ticket):** second run shows warm-path lines, no reset/
  config round-trips, verifies correctly, measurably faster than run 1;
  third run shows full ladder again. Verdict: confirmed → close (tune the
  TTL as follow-up only with data).
- **Falsify:** warm runs fail (FDT silence, garbage frames, TLS errors)
  while full-ladder runs pass, OR no measurable time delta (round-trips
  were never the bottleneck — attention returns to 38). Verdict:
  falsified → next lane is deleting the warm path and keeping full-ladder
  always, NOT widening the skip set.
- **Inconclusive:** finger-wait dominates all three runs (late placement).
  Verdict: `inconclusive-because-[flaw]` + rerun with finger pre-placed.

## Hermetic verification (agent-run 2026-09-06, no hardware)

- Implemented: 3-way branch in dev_activate (38-park → warm → full ladder);
  warm ladder READ_AND_NOP → CHECK_FW_VER → TLS via jump_to_state (no reduced
  enum); `boot_seq` counter + 60s TTL; silent once-per-claim full-ladder
  fallback at both error funnels; suspend clears warmth.
- `python3 -m unittest tests.tier1_feature.test_f40_warm_activation` — 8/8
  green. Driver ninja build green.
- Full suite green: 425 passed, 0 failed. Patch re-rolled
  (`3c4ed07efaf254885eb62146e017e458384a13d0ce8955fdaeee1ceef56c261c`,
  repo + NixOS module copies identical); LOC budget 1350 (measured 1334).
- NO speedup claimed — run-2-vs-run-1 delta is hardware-only.

## Hardware finding 2026-09-07 (warm branch not exercised)

- Every warm-filtered line shown was `warm expired: reason=cold-start`; no
  `warm taken` line appeared. The observed `TLS session reused` lines belong
  to ticket 38's earlier branch and correctly dominate ticket 40.
- Verdict: `inconclusive-because-warm-branch-not-exercised`.
  Next experiment: issue the next claim 31–59 seconds after a clean claim,
  while confirming the same fprintd PID remains alive, so the 30-second park
  TTL expires while the 60-second warm TTL remains valid.

## Hardware finding 2026-09-06 (falsified-as-implemented, corroboration pending)

- Every claim logs `warm expired: reason=cold-start`, including 4–6s-apart
  claims inside one fprintd PID (147364, 22:00:36→22:01:41). No `warm
  taken` line ever. The ticket's own step-3 (3-min run) is MOOT until the
  root cause is addressed — skip it.
- Root cause (code): `goodix_dev_init` (`img_open`) does
  `priv->boot_seq++` on every per-claim open, guaranteeing predicate
  mismatch; the ticket-40 comment claiming open "brackets the whole open
  session, not each verify" is falsified by this journal. Same killer as
  ticket 38 (the open-path USB reset).
- Successor: ticket 42 (conditional USB reset). If 42 confirms, this
  ticket re-verifies with ZERO code changes. Formal close verdict after
  corroboration.
