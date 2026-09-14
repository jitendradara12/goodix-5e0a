# 74 — NixOS Packaging and Hardware Verification

**What to build / verify:**
Deploy the Milan-integrated driver (`goodix5e0a.c` + `goodix_milan.c`) to hardware, provision `GoodixEngineAdapter.dll` into `fprintd`'s accessible state path (`/var/lib/fprint/GoodixEngineAdapter.dll`), and verify real-world biometric enrollment and verification against user hardware.

**Blocked by:** 73 (closed — C driver refactored to `FP_TYPE_DEVICE` with in-process Milan engine, clean ninja build, patch synced to NixOS flake module, 459/459 tests green).

**Status:** closed (verdict: confirmed; single-touch biometric match proven on hardware; successor: 75)

---

## 1. Systemd Sandboxing Context

The `fprintd.service` on systemd runs with:
- `ProtectHome=yes` (blocks all paths under `/home/`)
- `ProtectSystem=strict` (mounts `/usr`, `/boot`, `/etc` read-only)
- `StateDirectory=fprint` (`/var/lib/fprint` is read-write and owned by `fprintd`)

In `libfprint-driver/goodix_milan.c`, `default_search_paths` explicitly checks:
`"/var/lib/fprint/GoodixEngineAdapter.dll"`.

Therefore, the user must copy `GoodixEngineAdapter.dll` to `/var/lib/fprint/` with permissions before starting `fprintd`:
```bash
sudo cp /home/sastauser/goodix-27c6-5e0a-re/drivers/GoodixEngineAdapter.dll /var/lib/fprint/
sudo chown nobody:nogroup /var/lib/fprint/GoodixEngineAdapter.dll
sudo chmod 644 /var/lib/fprint/GoodixEngineAdapter.dll
```

---

## 2. Invariants & Guardrails (AGENTS.md)

- `0x32` FDT_DOWN timeout is strictly 0 (blocking capacitive wait).
- `0x34` FDT_UP finite timeout (2000ms guard / 5000ms normal) with re-issue loop.
- Park cross-claim TTLs (guard 2s, park 30s, warm 60s) survive idle park.
- `CANCELLED` never re-issues.
- Only the user has fingers sudo. Never run hardware claims or USB captures as agent.

---

## 3. User Hardware Verification Runbook (User Only)

```bash
# Step 1: Place the Milan engine DLL into fprintd's state directory
sudo cp /home/sastauser/goodix-27c6-5e0a-re/drivers/GoodixEngineAdapter.dll /var/lib/fprint/
sudo chown nobody:nogroup /var/lib/fprint/GoodixEngineAdapter.dll
sudo chmod 644 /var/lib/fprint/GoodixEngineAdapter.dll

# Step 2: Switch NixOS configuration to rebuild libfprint-goodix with Ticket 73 patch
cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .#
sudo systemctl restart fprintd

# Step 3: Delete stale Bozorth templates (which are incompatible with Milan format)
fprintd-delete "$USER"

# Step 4: Enroll finger (8 stages with dynamic Milan template stitching)
fprintd-enroll

# Step 5: Verify protocol
# Phase 1: Hands off 60s (silent vs cycles)
# Phase 2: Casual single-touch test (e.g. sudo fprintd-verify or hyprlock unlock)
# Phase 3: Un-enrolled finger test (confirm 100% rejection)
```

---

## 4. Predicted Journal Signatures

1. **Initialization**:
   - `5e0a: Milan engine initialized successfully (Milan_v_3.02.00.20)`
2. **Enrollment**:
   - `5e0a: Milan enroll add image -> stage N/8, quality=...`
   - `5e0a: Milan enroll completed, packed template size: 23... bytes`
3. **Verification**:
   - On enrolled finger: `5e0a Milan verify: match=1 pts=...` -> `verify-match (done)`
   - On un-enrolled finger: `5e0a Milan verify: match=0 pts=0` -> `verify-no-match (done)`
4. **Rule-7 Smoke Check**:
   - `journalctl -u fprintd --since "5 minutes ago" | grep -E "timed out|Invalid ACK|verify-unknown-error|failed to"` is empty outside ticket-47/53 tolerant paths.

---

## 5. Live Hardware Iteration 1 Findings & Resolution

