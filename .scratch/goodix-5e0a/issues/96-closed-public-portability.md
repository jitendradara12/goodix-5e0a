# 96: Make the repo public-usable (unhardcode + any-distro install)

**What to build:** A stranger with a Realme Book Prime (Goodix 27c6:5e0a) on any
distro can clone the repo and get working fingerprint login, without touching
the developer's paths or hand-editing anything. Driver behavior is unchanged.

**Blocked by:** None.
**Status:** closed

**Verdict:** confirmed for NixOS flake deployment and Fedora operation after
manual setup on the tested laptop. Stock Fedora installation exposed the
SELinux and desktop-integration gaps now owned by tickets 98 and 99.
Closure does not claim those fixes have shipped or that every distro works.
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
- [x] NixOS module deployed; hands-off observation and successful CLI match
      recorded below. Repeated waits waived by the user; detailed timing and
      continuous-hold retry claims remain unverified.
- [x] Non-NixOS installer exercised on Fedora 44 Enforcing. Enrollment,
      matching and desktop login worked after manual SELinux/PAM setup.
      Clean-install fixes transferred to tickets 98 and 99.

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

## Hardware run record, 2026-09-17 19:16–19:19 IST (deployed-driver mismatch)

- Daemon: PID 29796 since 17:29:20, `/nix/store/8jkiyn4gjry62n92vl6h9cmvbblrklqd-fprintd-1.94.5`
  with `/nix/store/q2qbsdmcjcz8zkcffywyfbyyrmdi9h08-libfprint-goodix-1.94.5-goodixtls-5e0a`.
  `strings` on the deployed `.so` still contains
  `/home/sastauser/goodix-27c6-5e0a-re/drivers/GoodixEngineAdapter.dll`;
  repo HEAD `goodix_milan.c:867-870` no longer does. Service env has no
  `GOODIX_ENGINE_DLL_PATH`; deployed udev rule is still `MODE="0666"`.
  Conclusion: the running driver predates ticket 96. This run exercises the
  sensor path, not the new module/env/0660 wiring.
- Software re-check this session: `test_f96_public_portability` 5/5,
  `test_f25_patch_sync` 9/9, `bash -n install.sh` clean, `nix flake show`
  succeeds (transient `flake.lock` removed afterwards).
- Phase 1, hands off 19:16:11 IST 20s: `-- No entries --` (silent, no cycles).
  Matches predicted silent signature.
- Phase 2, first attempt holding 19:16:36: cold-start activation
  (`reason=cold-start`), start-verification 19:16:36.755 → `0x32` send
  19:16:37.182 (~427 ms, in line with ticket 93 cold 429–431 ms envelope),
  then finger-wait 29 s with no touch → idle cancel, `verify-no-match`.
  No-touch, so no latency verdict from this attempt.
- Phase 2 retry, user holding, 19:19:33.786 start-verification →
  `0x32` send 19:19:34.213 (~427 ms cold) → touch confirmed 19:19:34.274
  (`mask=0x3f energy=1291`, ~61 ms finger-wait) → 4/4 frames
  (range 2136–2141, overlap 45–46) → Milan `match=0 pts=0 (threshold=50)` →
  `verify-no-match (done)` at 19:19:34.470. Total start-to-verdict ~684 ms.
  Advances on retry confirmed; latency envelope reproduced.
- Verdict for ticket 96: **inconclusive-because-deployed-driver-predates-96**.
  The 2-phase journal signatures reproduce on the old deployment, but the
  NixOS module deployment (`GOODIX_ENGINE_DLL_PATH` + 0660 rule) and the
  non-NixOS `/opt` installer remain unverified on hardware.
- Single next experiment: rebuild the system with the repo's
  `nixosModules.default` imported (`dllFile` default + `pamServices` as
  desired), `nixos-rebuild switch`, confirm service env + 0660 rule +
  `/proc/<pid>/maps` engine load, then repeat the 20 s hands-off / press-hold
  protocol.

## Flake deployment run, 2026-09-17 20:44 IST

Evidence: `/home/sastauser/goodix-96-IYhLJP/verify.txt` and `journal.txt`.

- New daemon PID 142558 started at 20:36:03 with fprintd store prefix
  `5ip2mch72x054ra4pd5s31y5453c563g`, `--no-timeout`, and
  `GOODIX_ENGINE_DLL_PATH=/nix/store/0wajf7zqw9y995hcqf9h2rwszzqmg8y0-source/windows_driver/GoodixEngineAdapter.dll`.
  `/etc/udev/rules.d/99-local.rules` now specifies 0660 + uaccess.
  The startup journal at 20:36:54.961772 records successful engine loading,
  version `Milan_v_3.02.00.20`. No process maps inspection was performed.
