# Jet-Soup: test PR #15

The maintainer’s regression passed. This test combines the current matching
fix with your wire-only capture settings.

Run in Fedora with your sensor attached, as your normal user. Use your existing
sensor key and installed build dependencies. The runner uses private test
enrollments and restores your normal setup afterward. Fingerprint login is
unavailable during the test.

## 1. Get the PR and run

Use a fresh checkout; the capture patch is applied automatically:

```sh
git clone --depth 1 --branch codex/linux-psk-jet-capture \
  https://github.com/jitendradara12/goodix-5e0a.git goodix-jet-test
cd goodix-jet-test
bash tools/test-hardware.sh --capture-settings jet-soup
```

It builds first, then asks for sudo to start the temporary test.

## 2. Follow the prompts

1. **Hands off for 20 seconds.** Expect no enrollment activity.
2. **Press and hold for 20 seconds.** Expect one advance, then waiting for release.
3. Lift and finish the 12-touch enrollment with that same right index finger.
4. Try that finger five times, then a different finger five times. Lift between
   attempts. Expect five matches and five rejections.

The runner records timestamps and reports `confirmed`, `falsified`, or an
inconclusive result if setup/testing could not finish.

## 3. Send the result

Attach the ZIP printed at the end to [PR #15](https://github.com/jitendradara12/goodix-5e0a/pull/15),
even if the test fails. It contains results and numerical logs, not keys,
images or templates. If it stops before producing a ZIP, copy the error text.
Stop after one run; we’ll review the report before choosing another test.

## If interrupted

Ctrl-C normally restores the setup. If the terminal closes or restoration fails,
run this from the checkout:

```sh
bash tools/test-hardware.sh --restore
```
