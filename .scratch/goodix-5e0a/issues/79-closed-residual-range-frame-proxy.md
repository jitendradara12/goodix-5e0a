# 79: Residual-Range Dynamic-Range Frame Proxy (Offline, Then Hardware)

**What to build:** An offline threshold analysis (no driver changes at first)
that replaces Milan `getQuality` with the `residual_range` metric
(`residual_max − residual_min` from the driver's 3x3 local-contrast path) as
the best-of-N burst rank, validated on **real live burst** frames — then, only
if the offline separation holds with FAR intact, wire it behind the ticket-76
rank interface (`quality` → `residual_range`, same journal shape) for a
hardware verify.

**Blocked by:** 78 (closed 2026-09-14 — gain shaping confirmed on synthetic
dense but falsified as the live quality=0 cause; `qout` side-channel dead;
`residual_range` correlates: 727/704 → quality>0, 394/0 → 0).

**Status:** closed (verdict: falsified — residual_range measures partial-contact edge energy, not matchability; successor 80 tests fuller-contact live frames, then enrollment-side)

## Acceptance Criteria

- [ ] Step 0 (user-only, agent has no fingers): user saves one real 4-frame
  live burst (deliberate press + one casual tap) to `experiments/live_burst_*.pgm`
  (64x80 P2 12-bit, same layout as `fingerprint.pgm`) and pastes the capture
  command + output. No real live burst exists in-repo today (only synthetic
  dense + sparse fingerprint + blank) — do NOT invent live data or tune the
  threshold on synthetic frames alone.
- [ ] Offline probe (copy of the ticket-78 harness): per-frame
  `residual_range` + Milan `identifyImage` score vs `milan_dense_pad.tpl`
  (and, once enrolled on live data, vs a live template) showing a threshold
  between ~394 and ~704 that keeps matchable frames and drops blanks
  (e.g. live settled ≥ threshold > sparse/blank) with genuine-100 /
  impostor-0 intact.
- [ ] Only then: driver wiring reusing the ticket-76 rank/journals (one
  variable: burst-winner ranking only; enrollment floor unchanged), ninja
  drivers-only build + full test suite green, patch synced.
- [ ] Hardware verify per AGENTS.md two-phase protocol with pre-registered
  journal signatures; conclude only confirmed / falsified /
  inconclusive-because-[flaw] + the single next experiment.

## Context & Evidence

- Ticket 78 probe (`experiments/test_getquality_contrast.c`, exit 0 CONFIRMED):
  driver shaping `g1.0-m128` still reports quality 12 on dense-like input, so
  live 0/0 frames are sparse-like, not gain-starved. `qout[0]==overlap`,
  `qout[1]==quality` every row (no side-channel); identify details flat
  `[100,100]`. Quality is clarity-only (impostor dense scores 19 vs genuine
  18) — valid solely for intra-burst same-finger ranking.
- Ticket 76 hardware: every live frame `quality=0`, `overlap` flat intra-burst;
  winner == minutiae winner. Ticket-39 minutiae order remains the fallback.

## Predicted Signatures

- **Confirm** (range separates live): settled live frames sit clearly above the
  threshold, blanks/sparse below, genuine 100 / impostor 0 intact, and the
  hardware burst winner differs from the minutiae winner on ramp frames with
  casual taps matching first touch → keep the wiring.
- **Falsify** (range overlaps): live matchable frames and blanks interleave
  across the threshold, or winners == minutiae winners line-for-line again →
  revert the wiring; next experiment pursues multi-frame fusion or enrollment
 -side changes, never minutiae-floor relitigation without new data.
- **Inconclusive-because-[flaw]**: no real live burst provided (synthetic-only
  tuning), DLL/template path missing, or dirty-TLS-park noise in the journal
  (re-run after `sudo systemctl restart fprintd`).

## Implementation (2026-09-14, agent build, offline only — no driver changes)

**Progress note (superseded by verdict below):** probe staged while blocked on Step-0 live burst.

- New `legacy-experiments/test_residual_range_proxy.c`: pristine ticket-78
  PE-loader head (`head -n 896 test_getquality_contrast.c`) + new tail that
  measures per-frame `residual_range` at the as-shipped shaping
  (`lc-g1.0-m128`, driver-faithful 3x3 local-contrast, matching
  `goodix5e0a_normalize_raw_frame`) alongside Milan `getQuality` and
  `identifyImage` vs `legacy-experiments/milan_dense_pad.tpl` (finger A).
  Build: `gcc -O2 -o /tmp/opencode/probe79
  legacy-experiments/test_residual_range_proxy.c -lm` (exit 0).
- Harness sanity on synthetic refs only (NOT a threshold claim):
  `timeout 120 /tmp/opencode/probe79` → exit 3
  `[VERDICT: INCONCLUSIVE-because-no-live-burst]`, ref ranges
  dense-A=727.4 / dense-B=703.8 / sparse=394.1 / blank=0.0 (exact ticket-78
  reproduction), FAR intact (genuine-100 yes, impostor/blank-0 yes),
  `qout[0]==overlap`, `qout[1]==quality`, details `[100,100]` flat.
  Zero `live_burst_*.pgm` files found — threshold deliberately NOT tuned.
- New `legacy-experiments/capture_live_burst.py` (Step-0 helper): same TLS +
  `mcu_get_image` wire path as `test_press_and_capture.py`, but captures 4
  consecutive frames per hold and saves each via `tool.write_pgm(pixels, 80,
  64, <prefix>_NN.pgm)` (header `P2 / 64 80 / 4095`, same layout as
  `fingerprint.pgm`). User runs twice (press + tap); agent ran nothing
  hardware (no fingers/sudo).
- `libfprint-driver/` untouched; no driver wiring, no patch regen. Next:
  after the user pastes Step-0 capture output + files land in-repo, re-run
  the probe with live paths and evaluate the 394..704 window, then decide
  wiring behind the ticket-76 rank interface.
- Subagent review fixes (2026-09-14, still offline, same variable): probe
  lower bound is now max(sparse, blank) only — dense-B reported as context,
  never gating (clarity-only, ticket-78 #3); live no-match prints
  `NONE-matched (finger mismatch? enroll a live template)` instead of a raw
  1e9 float, range distribution still reported match-decoupled (live-template
  enrollment deferred until the burst arrives). Capture helper now polls
  `s_server` after startup (fatal + port/PID recovery hint), reaps it with
  `wait`/`kill` + pipe close, and skips saving short reads loudly.
  Rebuild green, re-run exit 3 with identical ref ranges (727.4 / 703.8 /
  394.1 / 0.0), `py_compile` clean (`--help` needs the AGENTS.md nix-shell
  for `usb`, same as existing capture scripts).

## Verdict: FALSIFIED (2026-09-14, offline on real live data — no driver changes made)

Step 0 arrived: user pasted full capture output for 2×4-frame bursts
(`live_burst_press_01..04`, active 392/438/472/474; `live_burst_tap_01..04`,
active 764/727/703/706; all `P2 / 64 80 / 4095`). `*.pgm` is gitignored
(`.gitignore:12`) by design — evidence is the pasted output + probe logs,
not committed files. Source hashes (`sha256sum`, 2026-09-14):
press ac909d53/9dcae997/ee5a72f4/2fe13d85, tap 93e598fe/b31a61a9/1a9141e5/80f2be90
(prefixes; full strings in session log).

- New `legacy-experiments/test_enroll_live_burst.c` (same pristine head +
  enroll/score tail, modes `live|live8|densectrl`, gain argv `1.0|1.5`):
  `gcc -O2 -o /tmp/opencode/enroll79 test_enroll_live_burst.c -lm` (exit 0).
- Live ranges @ g1.0-m128: press 702.7/728.1/765.8/770.3, tap
  935.0/923.0/915.0/908.0 — meeting/exceeding matchable synthetic dense-A
  (727.4), all above sparse (394.1)/blank (0.0). `getQuality` = 0/0 on all 8
  (pre-enroll clean state), `identifyImage` vs finger-A template 0/8.
- Own-finger enroll fails at every setting: `live` g1.0/g1.5 and `live8`
  (8 touches) → `add_res=131` every touch, stitched=0, progress=0%,
  degenerate 1443B template matching 0/8 including itself.
- Positive control `densectrl` (ticket-72 faithful, dense + shifts) @ g1.0:
  `add_res=0`, 8/8 stitched, 100%, 22822B (≈23110B ticket-72 template),
  self-match 100, impostor-B/sparse/blank/noise all rejected. Enroll path
  healthy — rejection is live frame content, not harness or shaping.
- Falsification: range cannot distinguish matchable from unmatchable —
  tap_01 (935, unmatchable partial) outranks genuine dense-A (727.4), and
  press_01 (702.7) ≡ impostor dense-B (703.8). High range = partial-contact
  edge spikes (live res_max +485..+658, asymmetric; dense ±360 symmetric),
  not ridge clarity. Ranking by range would prefer the worst frames.
- Caveats (do not cite without them): score-matrix quality is post-enroll
  (noise q=100 artifact vs 0/0 pre-enroll — state pollution, not signal);
  these bursts are partial-contact (active ≤764 vs 5120; live max pixel
  ≤935 vs ~2500 dense), so the narrower claim "range ranks AMONG matchable
  live frames" is untested — that is successor 80. No minutiae-floor
  relitigation: driver/enrollment floor untouched throughout.

Successor: ticket 80 (fuller-contact live burst + offline enroll retry; if
still `add_res=131`, enrollment-side comparison with the device flow).