- Test requested `left-middle-finger`. The script printed hands-off and
  holding timestamps to the terminal but did not save them. Exact phase
  boundaries therefore cannot be recovered from the evidence folder.
- Saved journal: cold activation at 20:44:57.853482, TLS ready at
  20:44:58.190617, then no entries until touch at 20:45:18.357783.
  No pre-touch image captures or repeated scan cycles appear. This supports
  the hands-off prediction but is not a timestamped phase-boundary proof.
- Touch triggered four frames and best-frame submission at 20:45:18.528936,
  about 171 ms after logged touch detection. The client returned
  `verify-no-match (done)`. This is not a successful fingerprint match.
- Debug action-start, command-send and Milan score markers are absent.
  Ticket 93 activation timing and retry behavior cannot be verified from
  this capture. The client ended on its first decision, so the remaining
  hold window did not test ongoing retries.
- Deployment wiring and sensor capture: confirmed on this NixOS unit.
  Full ticket verdict: **inconclusive-because-no-successful-match-and-missing-timing-markers**.
  Non-NixOS installation remains untested. Status stays ready-for-hardware-verify.
- Single next experiment: repeat the same two-phase claim with the operator
  explicitly confirming left-middle-finger, saving phase timestamps and
  enabling temporary service debug logging before the measured window.
  Confirm with no hands-off captures, successful matching, and complete
  activation markers; a genuine no-match falsifies success for that attempt;
  missing markers leave the timing comparison inconclusive.

## Successful verification after flake deployment, 2026-09-17

The user repeated `fprintd-verify -f left-middle-finger` and supplied the
terminal result `verify-match (done)` with exit code `0`. The repeated
20-second waits were omitted at the user's request, reusing the preceding
hands-off observation. No restart or configuration change was requested
between these attempts. This result is user-supplied terminal evidence,
not a newly collected journal timing measurement.

Verdict: **confirmed** for NixOS flake deployment and a successful
left-middle-finger verification on this unit. This supersedes the earlier
no-successful-match limitation. Activation timing, repeated-hold retries,
PAM login and population matching reliability are not established by this
successful CLI attempt.

The ticket stays ready-for-hardware-verify for the untested non-NixOS
installer. Single next experiment: run `./install.sh` as a normal user on
one supported non-NixOS distribution with compatible hardware, then verify
that fprintd loads the private driver and completes a fingerprint match.
Confirm with the intended library/DLL loading and `verify-match`; falsify
that setup's installation claim if installation or activation fails.

## Fedora follow-up, 2026-09-17

Reviewed the Fedora records committed in `e07843b`, `4cc81be` and
`3d41cab`. Ticket 98 records Fedora 44 Enforcing, the private `/opt`
installation, successful engine loading, completed enrollment and a match
with PID 12989 after a manually installed SELinux policy. Ticket 99 records
manual installation of `fprintd-pam` and authselect configuration, followed
by the Settings row appearing and desktop login working. The user also
confirmed that matching and PAM worked after the initial setup problems.
These are the Fedora session's recorded results and the user's report, not
new Fedora tests performed by this session.

Verdict: **confirmed** for Fedora operation after manual SELinux and PAM
setup. The installer-only path is **falsified** on the recorded stock
Fedora 44 Enforcing setup: engine loading failed until the local policy
was installed. The earlier statement that non-NixOS operation was entirely
untested is superseded by these results. Neither workaround is yet shipped
by the repo; tickets 98 and 99 own those remaining changes. Ticket 96 stays
open for that clean-install gap, not for another matching or PAM retest on
the already working setup.

Single next experiment: after ticket 98 ships its SELinux fix, test a clean
Fedora 44 Enforcing installation without the manually installed workaround
policy. Confirm with engine loading, enrollment and matching; falsify with
recurring loader failures and corresponding AVC denials.

## Decisions (user, 2026-09-17)

- DLL stays committed ("nobody is filing a case on me") — prominent README
  disclaimer instead of removal.
- Repo stays whole: .scratch/, legacy-experiments/, AGENTS.md all ship. No
  splitting, no sanitizing.
- Target: Realme Book Prime. Dual-boot DLL steal is the documented acquisition
  path; vendor-installer extraction mentioned as alternative.
- First-party Nix; everyone else gets install.sh (no AUR/COPR/PPA).

## Closure, 2026-09-17

Closed at the user's request. This supersedes the earlier decisions to keep
96 open for the Fedora clean-install gap. Tickets 98 and 99 already own
that work; no duplicate implementation or hardware checkpoint remains here.
No new hardware run was performed for closure. The single next experiment
remains the clean Fedora Enforcing install after the ticket 98 fix ships,
using the confirm/falsify signatures in the Fedora follow-up above.
