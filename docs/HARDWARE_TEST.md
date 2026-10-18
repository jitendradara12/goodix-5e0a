# Issue #12: one temporary hardware test

The owner's working laptop passed its regression control: five genuine matches,
five wrong-finger rejections, quiet hands-off and one advance during holding.
**ptrip7's affected laptop is next.** No new Windows boot, calibration export, image dumps or
parameter tuning is needed. Jet-Soup does not need to run this revision yet:
their unit needs its separate wire settings preserved in a later test.

This is the disposable experiment in PR #13, not a proposed production install.
Offline replay gives 10/10 genuine and 0/10 wrong-finger matches on the supplied
labeled dataset. The separate session improves from 62/96 to 82/96 frame
matches. Hardware operation on the affected unit is the remaining question.

ptrip7's first attempt stopped before sensor testing because Mint mounts `/run`
with `noexec`. The runner now stages its private driver in a root-only temporary
directory under `/var/lib` and checks executable mapping before changing the
service. Runtime control files and the temporary print database remain in `/run`.

## Run

Use a normal terminal on the Linux fingerprint laptop, as your normal user.
Use a fresh checkout so your current driver work stays untouched:

```sh
git clone --depth 1 --branch codex/offline-calibration-replay \
  https://github.com/jitendradara12/goodix-5e0a.git goodix-raster-test
cd goodix-raster-test
bash tools/test-native-raster.sh
```

The runner builds separately using existing build dependencies. On NixOS it
uses the pinned flake. It does not install packages. If a dependency/build check
fails, stop and send the printed error; do not work around it or change drivers.

After building, it asks for sudo to start a temporary session. Normal fingerprint
authentication is unavailable during that session; keep your terminal open.
The runner uses a new, private enrollment database, so the test finger can be
one you already enrolled normally. Existing prints are not deleted or replaced.

Follow the prompts:

1. Use your **right index finger** for enrollment. Keep hands off for the first
   20 seconds, then press and **hold steadily for 20 seconds** when prompted.
2. Lift, then finish enrollment using separate placements of that same finger.
   The driver still targets 12 touches; the initial hold is part of that session.
3. Perform five verification attempts with that same finger, then five with a
   different finger. Lift between attempts. Do not change settings between them.

At the end, send **only the ZIP path printed by the runner**. If something
fails, send that ZIP, or the printed error if it stopped before creating one.
No manual journal gathering is needed. Stop after this one session; the
maintainer will inspect its results before proposing any follow-up.

## Restore after interruption

Ctrl-C normally restores the previous service state automatically. If the
terminal disappears or the runner reports that restoration failed, run:

```sh
bash tools/test-native-raster.sh --restore
```

The same recovery action is also scheduled independently for 30 minutes after
session setup. The override lives under `/run`, so it does not survive reboot.
Restoration removes the staged driver under `/var/lib/goodix-5e0a-experiment-<id>`.
If a reboot interrupts cleanup, that directory may remain; it holds only the
library and DLL, never prints. Mention an interrupted reboot in your report.
There are no installed library, account, PAM or permanent service-file changes.

## What the runner verifies

- Builds the opt-in band-pass/native-raster patch in an isolated source copy;
  neither checkout nor installed library is patched.
- Checks executable mapping from the private driver directory before restarting
  fprintd; an execution restriction aborts setup and removes the staged files.
- Proves a private `/var/lib/fprint` bind mount using a harmless transient
  systemd unit before changing fprintd. The normal print database is not read.
- Temporarily adds its own runtime drop-in and restarts fprintd with the test
  library, `GOODIX_5E0A_NATIVE_RASTER=1`, no image dumping, and no idle timeout.
- Before enrollment, checks the live daemon's mount identity, selected library
  and experiment environment. A mismatch aborts the test and restores the setup.
- Saves timestamps, enrollment/verification status tokens, numerical driver
  summaries and build hashes. The ZIP allowlist excludes images, print
  templates, keys, packet hex dumps and the private storage tree. Temporary
  enrollment storage is removed after stopping the experimental daemon.
- Removes only its own unchanged drop-in. An originally running service is
  restarted normally; an originally inactive service is left inactive. A changed
  override is preserved for review instead of being deleted blindly.

The reported verdict applies only to this guided run. `confirmed` requires no
hands-off enrollment activity, one advancement during the steady hold, five
genuine matches and five wrong-finger rejections. `falsified` records a failed
behavioral check. Setup errors/interruption are `inconclusive-because-…`.
The ZIP includes the individual outcomes so the maintainer can inspect them.

Read-only prerequisite check:

```sh
bash tools/test-native-raster.sh --check
```

Build-only check, without sudo or a service/sensor operation:

```sh
bash tools/test-native-raster.sh --prepare-only /tmp/goodix-test-build
```

The destination must not already exist. These checks do not establish hardware
matching. Background: [calibration and raster evidence](calibration-raster-2026-10-19.md).
