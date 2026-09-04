# AGENTS.md — Goodix 27c6:5e0a driver repo

You implement; only the user has fingers sudo. Never run hardware
claims, or USB captures yourself — write the exact commands for the user.

## Lanes (do not cross without saying so)

- One variable per build. Frozen code needs a journal-backed reason.

## Tickets (`.scratch/goodix-5e0a/issues/NN-*.md`)

- Statuses: `ready-for-agent`, `in-progress`, `superseded` (+successor),
  `closed` (+verdict). `verified` requires a deployed-driver hardware run.
- Each experiment states predicted journal signatures per branch (confirm /
  falsify). Supersede, don't delete.

## Evidence standards

- Cite sources: journal lines, packet numbers, file bytes, command+output.
  "Verified on hardware" without pasted output doesn't count.
- Score images by metrics (column energy, correlation, orientation), never
  by looks. `README.md` is aspirational — several claims there (FDT working,
  minutiae counts, match scores) are unproven; trust journal/pcap, not prose.
- Any capture/analysis harness must pass its own control first (stale
  `openssl s_server` processes squat on ports and poison later runs; pipe
  buffering eats sub-8K output). Uncontrolled harness output is void.

## Verify protocol (every hardware run, no exceptions)

1. Phase 1, hands off 60s ("hands off" + timestamp): silent vs cycles.
2. Phase 2, press-hold steady 60s ("holding" + timestamp): latency, advances.
3. Paste client lines plus `journalctl -u fprintd --since "N min ago"
--no-pager | grep -a -E "5e0a frame|timed out|error|failed|minutiae" |
tail -n 20`. Conclude only: confirmed / falsified /
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

## Live edge

Transport/activation/TLS proven and frozen. Active experiments, findings,
and hardware run logs belong in tickets (`.scratch/goodix-5e0a/issues/NN-*.md`)
and `docs/`, never in `AGENTS.md`. Refer to the open ticket for current status.
