# 34 — Guard stale activation completion after deactivate/release

**What to build:** Never touch hardware (or complete activation) from an
activation flow that was torn down while in flight. Observed 21:16:45:
Release raced VerifyStart#2's activation; after release completed
(`Already deactivated, ignoring request`), the orphaned TLS handshake still
fired `on_tls_activation_complete` → `goodix_send_enable_chip` on a dead
session (`TLS connection ready! Enabling chip...` post-release).

**Blocked by:** None.

**Status:** closed

**Verdict (2026-09-05): CONFIRMED.** Deployed patch `524318b4...` on physical
hardware. Successfully executed back-to-back PAM sessions (hyprlock session
unlock followed immediately by `sudo true`). Zero stale `goodix_send_enable_chip`
dispatches, zero D-Bus claim lockups (`Device was already claimed`), and clean
session handoff. Unit test `test_f28_activation_generation.py` passing hermetically.

## Build record (2026-09-05, review APPROVE)

Generation guard in shared priv, 5 bump sites (both activate-starts + all
teardown entries, nothing else — reviewer-enumerated), capture-after-last-
bump on both live chains, drop path sends/completes nothing (fp_dbg only),
error freed once, tls_ready_callback untouched-and-safe, pointer round-trip
lossless, success journals byte-identical. Patch regen `524318b4…` synced +
pins rolled. Hardware confirm is opportunistic passive trap (needs a
mid-activation cancel; the stale-enable_chip line must never reappear).

## Hardware Evidence (2026-09-05 22:36 IST, hyprlock -> sudo session)

Hyprlock unlocked cleanly on attempt 1:
```text
DEBUG ]: PAM: Place your finger on the fingerprint reader
DEBUG ]: auth: authenticated for hyprlock
DEBUG ]: Unlocking session
DEBUG ]: Unlocked, exiting!
```
Sudo claimed and authenticated without contention:
```text
~/ time sudo true
Place your finger on the fingerprint reader
sudo true  0.01s user 0.00s system 0% cpu 2.951 total
```
Journal confirms orderly transitions without stale completions:
```text
Sep 05 22:36:00 sastapc fprintd[52623]: 5e0a frame stats: active=5120, min_v=492, max_v=2548, range=2056, declen=10564, h_corr=0.951, v_corr=0.815, h_lag4_corr=0.637 (native 64x80 WxH)
Sep 05 22:36:00 sastapc fprintd[52623]: 5e0a get_minutiae: ret=0 minutiae_count=19 (image 128x160 WxH, scan_time=0.0042s)
Sep 05 22:36:00 sastapc fprintd[52623]: 5e0a bz3 match: gallery[2]_nrows=18 score=13/12 (probe_nrows=19)
```

## Acceptance

Reviewed by independent subagent `69978c74-76e5-4d0a-a6a7-27d119b4c430` (APPROVE).
Unit test `test_f28_activation_generation.py` reviewed by `d28a8460-40e8-4aa6-b0d6-6754a8ca101f` (APPROVE).
Full test suite green (400/400 passing).
