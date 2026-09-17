# 88: Keep fprintd resident for the 300s TLS park

**Status:** closed

**Verdict:** confirmed on deployed hardware, 2026-09-17; evidence below.

**Blocked by:** User deployment and the targeted 90s hardware probe. Blocks hardware acceptance of 85.

## Mechanism and evidence

fprintd 1.94.5 exits itself after 30s with no busy devices. This is not a
systemd idle-stop setting. Busy means clients present or device temperature
above cold. Last-client departure explains the observed delay here.

Exact source: `/nix/store/173497h2nmqysyp6jj0il96fy5hb72vz-source`, the src
input of `/nix/store/h9j09h8wdmdc4s3qz0sx2wb2fi5qddkk-fprintd-1.94.5.drv`.
`nix-store --query --deriver` and `nix derivation show` connect it to deployed
`/nix/store/8jkiyn4gjry62n92vl6h9cmvbblrklqd-fprintd-1.94.5`.

- `src/fprintd.h:29`: `TIMEOUT 30`.
- `src/manager.c:158-164`: timer callback calls `exit(0)` without logging.
- `src/manager.c:176-198,532-533`: timer cancellation/re-arm and startup arm.
- `src/device.c:298-301,1000-1023`: busy definition and client notifications.
- `src/main.c:41,123,211`: default timeout enabled; supported opt-out is
  `--no-timeout`, described as "Do not exit after unused for a while".
- Installed `etc/fprintd.conf` only selects storage. Installed binary
  `--help` listed `-t, --no-timeout` and exited 0 before bus/device access.

`/home/sastauser/goodix-ticket87-20260916-233440/journal.txt`:

- PID 21957 parks at 23:39:14.076166, line 354; release completes at
  23:39:14.076257, line 359; successful deactivation at 23:39:44.003460,
  line 360. Park-to-exit is 29.927294s.
- PID 20638 last close activity at 23:35:41.080196, line 164; successful
  deactivation at 23:36:10.979237, line 165. Gap is 29.899041s.
- No Exiting, main-loop-completed, name-loss, or service-stopping message
  accompanies the exit. Full stop sequence and grep are recorded in 85.

The callback destroys in-process TLS regardless of the driver's 300s TTL.

## Implementation, 2026-09-17

One behavior variable: append `--no-timeout` to the service command.
Driver, patch, timeout constants, and package selection are unchanged.
Both `nixos-module.nix` and
`/home/sastauser/NixOS-Hyprland/modules/goodix/default.nix` now contain:

```nix
  # The daemon's 30s idle exit destroys parked TLS before the driver's 300s TTL.
  # Reset the packaged unit's ExecStart in the NixOS drop-in, then keep it resident.
  systemd.services.fprintd.serviceConfig.ExecStart = [
    ""
    "${config.services.fprintd.package}/libexec/fprintd --no-timeout"
  ];
```

The empty entry is necessary here, not a guessed workaround. The actual
flake's `serviceConfig` was `{}` before this edit. Nixpkgs' fprintd module
imports the package through `systemd.packages`; its ExecStart lives in the
packaged unit, outside Nix option merging. Evaluation gives unit strategy
`asDropinIfExists`. The generated drop-in contains exactly:

```ini
ExecStart=
ExecStart=/nix/store/8jkiyn4gjry62n92vl6h9cmvbblrklqd-fprintd-1.94.5/libexec/fprintd --no-timeout
```

After systemd applies the reset there is one effective command. No
`mkForce` is needed: there was no competing Nix ExecStart definition.
The command uses `config.services.fprintd.package`, retaining the custom
Goodix-linked package and its unchanged derivation above.

## Non-hardware validation

From `/home/sastauser/NixOS-Hyprland`:

```bash
nix eval --json .#nixosConfigurations.sastapc.config.systemd.services.fprintd.serviceConfig.ExecStart
nix eval --raw '.#nixosConfigurations.sastapc.config.systemd.units."fprintd.service".text'
nix eval --raw .#nixosConfigurations.sastapc.config.services.fprintd.package.drvPath
```

All exit 0. Output is the reset/command above and unchanged package drv.
An additional Nix assertion checked the exact ExecStart list, the drop-in
strategy and exactly two generated ExecStart lines. It returned unit drv
`/nix/store/fr4ap4rd803gacgaw6wh7vamyn9j7a9d-unit-fprintd.service.drv`.
This evaluates the real dirty flake without deployment or rebuilding fprintd.

