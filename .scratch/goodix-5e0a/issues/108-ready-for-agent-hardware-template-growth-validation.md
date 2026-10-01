# 108: Hardware Template Growth & Auto-Study Acceptance Protocol

**What to build:** Hardware verification protocol evaluating the deployed auto-learning driver on NixOS (`sastapc`). Verify that initial enrollment yields a valid baseline, subsequent varied touches from peripheral angles trigger `templateStudy`, the stored template grows in size, and verification accuracy improves for previously marginal angles with 0.0% false accepts.

**Blocked by:** 107: Driver Verify Auto-Learning & Template Persistence

**Status:** ready-for-agent

## Rationale & Acceptance Criteria

1. **Verification Protocol:**
   - Deploy driver to NixOS Hyprland host `sastapc`.
   - Enroll fresh right-index print via `sudo fprintd-enroll "$USER"`. Note initial template size $S_0$.
   - Phase 1 (Standard Verification): Perform 5 normal touches. Verify sub-50ms unlock latency is preserved.
   - Phase 2 (Angle/Edge Expansion): Perform 10 touches deliberately presenting finger edges, tips, and varied angles. Observe journal for `templateStudy` trigger.
   - Phase 3 (Growth & Persistence): Check template size on disk $S_1 > S_0$. Restart `fprintd` (`sudo systemctl restart fprintd`).
   - Phase 4 (Security / Impostor Check): Verify different fingers are strictly rejected with `verify-no-match` (zero FAR).
2. **Acceptance Criteria:**
   - [ ] Baseline template enrolled successfully.
   - [ ] Peripheral touches trigger `templateStudy` and expand template size gracefully ($S_1 > S_0$).
   - [ ] Stored print retains updated data across daemon restarts.
   - [ ] Impostor fingers strictly rejected with 0 false accepts.

## Predicted Signatures

- **Confirm:**
  - Journal logs `templateStudy: learned new features`.
  - Template size expands from $\sim 50\text{ KB}$ up to $\sim 55\text{–}65\text{ KB}$ as novel edges are introduced.
  - Verification succeeds consistently from multiple angles.
  - Zero false accepts on un-enrolled fingers.
- **Falsify:**
  - Template size does not change after repeated novel edge touches.
  - Template corruption causes verify to regress to `verify-no-match`.
