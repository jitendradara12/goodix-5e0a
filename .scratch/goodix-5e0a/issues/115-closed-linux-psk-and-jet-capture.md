# 115 — Linux-only PSK recovery and isolated hardware test runner

**What was built:**
1. Integrated Linux-only PSK recovery tool (`tools/extract_psk_whitebox.py`), deriving candidate record offsets from bounded DPAPI parsing and validating the 32-byte key's SHA-256 against sensor hardware before writing `/etc/libfprint/goodix-5e0a.psk` with mode 0600.
2. Built isolated hardware test runner (`tools/hardware_session.py`, `tools/test-hardware.sh`) using temporary systemd namespace drop-ins to protect existing user enrollments and configuration.
3. Preserved contributor Jet-Soup's wire-only capture candidate patch in `experiments/jet-soup-capture.patch` for hardware evaluation.
4. Added test coverage in `tests/tier1_feature/test_f115_linux_psk.py` and `tests/tier1_feature/test_f115_hardware_session.py`.
5. Updated documentation in `docs/psk-extraction.md` and `tools/README.md`.

**Hardware verification runs:**
- Maintainer regression (`--capture-settings current` at `09e78f1`): 5/5 genuine matches, 5/5 impostor rejections. Silent hands-off (20s), single holding advance. Verdict: confirmed.
- Jet-Soup candidate (`--capture-settings jet-soup` at `186f32d`, bundle `goodix-test-0f643487c98e906e.zip`): 0/5 matches due to air DAC saturation and missing release guards. Verdict: falsified (successor: Ticket 116).

**Successor:** Ticket 116 (`116-closed-quality-floor-and-release-gating.md`).

**Blocked by:** None.

**Status:** closed

**Verdict:** Closed (software-complete, baseline verified; successor: 116).
