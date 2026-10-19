# Hardware test: current driver, then Jet-Soup's capture candidate

The matching fix is already the normal pipeline: 3×3 smoothing, 11×11
background removal, RMS 80, and a transpose only at the Milan boundary.
Enrollment remains 12 separate touches. This PR adds easier Linux key recovery;
it does not establish a matching fix for Jet-Soup's unit yet.

The maintainer runs the **current-settings regression first**. After that
passes, Jet-Soup runs **their capture candidate**, which combines the current
pipeline with only their wire-derived config and image-request changes.
No calibration export, image dumps, new preprocessing settings, or PSK
re-pairing are needed. An already working sensor key is reused.

## Get the PR

Use a fresh checkout of this PR on your x86-64 Linux fingerprint laptop,
as your normal user. Existing build dependencies must already be installed.
The runner supports NixOS through the flake and other systemd distributions
through `install.sh --build-only`.

## Maintainer regression

```sh
bash tools/test-hardware.sh --capture-settings current
```

This builds the PR's normal driver with the same capture settings as master.
Separately, validate extraction using the [Linux recovery instructions](psk-extraction.md)
with a new output path. You do not need to replace your existing working key.
Once this regression is confirmed, share the PR revision and the command below
with Jet-Soup. The owner's run does not establish a fix for their unit.

## Jet-Soup capture candidate

```sh
bash tools/test-hardware.sh --capture-settings jet-soup
```

The runner applies [the wire-only patch](../experiments/jet-soup-capture.patch)
to a temporary source copy. It changes config bytes 200, 235–236 and the two
checksum bytes, plus the image-request payload to
`01 00 ad 00 ae 00 ac 00 ad 00`. Both duplicate payload definitions stay equal.
These are Jet-Soup's reported settings, not an automatically selected hardware
profile or a replacement for defaults on other units. Their experimental
9×9 preprocessing, replay hooks and vendor-tail commands are not applied.

## Follow the prompts

1. Start fresh enrollment in the isolated database. **Hands off for 20 seconds**
   when prompted; the timestamp is recorded. Expect no enrollment activity.
2. Press and **hold steadily for 20 seconds** when prompted. Expect one
   enrollment advance followed by waiting for release. Event timestamps record
   latency to the first advance; repeated advances are a failure.
3. Lift and finish enrollment with separate placements of that same right
   index finger. All 12 stages must complete.
4. Perform five attempts with that finger, then five with a different finger,
   lifting between attempts. Expect five matches and five rejections.

Send only the ZIP printed by the runner. It records the Git revision, capture
settings, candidate patch/library hashes, timestamps, client decisions and
allowlisted numerical driver summaries. It excludes sensor keys, raw packet
dumps, images and templates. Stop after one run and review its result before
requesting another experiment.

**Confirmed:** quiet hands-off, one hold advance, complete fresh enrollment,
five genuine matches and five wrong-finger rejections. **Falsified:** valid
testing shows spurious activity, repeated hold advances, genuine failures or a
wrong-finger match. **Inconclusive-because-[flaw]:** wrong build, setup error,
interruption, or missing protocol phases. A wrong-finger match ends the test.
The verdict applies to this unit and run, not population accuracy.

For Jet-Soup, confirmation supports the corrected pipeline with their capture
settings. Falsification means that combination still needs investigation; it
does not establish that calibration is required. The single next experiment
after either run is chosen from that report.

## Isolation and recovery

The runner builds before requesting sudo, stages its library under a private
`/var/lib` directory (not a possibly `noexec` `/run`), and verifies executable
mapping before changing the service. It tests an isolated `/var/lib/fprint`
mount, then checks the live daemon's mount and library before enrollment.
Existing prints, installed libraries and PAM configuration are not replaced.

The test uses a runtime drop-in and temporarily keeps fprintd resident. It
restores the original active/inactive state, removes its private enrollment
database and driver, and has an independent 30-minute recovery timer.
Normal fingerprint authentication is unavailable during the session.

If interrupted, Ctrl-C normally restores the setup. If restoration fails or
the terminal disappears:

```sh
bash tools/test-hardware.sh --restore
```

An interrupted reboot may leave a staged directory under
`/var/lib/goodix-5e0a-experiment-*`; mention it in the report. It contains no
prints. The runtime service override does not survive reboot.

Read-only prerequisite check:

```sh
bash tools/test-hardware.sh --check
```

Build-only candidate check:

```sh
bash tools/test-hardware.sh --capture-settings jet-soup --prepare-only /tmp/goodix-jet-build
```

Neither check validates sensor behavior. This PR remains ready for hardware
verification until the actual deployed test reports are reviewed.
