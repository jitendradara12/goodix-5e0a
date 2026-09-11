# 68 — Enrollment Quality Floor Calibration (12 -> 16 Minutiae)

**What to build:**
Elevate the enrollment quality floor `GOODIX_5E0A_ENROLL_MIN_MINUTIAE` from 12 to 16 in `libfprint-driver/goodix5e0a.h`. This ensures that every template saved across the 10-stage gallery has sufficient minutiae density to clear the `bz3_threshold = 14` matching bar, eliminating mathematically dead templates ($12\text{--}13$ minutiae) that consume gallery slots but can never verify.

**Blocked by:** 65 (closed — 10 stages and 4-frame burst verified on hardware).

**Status:** ready-for-agent

---

## 1. Problem & Mathematical Root Cause

1. **Threshold Disagreement ($12 < 14$)**:
   - In Ticket 18, `GOODIX_5E0A_ENROLL_MIN_MINUTIAE` was set to 12 when `bz3_threshold` was 12.
   - In Ticket 43, `bz3_threshold` was raised to **14** to eliminate PAM impostor false unlocks.
   - However, `GOODIX_5E0A_ENROLL_MIN_MINUTIAE` was left at **12**.
2. **The Dead Template Trap**:
   - In Bozorth3, the maximum possible match score between probe $P$ and gallery template $G$ is strictly bounded:
     $$\text{Score} \le \min(|P|, |G|)$$
   - When a user touches lightly or off-center during enrollment, capturing only 12 or 13 minutiae, the driver accepts the frame (`minutiae >= 12`).
   - Because $|G| < 14$, **it is mathematically impossible for that template to ever reach threshold 14**. It is 100% dead weight in the gallery.
3. **Natural Skin Deformation Headroom**:
   - Under real touch variation, skin stretching and angle differences achieve $\sim 70\%\text{--}80\%$ minutiae pairing efficiency.
   - A template needs at least **16 minutiae** so that a $75\%$ genuine match yield ($16 \times 0.75 = 12\dots 14$) has realistic headroom to clear threshold 14.
   - With the floor at 12, faint or glancing touches ($12\text{--}15$ minutiae) pollute 30–40% of the gallery slots, causing verification retries whenever the user taps that portion of their finger.

---

## 2. Invariants & Guardrails (AGENTS.md)

- `0x32` timeout 0, `0x34` finite guard loop (2000ms/5000ms), TLS park lifecycle, and `CANCELLED` non-reissue strictly preserved.
- `bz3_threshold = 14` remains locked.
- `dev_class->nr_enroll_stages = 10` and `GOODIX_5E0A_FRAMES_PER_TOUCH = (4)` remain unchanged.
- Verification mode remains completely ungated: `GOODIX_5E0A_ENROLL_MIN_MINUTIAE` is evaluated **only** during `FPI_DEVICE_ACTION_ENROLL`.
- Single variable per build: only `GOODIX_5E0A_ENROLL_MIN_MINUTIAE (12 -> 16)`.

---

## 3. Acceptance Criteria

- [ ] `libfprint-driver/goodix5e0a.h`: `#define GOODIX_5E0A_ENROLL_MIN_MINUTIAE (16)` with clear rationale comment.
- [ ] Test suite updated: pin assertions in `test_f39_multiframe_best_of_n.py` and any other tier tests checking the enroll floor.
- [ ] Full test runner passes: `bash tests/run_all_tests.sh` (459/459 green).
- [ ] Ninja driver build clean (0 warnings, 0 errors).
- [ ] Unified patch `0001-Add-driver-support-for-Goodix-27c6-5e0a.patch` regenerated and byte-synced to NixOS module.
- [ ] Hardware verification: 
  - Fresh enrollment rejects glancing touches $< 16$ minutiae with prompt to press firmer.
  - Completed 10-stage gallery has `gallery[i]_nrows >= 16` for all $i \in [0..9]$.
  - Natural verification taps achieve instant 1-tap unlock (`score >= 14/14`).
  - Held wrong finger test produces exactly one `verify-no-match` with attempts withheld until lift (FAR guard).

---

## 4. Predicted Journal Signatures

### Enrollment Touch Quality Rejection (< 16 Minutiae):
```text
5e0a enrollment touch rejected: minutiae_count=13 < 16 (press firmer)
```

### Verification (All Gallery Templates Rich >= 16):
```text
5e0a bz3 match start: probe_nrows=21 gallery_len=10 (probe_len=164)
5e0a bz3 match: gallery[0]_nrows=22 score=15/14 (probe_nrows=21)
-> verify-match (done)
```

---

## 5. Verification Commands (For User)

```bash
# 1. Deploy
cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd

# 2. Re-enroll with quality floor
fprintd-delete $USER
fprintd-enroll

# 3. Verify
fprintd-verify

# 4. Check gallery density and match score
journalctl -u fprintd -n 30 --no-pager | grep -E "5e0a bz3 match|enrollment"
```
