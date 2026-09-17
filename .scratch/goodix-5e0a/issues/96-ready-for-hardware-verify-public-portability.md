# 96: Make the repo public-usable (unhardcode + any-distro install)

**What to build:** A stranger with a Realme Book Prime (Goodix 27c6:5e0a) on any
distro can clone the repo and get working fingerprint login, without touching
the developer's paths or hand-editing anything. Driver behavior is unchanged.

**Blocked by:** None.
**Status:** ready-for-hardware-verify
**Owns:** Loader search paths, patch sync, install.sh, flake.nix, NixOS module
options, README rewrite, LICENSE, .gitignore hardening, portability test lane.

Predicted signatures (software branch, confirm/falsify):
- `test_f25_patch_sync` green after the goodix_milan.c edit and patch
  regeneration → the patch still byte-embeds driver sources.
- New tier1 portability test green: no `/home/sastauser` in driver/patch/
  install.sh/flake.nix; DLL search paths agree between .c and patch.
- `nix flake show` succeeds; `bash -n install.sh` clean.
- Hardware branch (later, hands-on): deploy via the NixOS module on NixOS,
  or test `sudo ./install.sh` on a supported non-NixOS distribution. A working
  activation and verification supports compatibility only for that tested setup.
  TLS failure on a second unit is inconclusive about PSK scope without further
  diagnosis; it does not establish that the key differs.

Predicted journal signatures (hardware verify phase, per protocol):
- Hands off 20s: silent, no cycles.
- Press-hold 20s: verify latency in line with ticket 93 baseline, advances on
  retry.

- [x] Kill `/home/sastauser/...` DLL fallback in goodix_milan.c + patch sync.
- [x] Distro-neutral install.sh (deps, pinned fork clone, meson build,
      udev, DLL to /var/lib/fprint, ldconfig).
- [x] flake.nix entry point + opt-in PAM / dllFile options in NixOS module.
- [x] README rewrite (honest limits: 12 stages, suspend defect, 0/2 batch,
      per-unit PSK/DAC scope) + LICENSE (LGPL-2.1) + vendor-binary disclaimer.
- [x] .gitignore: never-commit section for tpl/exe/pnf/cat/psk/dpapi artifacts.
- [x] Portability regression test (tier1).
- [x] Full suite green after all agents land: `bash tests/run_all_tests.sh`
      → 372/372 passed, 0 failed, 1 skip; NixOS module eval wired into the
      suite preflight. Independent review round accepted and fixed: real PAM
      opt-in, bundled-DLL default via service env, 0660+uaccess USB rule
      (shipped rules file is empty for 5e0a), rewritten /opt installer with
      rollback + uninstall, C++ deps. Evidence chain in
      `.scratch/goodix-5e0a/96-review-log.md`.
- [ ] Hardware verify: NixOS module deployment + 2-phase protocol.
- [ ] Non-NixOS installer: end-to-end run on a supported distribution.

## NixOS installer follow-up

The user ran `sudo ./install.sh` on NixOS following the agent's incorrect
verification instructions. It exited with `no supported package manager found`
before package installation. The preceding fingerprint prompts came from sudo;
the transcript does not establish a successful fingerprint match.

The installer now detects NixOS before root/DLL checks and temporary staging,
and directs users to the NixOS module. README links to that installation path.
The portability suite passed all five tests, including executing the real
installer unprivileged on NixOS from an empty directory with a missing DLL.
No deployment or hardware verification was performed for this fix.

## Decisions (user, 2026-09-17)

- DLL stays committed ("nobody is filing a case on me") — prominent README
  disclaimer instead of removal.
- Repo stays whole: .scratch/, legacy-experiments/, AGENTS.md all ship. No
  splitting, no sanitizing.
- Target: Realme Book Prime. Dual-boot DLL steal is the documented acquisition
  path; vendor-installer extraction mentioned as alternative.
- First-party Nix; everyone else gets install.sh (no AUR/COPR/PPA).
