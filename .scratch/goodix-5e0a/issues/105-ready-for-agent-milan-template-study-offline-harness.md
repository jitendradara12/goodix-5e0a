# 105: Offline Milan templateStudy ABI & Learning Verification Harness

**What to build:** A hermetic standalone C test harness (`legacy-experiments/test_milan_template_study.c`) against `windows_driver/GoodixEngineAdapter.dll` that proves `templateStudy` (RVA `0x79860`):
- Consumes probe ridge features from the preceding `identifyImage` match and incorporates new minutiae into the active template.
- Generates a valid expanded template via `templatePack`.
- Confirms safety gating: high-confidence genuine probes update the template (`*out_updated == 1`), while impostor probes and blank frames are rejected (`*out_updated == 0`, zero template poisoning).

**Blocked by:** none.

**Status:** ready-for-agent

## Rationale & Acceptance Criteria

1. **ABI Contract Discovery:**
   - Disassembly of `templateStudy` in `GoodixEngineAdapter.dll` (RVA `0x79860`):
     - Takes `int *out_updated` as the first argument (`%rcx`).
     - Reads the active matching session and internal template structures from the preceding `identifyImage` call.
     - Calls internal merger function `0x35470` to update ridge topology.
     - Writes update flag (`1` if updated, `0` if unchanged) into `*out_updated` and returns `0` on success.
2. **Acceptance Criteria:**
   - [ ] Implement `legacy-experiments/test_milan_template_study.c` compiling under `gcc -O2` with the PE loader shim.
   - [ ] Verify genuine matching touch triggers `templateStudy` with `out_updated = 1`.
   - [ ] Verify `templateGetPackedSize` and `templatePack` serialize the updated template.
   - [ ] Verify un-packed updated template successfully matches subsequent edge probes that failed on the initial template.
   - [ ] Verify impostor probe (different finger) and blank probe result in `out_updated = 0` (zero template drift/poisoning).

## Predicted Signatures

- **Confirm:**
  - Standalone harness reports `templateStudy returned 0, updated=1`.
  - Template size expands gracefully by $\sim 1\text{–}3\text{ KB}$ per novel ridge angle.
  - Impostor probe reports `updated=0` with `identifyImage score=0`.
- **Falsify:**
  - `templateStudy` crashes or returns non-zero error code.
  - Template corruption causes subsequent `templateUnPack` or `identifyImage` to fail.
