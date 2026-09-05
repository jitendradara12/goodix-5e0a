# 36 — Upstream Rebase & umockdev Replay Harness (freedesktop.org alignment)

**What to build:** Align the working downstream Goodix 5e0a driver with
upstream `gitlab.freedesktop.org/libfprint/libfprint` master as outlined in
`docs/UPSTREAM.md`. Specifically:
1. Wire `umockdev` replay test recording harness (`tests/create-driver-test.py`
   targeting `tests/goodixtls5e0a/capture.ioctl` + `device` + `capture.png`
   evaluated under `FP_DEVICE_EMULATION=1`).
2. Add device lifecycle power management hooks (`.suspend` and `.resume` vfuncs)
   in `goodix5e0a.c` to cleanly re-prime OTP and reset session across S3 sleep.
3. Validate driver source against upstream `scripts/uncrustify.sh` and
   `meson setup --werror` in an upstream tree checkout.

**Blocked by:** None (hardware is working downstream; upstream tree can be
cloned/evaluated offline).

**Status:** ready-for-agent

## Background & Upstream Requirements (`docs/UPSTREAM.md`)

- **Replay Requirement:** Upstream CI refuses new drivers lacking `umockdev`
  replays. In-repo Python mock tiers (Tiers 1–5) are downstream-only.
- **Power Management:** Reviewers probe suspend/resume re-initialization.
- **Upstream Placement:** Driver placed under `libfprint/drivers/goodixtls/`,
  registered in top-level and library `meson.build`.

## Next Steps (One Variable per Phase)

- **Phase 1 (Agent):** Clone/inspect upstream `libfprint` master in `/tmp/libfprint-upstream`,
  audit API differences against our 1.94.5 base (e.g. meson options, device vfuncs).
- **Phase 2 (Agent):** Implement `.suspend` / `.resume` vfuncs in `libfprint-driver/goodix5e0a.c`.
- **Phase 3 (Hardware/User):** Execute `tests/create-driver-test.py` with side-finger/arm
  to capture the canonical `capture.ioctl` recording for upstream CI.
