# 116 — Milan quality-floor contact gating, finger release enforcement, and FDT DOWN calibration

**What was built:**
1. Enforced Milan frame quality floor (`best_quality < 15`) in `choose_best` (`libfprint-driver/goodix5e0a.c`): rejects air triggers and poor-contact frames during enrollment (`active=%u (press firmer)`), and silently re-arms `SCAN_5E0A_FDT_DOWN` during verify/identify to prevent air noise from degrading matching scores.
2. Enforced physical finger release between enrollment touches in `goodix5e0a_on_fdt_up_reply` by re-issuing FDT_UP if the finger remains pressed, stopping runaway stage advances on continuous contact.
3. Aligned 4-channel DAC registers (`[0xad, 0xae, 0xac, 0xad]`) for Jet-Soup's hardware revision in `experiments/jet-soup-capture.patch`, eliminating air readout saturation.
4. Hardened test runner (`tools/hardware_session.py`) with `G_MESSAGES_DEBUG=all` and Fedora SELinux context fixes (`chcon -R -t lib_t`).

**Hardware verification runs:**
- Maintainer baseline (`2885d46439c7dbf6`): 5/5 genuine matches, 5/5 impostor rejections. Silent hands-off (20s), single holding advance. Verdict: confirmed.
- Maintainer candidate (`53128b6d64ee485d`): 5/5 genuine matches, 5/5 impostor rejections. Silent hands-off, single holding advance. Verdict: confirmed.
- Jet-Soup live verification (`080e6c718b3b818c` on Fedora 44): 5/5 genuine matches, 5/5 impostor rejections (touch qualities 40..74, overlap 78..94%). Verdict: confirmed (falsification resolved).

**Successor:** Ticket 117 (`117-closed-dynamic-otp-dac-calibration.md`).

**Blocked by:** None.

**Status:** closed

**Verdict:** Closed (confirmed on maintainer and contributor hardware; successor: 117).
