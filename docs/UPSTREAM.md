# Upstream roadmap (libfprint on freedesktop.org)

Goal: merge a reverse-engineered image driver upstream. Review cycles take
weeks to months; the NixOS overlay stays the downstream route until then.
Researched against upstream `master` (September 2026); re-verify paths before
submitting, they move.

## 1. Driver type

Image sensor with host matching subclasses `FpImageDevice` (base `FpDevice`
is for match-on-chip). Implement image vfunctions — open, close, activate,
deactivate, change-state — and report captures for the in-tree matcher.
Reference shapes: `egis0570`, `vfs5011` upstream; counter-precedent: all
upstream Goodix drivers are match-on-chip (`goodixmoc`) with on-chip storage
semantics this sensor lacks, so the MR must argue the image classification
explicitly (see `docs/adr/0001-host-image-matching.md`).

- Internal device API: `libfprint/drivers_api.h`
- Image device API: `libfprint/fp-image-device.h`, `libfprint/fpi-image-device.h`
- Device classes: `libfprint/fpi-device.h`, `libfprint/fp-device.h`
- Contributor guide: `HACKING.md` (protocol specs plus real-hardware
  enroll/verify evidence expected for community reverse-engineered drivers)

## 2. Tree placement and build

- Driver sources under `libfprint/drivers/` (single file or one
  subdirectory, matching the existing per-family layouts).
- Register in both `meson.build` (driver info: helpers, endianness) and
  `libfprint/meson.build` (driver sources); the driver id must be a valid C
  identifier matching the filename.
- Build flavors via `-Ddrivers=default|all|<csv>`; CI builds all drivers
  with warnings as errors.
- USB ids come from the driver's id table; autosuspend hwdb and rules are
  *generated* (`fprint-list-udev-hwdb`, `fprint-list-udev-rules`,
  `fprint-list-metainfo`) — never hand-write rules files.

## 3. Replay tests (mandatory)

Every driver needs `tests/<driver>/` wired into `tests/meson.build`,
following `tests/README.md`:

- Image drivers record `device` plus `capture.ioctl` (plus optional
  `capture.ioctl-recording`) plus a pixel-compared `capture.png`, driven by
  the shared `capture.py` harness under `FP_DEVICE_EMULATION=1`.
- Record with `tests/create-driver-test.py` as root from the build
  directory; use a finger side or arm, never a real fingerprint.
- Cover open, enrollment, matching and non-matching verification,
  cancellation mid-scan, and suspend/resume. A patch without replay coverage
  for new hardware is routinely refused.
- The in-repo Python tiers are synthetic-payload mocks, not USB replays —
  they do not count toward this requirement.

## 4. Style and CI gates

- Style is **uncrustify** (`scripts/uncrustify.cfg` + `scripts/uncrustify.sh`;
  CI fails on any diff) — not clang-format.
- `meson setup --werror` with the project's warning set must pass; big-endian
  (`s390x`), `valgrind`, ASan/UBSan, coverage, installed-tests, ABI check,
  and generated-hwdb consistency checks all run in CI.
- Public API additions need gtk-doc comments.

## 5. Lifecycle edge cases reviewers probe

- Suspend/resume must re-initialize cleanly (cold-boot OTP priming needs a
  wake-from-sleep proof, not just a reboot proof).
- Cancelled reads mid-enroll/mid-scan must abort transfers without leaks or
  a wedged device (disarm timers and state machines together).
- Stalled packets must fail gracefully so a login-time authentication never
  hangs PAM.

## 6. Legal and clean-room posture

- New files carry LGPL-2.1-or-later headers, matching the tree.
- Upstream rejects proprietary shims but encourages clean-room
  reverse-engineering within local law. State the derivation method
  (passive USB capture on Windows) in the MR; include no decompiled vendor
  code or confidential headers.
- Known hard sell: per-unit factory secrets and vendored PSK cipher
  downgrades have no accepted upstream pattern — sibling out-of-tree forks
  resort to dual-boot extraction or reflashing, neither of which upstream
  has blessed. The MR must disclose the secret-provisioning story plainly:
  what is hardcoded, how it was derived, and why the driver cannot derive
  it at runtime. Expect this to be the longest review thread.
- Process: merge requests to the upstream tracker; end users file driver
  requests with protocol spec, `lsusb -v`, replay traces, and hardware
  enroll/verify evidence. Unsupported ids sync from the wiki list in CI.

## 7. Submission packing

Keep history as logical commits (transport, driver, tests/recordings, device
table/udev), each passing CI alone. Downstream while waiting: NixOS overlay
here; Fedora/COPR and Arch/AUR equivalents follow the same patch.
