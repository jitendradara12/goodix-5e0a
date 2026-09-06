# 39 — Multi-frame capture with best-of-N match per touch

**What to build:** Capture N frames per touch (proposed N=3 rapid
`GET_IMAGE` reads inside `SCAN_5E0A_GET_IMAGE`) and match each against the
gallery, keeping the best score for the attempt verdict. One variable:
frames-per-touch (1 → N) plus best-score selection. Pipeline per frame
(decode → residual → upscale → mindtct → bozorth) byte-identical to today;
no gain/geometry/threshold changes (tickets 17/35 stay frozen, 41 owns the
threshold).

**Blocked by:** None (works on today's pipeline). Pairs with ticket 41:
this ticket raises the attempt's best genuine score; 41 decides where the
bar sits.

**Status:** closed

**Verdict:** confirmed operationally on hardware 2026-09-07. Complete 3-frame
bursts and best-frame selection were repeatedly observed without transport
errors.

**Live-scope:** capture count + best-of-N selection only. No matcher swaps,
no template changes, no enrollment changes. FDT gating unchanged (frames
are captured back-to-back while the finger is down — no extra touches).

## Settled facts (do not re-litigate)

1. Today's design matches exactly ONE frame per touch. Ticket 35 proved the
   genuine distribution for single frames sits at 8–10 vs threshold 12, so
   ~every second genuine touch fails and each failure costs a full
   release–reprompt–reclaim cycle (ticket 33: attempts × ~2s).
2. Failure within a touch is uncorrelated enough to exploit: adjacent frames
   differ in pressure/micro-shift, and the Fedora report shows scores
   swinging 0–10 across attempts on the same finger. Best-of-3 turns one
   touch into three independent draws from that distribution.
3. Cost is bounded and measurable: each extra frame is one TLS read +
   ~4ms mindtct + sub-ms bozorth — tens of ms against the ~2s attempt
   budget. If per-frame journal shows all-3-identical scores, the draws are
   NOT independent and this ticket's premise dies (see falsify).

## Hardware verify protocol (user only, AGENTS.md compliant)

1. Deploy + restart:
   `cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd`
2. Single enrolled finger, 6 normal-pressure `fprintd-verify` attempts
   (natural placement, no pixel-perfect staging). Paste:
   `journalctl -u fprintd --since "10 min ago" --no-pager | grep -a -E "frame [0-9]/3|score [0-9]+/|verify-" | tail -n 40`
   (exact per-frame log wording is the agent's choice; all three frame
   scores per attempt MUST be visible).

### Predicted journal signatures

- **Confirm (close ticket):** attempts where frame-1 scores ≤10 but
  frame-2/3 clear 12 → `verify-match` on touches that fail today; attempt
  success rate clearly above today's ~50% across the 6 runs. Verdict:
  confirmed → close (tune N=2 vs 3 on the measured spread as follow-up).
- **Falsify:** all frames within a touch score within ±2 of each other
  (draws not independent — same pressure frozen per touch), OR extra
  frames add perceptible latency without changing verdicts. Verdict:
  falsified → next lane is inter-frame delay/pressure-dither during
  capture, NOT more frames.
- **Inconclusive:** finger lifted mid-burst (partial frame sets) on most
  attempts. Verdict: `inconclusive-because-[flaw]` + rerun holding the
  press ~1s.

## Hermetic verification (agent-run 2026-09-06, no hardware)

- Implemented: 3-frame burst inside SCAN_5E0A_GET_IMAGE (same SSM),
  driver-side minutiae-count proxy picks winner, single `image_captured`
  submit; enroll path single-frame unchanged; `GOODIX_5E0A_FRAMES_PER_TOUCH 3`.
- `python3 -m unittest tests.tier1_feature.test_f39_multiframe_best_of_n` —
  8/8 green. Driver ninja build green (new log lines in `libfprint-2.so.2.0.0`).
- Full suite + patch/NixOS/hash-pin/LOC hygiene re-verified green at
  ticket-40 close-out (425 passed).
- NO match-rate improvement claimed — 6-attempt success rate is hardware-only.

## Hardware finding 2026-09-07 (frame variation observed; match-rate acceptance pending)

- Pasted frames were complete (`declen=10564`) and varied within touches:
  one burst moved from `10,13,15` minutiae, while another was `10,10,10`.
  This supports frame variation but also shows that independence is not
  universal.
- The shown client results were `verify-no-match`, and no six-attempt
  success-rate comparison was pasted. The best-frame proxy therefore cannot
  yet be credited with improving verification.
- Verdict: `inconclusive-because-no-verify-match-or-success-rate`.
  Next experiment: repeat six natural-pressure attempts with the client
  result for each attempt pasted alongside all three frame lines.

### Final close evidence

The later paste contains more than six complete bursts in PID 7122, all with
`declen=10564`, followed by a `best frame` submission. Best-frame selection
chose frames 1, 2, and 3 across different bursts, demonstrating that the
selection path is active rather than fixed. A later PID 8589 showed the same
behavior with winners of 30, 22, and 22 minutiae and no timeout/error lines.
The feature is closed as operationally confirmed; no statistical match-rate
improvement claim is made.