### Evidence from Hardware Run 1:
```
Enroll result: enroll-completed
Using device /net/reactivated/Fprint/Device/0
Listing enrolled fingers:
 - #0: right-index-finger
Verify started!
Verifying: right-index-finger
Verify result: verify-no-match (done)
VerifyStop failed: GDBus.Error:org.freedesktop.DBus.Error.NoReply: Remote peer disconnected
```

### Root Cause Analysis:
1. Milan engine loaded cleanly in fprintd (`Milan_v_3.02.00.20`).
2. 8-stage dynamic template stitching succeeded (`enroll-completed`).
3. During verify, `D32 touch confirmed` received, 4-frame burst captured, frame 3 selected, template unpacked, and Milan `identifyImage` executed.
4. However, immediately upon completion, fprintd crashed with `SEGV_MAPERR` in `fp_device_get_driver (machine->dev)` inside `fpi_ssm_mark_completed`.
5. Root cause: `goodix5e0a_deliver_frame` called `goodix5e0a_deactivate` at line 1001, which freed `self->scan_ssm`. When `goodix5e0a_deliver_frame` returned to `goodix5e0a_on_read_img`, `fpi_ssm_mark_completed(ssm)` was invoked on the already freed SSM pointer.

### Fix Applied:
1. Removed premature `goodix5e0a_deactivate` from `goodix5e0a_deliver_frame` (both verify and enroll branches). In `FpDevice`, scan SSM completes naturally via `fpi_ssm_mark_completed`, and closing/parking is managed by `dev_close`.
2. Added defensive `self->scan_ssm != ssm` check at `goodix5e0a_on_read_img` entry.
3. Updated `on_read_img` deliver completion to mark SSM completed when `enroll_stage >= nr_enroll_stages`.
4. Cleaned up dangling scan SSM in `dev_close`.
5. Built clean with ninja, verified 459/459 tests pass, regenerated unified patch (SHA-256: `bf009e6d9ad03d5594f83147cf273d4224748260c69210f8f6bae2e667f59819`), and synced to `/home/sastauser/NixOS-Hyprland/modules/goodix/`.

---

## 6. Live Hardware Iteration 2 Findings & Verdict

### Evidence from Hardware Run 2:
```
Sep 14 17:37:46 sastapc fprintd[258081]: 5e0a best frame 3/4: minutiae=22 score-proxy=22 (submitting)
Sep 14 17:37:46 sastapc sudo[258286]: sastauser : TTY=pts/1 ; PWD=/home/sastauser/NixOS-Hyprland ; USER=root ; COMMAND=/run/wrappers/bin/sudo -v
Sep 14 17:37:46 sastapc sudo[258286]: pam_unix(sudo:session): session opened for user root(uid=0) by sastauser(uid=1000)
Sep 14 17:37:46 sastapc sudo[258286]: pam_unix(sudo:session): session closed for user root
```

**Result: CONFIRMED!** Single-touch biometric verification against the real enrolled finger unlocked `sudo -v` via PAM cleanly and without crashes. The post-verify SSM segfault was completely eliminated.

### Follow-up Finding (Back-to-Back Claim Assertion Failure):
When a second authentication claim / retry occurred 0.3s later:
```
Sep 14 17:37:53 sastapc fprintd[258081]: 5e0a warm activation: reusing MCU config (age=0.3s, boot_seq=2)
Sep 14 17:37:53 sastapc fprintd[258081]: 5e0a warm path: skipping RESET + config upload, entry=CHECK_FW_VER
Sep 14 17:37:53 sastapc fprintd[258081]: **
Sep 14 17:37:53 sastapc fprintd[258081]: libfprint:ERROR:../libfprint/drivers/goodixtls/goodix.c:1851:goodix_tls_init: assertion failed: (priv->tls_hop == NULL)
Sep 14 17:37:53 sastapc fprintd[258081]: Bail out! libfprint:ERROR:../libfprint/drivers/goodixtls/goodix.c:1851:goodix_tls_init: assertion failed: (priv->tls_hop == NULL)
```
- In the `FpDevice` model, consecutive claims entering `warm activation` without parking hit `goodix_tls_init`, which asserts `priv->tls_hop == NULL`.
- Because the previous claim did not shut down or park `tls_hop`, `priv->tls_hop != NULL` caused an assertion abort (`SIGABRT`).
- Tracked and resolved in successor Ticket 75.
