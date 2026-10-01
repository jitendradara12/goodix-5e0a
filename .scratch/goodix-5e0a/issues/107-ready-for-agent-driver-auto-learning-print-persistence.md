# 107: Driver Verify Auto-Learning & Template Persistence

**What to build:** Wire `goodix_milan_template_study` into `goodix5e0a_deliver_frame` on successful `VERIFY` and `IDENTIFY` actions in `libfprint-driver/goodix5e0a.c`. When the Milan engine updates the template during a high-confidence unlock, update the in-memory cached template and the `FpPrint` object's serialized GVariant so `fprintd` persists the enriched template to `/var/lib/fprint/`.

**Blocked by:** 106: Milan Engine Bridge templateStudy Integration & Safety Gating

**Status:** ready-for-agent

## Rationale & Acceptance Criteria

1. **Driver Integration Path:**
   - In `goodix5e0a_deliver_frame` (`action == FPI_DEVICE_ACTION_VERIFY` or `IDENTIFY`):
     - If `is_match` is true and `match_pts >= 50`:
       - Call `goodix_milan_template_study`.
       - If `updated`:
         - Update `self->tmpl_blob` and `self->tmpl_len` with the enriched buffer.
         - Retrieve active `FpPrint *print` from device context.
         - Update `print`'s `"fpi-data"` GVariant property using `g_variant_new_fixed_array`.
         - Pass updated `print` to `fpi_device_verify_report` / `fpi_device_identify_report` so `fprintd` writes the updated template back to disk.
   - Maintain line count constraint: `goodix5e0a.c` must remain under 2000 non-blank lines.
2. **Acceptance Criteria:**
   - [ ] Verified updates update `self->tmpl_blob` without memory leaks.
   - [ ] Driver line count stays $< 2000$ non-blank lines.
   - [ ] Full test suite passes (`bash tests/run_all_tests.sh`).
   - [ ] Nix derivation builds cleanly via `nix-build -E 'with import <nixpkgs> {}; callPackage ./libfprint-goodix.nix {}'`.

## Predicted Signatures

- **Confirm:**
  - Journal logs `5e0a Milan templateStudy: learned new features, template updated (%zu -> %zu bytes)` on novel high-confidence touches.
  - Subsequent verification probes retain the updated template across daemon restarts.
- **Falsify:**
  - Driver fails to compile or crashes during `fpi_device_verify_report`.
  - Memory leak in replaced template blobs.