From repo root:

```bash
bash -n scripts/verify-ticket88.sh
python3 /tmp/opencode/check-ticket88.py
git diff --check
```

Syntax and whitespace checks exit 0. The temporary mocked check replaces
sudo, systemctl, timeout, sleep and journalctl, never touching hardware:

```text
match: PASS (exit 0)
no-match: PASS (exit 0)
absent: PASS (exit 1)
timeout: PASS (exit 1)
bad: PASS (exit 1)
dead: PASS (exit 1)
```

It checks unfiltered journal capture on every exit, debug cleanup, acceptance
of completed no-match, rejection before claims when the flag is absent,
timeout failure, and one requested `sleep 90` between PID snapshots. Mock
sleep does not establish real timing; that belongs to the user run below.
No driver tests were rerun because no driver or test code changed.

## User-only deployment and one-paste probe

No deployment or hardware verification has been performed by the agent.
User deployment, only when ready:

```bash
cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .#
```

Then run the targeted probe with this one paste:

```bash
bash /home/sastauser/code/temp/goodix/scripts/verify-ticket88.sh
```

The script checks the loaded unit flag before restarting the managed service
with debug enabled. It makes two bounded one-shot claims separated by an
actual `sleep 90`, records wall-clock timestamps and daemon PID snapshots
before/after sleep and after the second claim, and saves the unfiltered
journal even on failure. First match OR completed no-match is normal;
client timeout is a clear failure. Lift after each claim, avoid other
authentication and suspend throughout the gap. It unsets the debug manager
environment on exit and never launches a foreground daemon.

Use AGENTS.md's already-verified exception: ticket 87 records the prior
hands-off, steady-hold and PAM evidence, including
`goodix-ticket87-20260916-233440` phases and the scoped wrong-finger hold.
Do not repeat those phases for this service-only change. This probe does
not newly prove PAM retry withholding.

## Predicted journal signatures and verdict

- Confirm daemon survival: same nonzero PID across the 90s gap and second
  claim, with no intervening successful deactivation. For 85, the second
  claim must also show `5e0a parked TLS session candidate fresh, health-checking`
  without a full handshake. Measure activation latency from the journal;
  matching alone does not prove reuse or the <15ms criterion.
- Falsify daemon survival: verified flag present but daemon disappears or
  changes PID during idle. The script stops before another claim if so.
- Falsify park reuse, not daemon survival: same PID but second claim logs
  expired/unhealthy park or full cold bring-up. Retain the full journal.
- Inconclusive-because-[flaw]: missing flag, client timeout/error, suspend,
  another claim during idle, or missing journal access. Do not infer success.

## Hardware result 2026-09-17: confirmed

Evidence: `/home/sastauser/goodix-ticket88-20260917-110502/`.
`before-idle.txt`, `after-idle.txt`, and `after-second.txt` show active PID
12821 throughout. `phases.txt` records an actual 90-second wait.

Pasted from `journal.txt`, all under PID 12821:

```text
192 11:05:03.570958 5e0a parking live TLS session (gen=2)
202 11:06:33.732012 5e0a USB reset skipped (clean close, boot_seq=1)
222 11:06:33.744226 5e0a parked TLS session candidate fresh, health-checking (gen=3)
228 11:06:33.744799 5e0a TLS session reused (parked 90.2s, gen=3)
235 11:06:33.757996 Chip enabled! Activation complete.
251 11:06:33.771981 Running command: 0x32
305 11:06:36.974374 report_verify_status: result verify-no-match
320 11:06:36.976155 5e0a parking live TLS session (gen=4)
```

First claim matched at line 177. Second claim completed no-match and parked
again; no second handshake occurred. A grep of the full journal for
`timed out|Invalid ACK|verify-unknown-error|failed to` returns no matches.

Verdict: confirmed for service survival and parked reuse across 90s idle.
Ticket 85 still owns the unmet <15ms FDT_DOWN target and untested >300s
expiry/fallback. Single next experiment, if continuing that ticket: a
controlled >300s idle pair on this unchanged build. No further service change.

## Rollback

User removes the ExecStart override from the imported module and rebuilds.
The stock 30s idle exit returns. No fingerprint templates are changed.
