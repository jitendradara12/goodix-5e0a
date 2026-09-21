# 99: Fedora desktop integration missing — no fprintd-pam / authselect / Settings row

**What to build:** A Fedora user who runs `install.sh` successfully and enrolls via `fprintd-enroll` still gets no desktop integration: no Fingerprint Login row in GNOME Settings > Users, no GDM/login/sudo fingerprint. Make the repo either wire it up or document/detect it so "enroll works but Settings shows nothing" stops being a surprise.

**Blocked by:** None (98 is the daemon-side counterpart; this is the session-side counterpart).
**Status:** closed
**Owns:** `install.sh`, README (Fedora section), portability test lane. No driver changes.

## Observed on failing setup (2026-09-17, sastalinux, Fedora 44, GNOME)

- Daemon side healthy after 98 workaround: `fprintd-list sastauser` shows `right-index-finger`, D-Bus `GetDevices → /net/reactivated/Fprint/Device/0`, `fprintd-enroll: enroll-completed`, `fprintd-verify: verify-match`.
- Session side empty:
  - `rpm -q fprintd-pam` → `package fprintd-pam is not installed`
  - `authselect current` → Profile `local`, features `with-silent-lastlog, with-mdns4, with-pam-gnome-keyring` — no `with-fingerprint`
  - `grep -r pam_fprintd /etc/pam.d/` → empty
  - GNOME Settings > Users → no fingerprint section (control-center 50.3, gdm 50.1, GNOME session confirmed via `XDG_CURRENT_DESKTOP=GNOME`).
- Root cause: `install.sh` explicitly does "no PAM changes" and only installs `fprintd`, not `fprintd-pam`. README lists the Fedora `authselect enable-feature with-fingerprint` step as manual opt-in, so a user following only the installer hits a working CLI + invisible desktop.

## Predicted signatures (software branch, confirm/falsify)

- Confirm (docs/detect fix): fresh Fedora `install.sh` run prints a PAM gap warning naming `fprintd-pam` + `authselect enable-feature with-fingerprint`; README Fedora section lists the exact 3 commands + reboot + Settings path; tier1 test asserts the warning text and package list.
- Confirm (full fix, if maintainer picks installer-managed PAM): `install.sh` installs `fprintd-pam`, enables the feature, `authselect current` shows `with-fingerprint`, `grep pam_fprintd /etc/pam.d/{gdm-password,login,sudo}` non-empty, Settings row appears after relogin.
- Falsify: installer claims "ready" with no PAM mention and Settings row still missing on a GNOME/Fedora box with a working `fprintd-list`.
- Inconclusive-because-[flaw]: tested on NixOS (PAM managed by the module, different path) or on non-GNOME desktops without noting it.

## Suggested fix directions (maintainer picks)

- **A (minimum, docs + detect):** keep PAM opt-in but make it unmissable — `install.sh` post-install echo + `install.sh --check` probe: `rpm -q fprintd-pam`, `authselect current | grep with-fingerprint`, `grep pam_fprintd /etc/pam.d`. README Fedora block becomes copy-paste:
  ```bash
  sudo dnf install -y fprintd-pam
  sudo authselect enable-feature with-fingerprint
  sudo authselect apply-changes
  ```
  plus "log out/in, then Settings > Users > Fingerprint Login; keep a password session open."
- **B (full):** `install.sh --with-pam` (Fedora/RHEL only) performing A + `authselect` enable, with rollback in `--uninstall`. Needs explicit PAM-backup + "keep password session" guardrails; out of scope for Debian/Arch paths.
- Either way: tier1 test covering the new warning/flag text; never silently mutate PAM on a default install.

## Acceptance

- [ ] Fresh Fedora GNOME box: documented path ends with visible Settings row + GDM fingerprint prompt, or installer states why not.
- [ ] `bash tests/run_all_tests.sh` green including the new PAM-lane test.
- [ ] Hardware verify: enroll via Settings (not just CLI) + `verify-match`, record `authselect current`, `rpm -q fprintd-pam`, Settings screenshot/description.

## Agent implementation record, 2026-09-17 (software branch, option A)

- `install.sh` now prints the PAM gap unmissably on every install and
  `--check` run: missing `fprintd-pam` (rpm probe) and missing
  `with-fingerprint` (authselect probe), each with the exact distro
  commands from the "Suggested fix directions" A block. No automatic PAM
  mutation anywhere (B was not taken); default install still never edits
  PAM. Non-authselect distros get the generic pam_fprintd guidance.
- README "PAM / desktop integration" section is copy-paste per distro,
  with the Settings row + relogin note and "keep a password session open".
- tier1 `test_f100_installer_flags.py` covers `--check` behavior and flag
  documentation; full suite 362/362 green.
- Pending hardware item: enroll via GNOME Settings on a real Fedora GNOME
  box with `rpm -q fprintd-pam` + `authselect current` recorded. The
  existing manual-workaround record below covers the commands themselves.

## Hardware verify record, 2026-09-17 (manual workaround, not repo fix)

- User ran the 3-command `fprintd-pam` + `authselect` block manually; Settings row appeared and desktop login worked. No repo changes were exercised — this ticket stays open until A or B lands.

## Notes

- Do not commit local `fprintd-goodix.pp/.te` from ticket 98 alongside this work; they are host-specific workaround artifacts (currently untracked in repo root).
- NixOS path already manages PAM via `pamServices`; keep the two paths consistent in wording but separate in code.

## Verdict (closed 2026-09-21, sastalinux Fedora 44 GNOME)

Confirm — went beyond option A: `install.sh` dnf deps now include `fprintd-pam`, new `./install.sh --integrate` idempotently enables `with-fingerprint` (explicit flag, never silent on default install), `--check` reports no PAM gaps, README quick-start includes the integrate step. Live: `authselect current` shows `with-fingerprint`, `authselect check` valid, `pam_fprintd.so` in system-auth, 10 prints enrolled, user confirms desktop login working.
