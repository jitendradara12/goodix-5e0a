# AGENTS.md — Goodix 27c6:5e0a driver repo

You implement; only the user has fingers sudo. Never run hardware
claims, or USB captures yourself — write the exact commands for the user.

## Lanes (do not cross without saying so)

- One variable per build. Frozen code needs a journal-backed reason.

## Tickets (`.scratch/goodix-5e0a/issues/NN-<status>-*.md`)

- Statuses: `ready-for-agent`, `ready-for-hardware-verify`, `in-progress`,
  `superseded` (+successor), `closed` (+verdict). `verified` requires a
  deployed-driver hardware run.
- The filename carries the status: `NN-<first-word-of-Status>-slug.md`
  (e.g. `26-ready-for-agent-*.md`, `18-closed-*.md`). Change the filename
  in the same edit as the `Status:` header — never one without the other.
  `ls *closed* *superseded*` shows permanent history; `ls *ready-for-agent*
*ready-for-hardware-verify* *in-progress*` shows the live workfront.
- Each experiment states predicted journal signatures per branch (confirm /
  falsify). Supersede, don't delete.

## Evidence standards

- Cite sources: journal lines, packet numbers, file bytes, command+output.
  "Verified on hardware" without pasted output doesn't count.

## Verify protocol (every hardware run, no exceptions)

1. Phase 1, hands off 60s ("hands off" + timestamp): silent vs cycles.
2. Phase 2, press-hold steady 60s ("holding" + timestamp): latency, advances.
3. Conclude only: confirmed / falsified /
   inconclusive-because-[flaw] + the single next experiment.

## Commands that actually work here

- Single test: `python3 -m unittest tests.tier1_feature.test_<name>` from
  repo root (`discover -s` has loader failures; don't "fix" the runner).
- Build drivers only: `/nix/store/6ji6bq0si2j8ibdrxqgcmh1cw0wmdiyk-ninja-1.13.2/bin/ninja -C /tmp/libfprint-goodix/build libfprint/libfprint-drivers.a libfprint/libfprint-2.so.2.0.0` (`ninja` isn't on PATH; full build dies at the unrelated `FPrint-2.0.gir` step).
- Full package: `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'` (needs the refreshed unified patch; check `git status` — a no-diff rebuild means untested identical code).
- Python USB scripts need fprintd stopped (else `Resource busy`) and repo-root imports: `PYTHONPATH=/home/sastauser/code/temp/goodix nix-shell -p python3Packages.pyusb openssl --run "python3 experiments/<script>.py"`.
- Never `pkill -f` a pattern containing your own command text (self-match hangs); list with `pgrep -af` and kill PIDs. Never rely on `timeout`-killed scripts having cleaned up their `s_server` children — verify ports (`ss -tlnp`) or use a fresh port per run.
- Deploy (user only): `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd && fprintd-enroll`.
- Debug via the service (`sudo systemctl set-environment G_MESSAGES_DEBUG=all`, unset after). Never a foreground daemon (loses the D-Bus race). `/etc/systemd` is read-only here.

## Journal cheat sheet

- `5e0a frame stats:` (always on): active/min/max/range/declen (+corr).
  Zeros + full `declen` = MCU ships blanks.
- `Running command: 0xNN` (debug env only): gaps distinguish waits from
  instant replies. `Failed to detect minutiae` (always on): extraction ran,
  found nothing. `fp_info`/`fp_dbg` need the debug env; `g_message` doesn't.
- `Transfer was cancelled…` at teardown is known debt, not signal.

## Rules to not face what's already solved

1. 0x32 FDT_DOWN is always timeout 0. It's a blocking capacitive interrupt, not a timed command (goodix.c:635 — 0 installs no timer). Any finite value turns idle finger-wait into Command timed out: 0x32. Never "harden" it with a watchdog; ticket 50 explicitly declined this. Bound comes from client timeout/deactivate, not the driver.
2. 0x34 FDT_UP is always finite (2000ms guard / 5000ms normal) with re-issue. Opposite semantics from 0x32: a 0x34 timeout means the finger is still down, never a release — re-issue, keep the guard. Success means genuine release — clear guard, arm FDT_DOWN. Mixing up the two commands' timeout meanings is the #1 source of burn bugs (ticket 47).
3. In deactivate, nothing the next claim depends on clears before the park early-return. retry_guard/mono clear on the destroy branch only (goodix5e0a.c:1187), never at function top. Generalize: any state with cross-claim TTL (guard 2s, park 30s, warm 60s) must survive an idle park. If you add new cross-claim state, put its reset on the destroy branch and say so in a comment.
4. Keep the rationale comment at every non-obvious site. The port stripped ticket comments ("blocking wait", "timeout means still down"), leaving bare code that looked like it needed hardening — which is exactly what broke it twice (203cfc8, 12e64db). One line naming the invariant beats a ticket number, but keep at least one.
5. CANCELLED never re-issues, always marks failed. Applies to every re-issue loop (0x32 poll, 0x34 guard, warm retry). Re-issuing on cancel resurrects orphaned SSMs against freed state.
6. Check .scratch/goodix-5e0a/issues/ for settled facts before changing driver behavior. Both regressions were re-litigations of closed tickets (13, 43, 47, 49, 50). If a ticket says "do not re-litigate without new hardware evidence," believe it.
7. Smoke every driver change with two journal greps. After deploy: grep -E "timed out|Invalid ACK|verify-unknown-error|failed to" must be empty on an enrolled tap, and the held-wrong-finger test must show exactly one Failed to match with attempts withheld (~18s re-issuing FDT UP loop) until lift. If either fails, revert before stacking more fixes. (Reading notes from ticket 53: scope the first grep to the serving instance's match-claim window — `0x34 timed out` tolerant lines during a held-finger test are the designed ticket-47 path, not failures; and the literal string `Failed to match` exists nowhere in this stack, so its observable equivalent is exactly one `verify-no-match` result with a single completion.)
