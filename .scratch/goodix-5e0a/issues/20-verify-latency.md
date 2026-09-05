# 20 — Verify latency (slow/late recognition)

**What to build:** Cut wall-clock time from touch to `verify-match` so
unlock feels instant. Measured baseline 09-05: ~2–3s per attempt
(`Starting up goodix tls server` → frame+match), several attempts per
`fprintd-verify` call, each attempt repeating full activation. Match
compute itself is milliseconds — latency is all session overhead.

**Blocked by:** Nothing structural (works, just slow). After 07.

**Status:** in-progress

## Implemented Optimization (Candidate 3: Instant Verify Release)

In `goodix5e0a_on_read_img`:
During `FPI_DEVICE_ACTION_VERIFY` (and all non-enroll actions):
1. The driver passes the captured frame to `fpi_image_device_image_captured(dev, img)` for instant Bozorth3 matching (4ms).
2. The scan SSM marks itself completed immediately (`self->scan_ssm = NULL; fpi_ssm_mark_completed(ssm);`).
3. The driver reports finger release (`fpi_image_device_report_finger_status(dev, FALSE)`) right away.
4. Libfprint's verify handler immediately completes the D-Bus action and deactivates the device without stalling in `FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_OFF` for 2–5 seconds waiting for the user to lift their finger or polling `0x34`.
5. For enrollment (`FPI_DEVICE_ACTION_ENROLL`), the release polling loop is preserved so multi-stage finger transitions remain strictly enforced.

## Build & Test Status

- **Master E2E Test Suite:** 375 / 375 tests passed (100% pass rate in 13s across all 5 tiers).
- **Driver Build:** Ninja build clean (0 errors, 0 warnings).
- **Full Nix Build:** Hermetic Nix package clean.
- **Unified Patch:** Synchronized to `~/NixOS-Hyprland/modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch`.
  - SHA-256 Checksum: `c3a18052972066ecf1a7ba19b193880a11ce1a5714e5beb335e8f3ee49c333a8`.

## Verification Protocol (Hardware Run 17)

1. Deploy patch in NixOS:
   ```sh
   cd ~/NixOS-Hyprland
   sha256sum modules/goodix/0001-Add-driver-support-for-Goodix-27c6-5e0a.patch
   # Verify: c3a18052972066ecf1a7ba19b193880a11ce1a5714e5beb335e8f3ee49c333a8

   sudo nixos-rebuild switch --flake .#
   sudo systemctl restart fprintd
   ```
2. Test verify latency:
   ```sh
   fprintd-verify
   ```
   Touch sensor: verify should return `verify-match (done)` immediately upon touch (< 300ms) without waiting for finger lift.
3. Test sudo latency:
   ```sh
   sudo echo "Instant unlock!"
   ```
4. Collect journal timestamps:
   ```sh
   journalctl -u fprintd --since "5 min ago" --no-pager | grep -a -E "5e0a D32 touch confirmed|5e0a bz3 match:|Device reported verify completion" | tail -n 20
   ```


## Measured breakdown (journal, 09-05 — do not re-derive, optimize)

Per attempt (~2–3s): TLS server startup + handshake proxy flights, the full
~32-stage analog bring-up, config upload, scan (DOWN-sample, capture,
release polls), minutiae + Bozorth3 (ms). Attempts repeat ~3s apart while
the finger is present; first attempts often no-match, later ones match
("recognizes late" = Nth-attempt match).

## Candidate wins (measure each with journal timestamps, keep what moves
the number, one variable per build)

1. **First-attempt quality over attempt count:** capture ~500ms after touch
   rather than instantly (settling), so attempt 1 matches instead of
   attempt 3. Counts attempts-to-match before/after.
2. **Bring-up trim:** profile which of the ~32 stages cost wall time
   (timestamp each stage marker already in journal) and which are
   load-bearing for content (max/range/corr per stage-skipped variant).
   Cheap stages stay; dead weight goes. Never touch the frozen transport
   (`goodix.c/h/proto`, `goodixtls.c`).
3. **Release path:** verify currently resolves after lift + release polls.
   If a content frame already matched, report without waiting for release
   mechanics (check libfprint verify-flow constraints first — do not break
   enroll stage transitions, which legitimately need release).

## Acceptance criteria (deployed driver, hardware only)

- [ ] Median touch-to-`verify-match` under 2s across 10 trials (report the
      distribution, not the best run).
- [ ] No regression: double-verify reliability, hands-off silence, 07 green.

## Rollback criteria

- Any timeout/unknown-error/no-match regression vs baseline → revert that
  step only with journal evidence.
