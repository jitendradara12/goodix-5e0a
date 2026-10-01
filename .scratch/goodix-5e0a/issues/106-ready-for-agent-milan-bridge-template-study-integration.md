# 106: Milan Engine Bridge templateStudy Integration & Safety Gating

**What to build:** Expose `goodix_milan_template_study` through `libfprint-driver/goodix_milan.c` with mutex safety and high-confidence match gating (only trigger study when `match_score >= 50`). When new ridge data is learned, re-pack and return the updated template blob and size.

**Blocked by:** 105: Offline Milan templateStudy ABI & Learning Verification Harness

**Status:** ready-for-agent

## Rationale & Acceptance Criteria

1. **Engine Bridge Responsibilities:**
   - Resolve `m_templateStudy = get_export("templateStudy")` in `goodix_milan_init`.
   - Implement `int goodix_milan_template_study (void *unpacked_template, uint8_t **out_blob, size_t *out_len, int *out_updated)`.
   - Protect invocation under `g_rec_mutex_lock (&g_milan_mutex)` and `ensure_gs()`.
   - Implement high-confidence threshold gating: auto-study must only run if the preceding probe achieved a strong match score ($\ge 50$), preventing degraded or marginal touches from altering the template.
   - When `*out_updated == 1`, call `m_templateGetPackedSize` and `m_templatePack` to construct the serialized payload.
2. **Acceptance Criteria:**
   - [ ] Function pointer `m_templateStudy` wired and validated in `goodix_milan.c`.
   - [ ] Header `goodix_milan.h` declares `goodix_milan_template_study`.
   - [ ] Full unit test suite passes without regressions (`bash tests/run_all_tests.sh`).

## Predicted Signatures

- **Confirm:**
  - Bridge cleanly exports `goodix_milan_template_study`.
  - Non-matching or low-score probes bypass study and return `out_updated = 0`.
  - High-confidence matching probes successfully pack and return enriched template buffers.
- **Falsify:**
  - `goodix_milan_template_study` returns allocation errors or deadlocks `g_milan_mutex`.
