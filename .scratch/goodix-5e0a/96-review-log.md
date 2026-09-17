# Ticket 96 review loop

Scope: portability changes from `a69296560771f332436d15c7506aa64a5a197e70`
to commit `b4eae76`, two reviewer rounds.

Ground rules: findings need evidence, not consensus; hardware claims stay out;
no sudo/deploy/push during review.

## Round 1 — findings and dispositions

| Finding | Verdict | Action |
|---|---|---|
| PAM not actually opt-in (NixOS defaults fprintAuth to fprintd.enable) | **Accepted** (3 reviewers, eval-proven) | Module sets explicit `fprintAuth = mkDefault cfg.pamServices`; eval test asserts effective login/sudo PAM for both option values |
| Default NixOS import ignores the committed DLL | **Accepted** (eval-proven: `dll: null`) | `dllFile` defaults to bundled DLL; passed via `GOODIX_ENGINE_DLL_PATH` env, not copy-once tmpfiles |
| Changing `dllFile` left old engine active (tmpfiles `C` semantics) | **Accepted** (tmpfiles.d(5) documented) | Same fix: store-path env var follows config changes and rollbacks |
| Shipped libfprint rules file empty for 5e0a (hwdb gen disabled) | **Accepted** (found in built toplevel) | Module ships own rule; `udevadm verify` passes on built system |
| Installer grants world-writable sensor (MODE=0666) | **Accepted** | 0660 + uaccess in module; private-prefix installer changes no USB perms |
| Installer missing C++ compiler deps (upstream meson requires cpp) | **Accepted** (upstream meson.build checked) | g++ / gcc-c++ added to apt/dnf/zypper branches |
| Installer: no rollback, global /usr/local libfprint replacement, ldconfig override | **Accepted** | install.sh rewritten: unprivileged build, /opt prefix, service-scoped drop-in, ownership-validated uninstall, rollback tests |
| README documented `sudo ./install.sh` but script refuses root | **Accepted** (self-caught) | README corrected |
| fprintd CLI package + libpam-fprintd gap on Debian/Ubuntu | **Accepted** | README documents per-distro PAM steps |
| flake.lock missing (nixpkgs input unpinned) | **Rejected for now** — module consumers use host pkgs; package pin is the libfprint fork rev. Revisit before calling the flake hermetic |
| Non-NixOS installer still lacks `--no-timeout` override | **Accepted as disclosure** — completion message states it; behavioral fix deferred until a second hardware setup can verify latency impact |
| Installer not exercised against a clean distro image | **Limitation, documented** — README + completion message say end-to-end is unverified |
| "Enough reviewers" / tracker-setup meta-suggestions | **Rejected** — no code content |

## Verification chain (executed, not claimed)

- `bash tests/run_all_tests.sh`: 372/372, 1 skip (tiers 1/4/5 + Nix eval preflight incl. new module eval test)
- `nix-instantiate --eval --strict tests/tier1_feature/test_f96_nixos_module.nix`: true (DLL default/custom/null, PAM off/on, udev rule 0660, no 0666)
- Full NixOS `system.build.toplevel` built twice with the module; inspected: drop-in has GOODIX_ENGINE_DLL_PATH + `--no-timeout`; sudo PAM has 0 fprintd lines when `pamServices=false`; rule present and `udevadm verify` clean
- `python3 -B tests/fixtures/install/test_install.py`: 7/7
- fprintd + patched libfprint derivations actually compiled in the Nix sandbox

## Still unverified (honest limits)

- Non-NixOS end-to-end install on real hardware (any distro)
- Actual daemon library loading (`/proc/<pid>/maps`) — linker-cache check was removed with the old approach; new approach scopes loading via service env, unproven until deployed
- Second-unit PSK/DAC behavior (per-unit scope, ticket 59)
- The 2-phase hardware protocol on the user's unit

Reviewer independence caveat: round-1 reviewers were subagents that had
authored parts of the change; the fixes above are the response to their
findings, and hardware deployment remains the definitive check.
