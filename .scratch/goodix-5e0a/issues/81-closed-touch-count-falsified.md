# 81: Enrollment-Side Device-vs-Offline Comparison

**What to build:** An offline enrollment-side comparison, with no driver
change first. Ticket 80 reached its contact ceiling before the
`residual_range`-among-matchable claim could be tested: four-touch live
enrollment still returned `add_res=131`, while the contact gate never reached
`active(>30)>2000`. The next question is why the device enrollment flow can
produce a usable enrollment where one offline live burst cannot.

**Blocked by:** 80 (closed 2026-09-15 — inconclusive-because-contact-ceiling;
the prescribed fuller-contact gate was not reached; successor lane is
enrollment-side).

**Status:** closed (verdict: falsified — touch count across independent presses does not rescue per-touch 131 rejection; successor: enroll-time shaping comparison)

## Acceptance criteria

- [x] Preserve frame provenance: use independently captured bursts identified
  as the same finger, and record each prefix, frame order, capture output, and
  SHA-256. Do not treat a post-overwrite PGM as the earlier attempt.
- [x] Extend the offline harness only as needed to enroll distinct frames from
  multiple bursts (not the same four frames cycled by `live8`). Compare the
  existing one-burst 4-touch path with combined independent-burst inputs,
  recording every `add_res`, stitched count, progress, pre-enroll quality,
  packed template size, self-match, and impostor/blank/noise rejects.
- [x] Keep the positive dense control in every run: `add_res=0`, stitched
  progress through completion, a non-degenerate template, self-match 100,
  and negative rejects intact. Keep the enrollment floor unchanged.
- [x] Compare only one enrollment-side variable per branch: first touch count
  across independent presses; only if that is insufficient, isolate shaping or
  stitching-threshold behavior. No residual-range ranking or minutiae-floor
  change is allowed in this ticket.
- [x] Conclude only `confirmed`, `falsified`, or
  `inconclusive-because-[flaw]`, with one next experiment. Do not wire a
  driver rank until an offline enrollment-side branch first produces
  `add_res=0` and genuine own-template matches with controls intact.

## Known baseline

- Ticket-79/80 single-burst live inputs: `add_res=131` on every input,
  `stitched=0`, `1443B` degenerate template, and no self-match; dense control
  produced an approximately `22.8KB` stitched template and self-match 100.
- Ticket-79 `live8` repeated the same four press frames and still failed. It
  is not evidence for independent touch-count coverage.
- Ticket-80 third attempt PGM hashes and the exact capture output are in
  `80-closed-fuller-contact-retest.md`; the second attempt's PGM bytes were
  overwritten, so only its pasted capture output is usable.

## Predicted signatures

- **Touch-count explanation confirmed:** each isolated burst remains
  `add_res=131`, but a combined set of independent same-finger bursts begins
  stitching and yields a non-degenerate template with genuine matches;
  controls remain rejected.
- **Touch-count explanation falsified:** combined independent bursts still
  return `131/0` while dense control remains healthy. The next single branch
  is device/offline enroll-time shaping comparison, not a rank or floor
  change.
- **Inconclusive-because-[flaw]:** frame provenance is mixed/unknown, the DLL
  or template path is unavailable, or the controls are polluted by
  post-enroll quality state.

## Guardrails

- Offline first; no deployment or driver wiring in this ticket.
- Keep `GOODIX_5E0A_ENROLL_MIN_MINUTIAE=16`, the device enrollment stages,
  and the ticket-76 rank interface unchanged.
- Cite command output and file bytes. Treat post-enroll `q/ov` columns as
  state-polluted metadata; trust pre-enroll values and match outcomes.

## Provenance (2026-09-15, current disk — independently captured bursts)

Finger identity is user-asserted same-finger only (no cryptographic proof):
ticket-79 Step 0 "deliberate press + casual tap" same session/user implies same
finger; ticket-80 press2 is the same user's retest with the same capture
command. Confirm would have retro-corroborated identity; falsify below does
not rely on it (touch 1 rejects before any cross-touch comparison — see
verdict reasoning).

| Burst | Prefix | Active (>30) per _01.._04 | Capture output | SHA-256 full (`sha256sum` 2026-09-15, current disk) |
|---|---|---|---|---|
| 79 press (deliberate) | `legacy-experiments/live_burst_press` | 392/438/472/474 | ticket-79 verdict (active 392..474) | `_01 ac909d5355f8ca47596c6c4d79033d44b8d2c17bd019b3feecd51d78f7301eca` / `_02 9dcae997d399cdc7f97dd52195a8f8a11ad740ed0fb558a9e2e56ee7b768b08f` / `_03 ee5a72f4118c13722bd0f67e26fd5acfeb279564208c1fbc46a2e6835b4d2fca` / `_04 2fe13d85096c8599fa09b7668cc130c988c56c61111c114a64ca68a08414d726` (prefixes match 79:110-112) |
| 79 tap (casual) | `legacy-experiments/live_burst_tap` | 764/727/703/706 | ticket-79 verdict (active 703..764) | `_01 93e598fe15bcaae732472da3d22435924718fd939a8020c9f3bba78cd47aa469` / `_02 b31a61a967bd55e9dce98b07f29f7f70c05cee0bc9bf04ec317caf136f28d227` / `_03 1a9141e5ab3d6c6009170f03066be7cfc0abfa963ca8151f54d3d79041e99018` / `_04 80f2be905a8b88556c9128567795b6cc3b48bf1a701f37c4a80775122a7a8f02` (prefixes match 79:110-112) |
| 80 press2 third attempt | `legacy-experiments/live_burst_press2` | 272/283/276/265 | ticket-80 Try 2 third attempt (`min 0 max 487..496 avg 9.4..10.2`) | `_01 5da72b166b6cc3a06c5912a76a16929c80f8de068ec1823ef072b15782c5f1fb` / `_02 70c163a9c78f5dc5d53a43827f7d957a4e7b772e793e67d613ddf205615f53a4` / `_03 fd9ec8c64d62b4b15dbed9eebbced49f564f1a2a4d6174b02fedddfbe728d137` / `_04 acd6ee3f03ac032f80a7592be5c86d425fdfef36edbe735941d713a769ee16e5` (exact match 80:133-138) |

Excluded: press2 second attempt (`active 432/427/417/410`, ticket-80 Try 2
second block) was overwritten by the third attempt — console output only, no
byte claim, never used as image input. No post-overwrite PGM is treated as
the earlier attempt.

Frame order rule (fixed for all combo branches): burst-grouped `_04.._01`
per burst concatenated (the live-mode convention, no interleaving or
range-sorting), logged per touch as `[enroll-src] touch-order N/M <path>`:
combo8pt = press_04,03,02,01 + tap_04,03,02,01 (8 distinct); combo12 =
press_04..01 + tap_04..01 + press2_04..01 (12 distinct).

## Implementation (2026-09-15, offline harness only — no driver changes)

- `legacy-experiments/test_enroll_live_burst.c`: `enrol_imgs[8]` → `[16]`
  (combo12 needs 12; `max_images=16` already); new `combo8pt` (8 distinct
  press+tap burst-grouped, matches `live8` touch count to isolate
  independence at fixed total touches) and `combo12` (12 distinct all-burst
  round, gated dose-escalation after combo8pt) modes with fixed paths,
  per-touch `touch-order` pre-enroll logging (`range`, `q`, `ov`);
  `prefix` argv ignored for combos; `live`/`live8`/`densectrl` logic
  byte-identical (re-indented only); `*(ctx+8)=8` completion criterion and
  `max_images=16` untouched (touches 9–12 logged as extra beyond 100%);
  gain fixed at `1.0` driver-faithful; usage strings + header NOTE
  (ticket-79 `[VERDICT …]` macros are data-only; judge per ticket-81
  signatures; never cite post-enroll `q/ov`). Build:
  `gcc -O2 -o /tmp/opencode/enroll81 legacy-experiments/test_enroll_live_burst.c -lm`
  (exit 0; only pre-existing shim warnings, no new warnings in edited
  region). No `libfprint-driver/*`, no `tests/*` changes.
- Reviews: plan review (`ses_f5eba3145ffeWIFFtlxmWxAYq6`) required the
  burst-grouped order fix, combo12 gating, full re-hash, fresh-baseline
  re-runs, and identity-asymmetry rule — all applied; code review
  (`ses_f5eb5ea96ffeQW4nNB5M5dfQho`) 6/6 PASS; results review
  (`ses_f5eb437e6ffeHph4BUyBoO77yt`) agrees FALSIFIED; final file review
  (`ses_f5eb25f81ffeHE57G6yElxV8n8`) caught truncated hashes / reject
  granularity / representative-commands gaps — fixed with full 64-hex
  hashes, per-category reject breakdowns, all 7 commands, and pasted
  combo12 + densectrl excerpts.

## Offline result (2026-09-15, final binary `/tmp/opencode/enroll81`, `gain=1.0`, all exit 0)

| Branch | Touches | Per-touch `add_res` / stitched / progress | Pre-enroll q/ov | Packed | Live match (incl self) | Non-live reject (impostor / sparse / blank / noise) |
|---|---|---|---|---|---|---|
| isolated press (`live` press prefix) | 4 | `131`×4 / 0 / 0% | 0/0 ×4 (ranges 770.3/765.8/728.1/702.7) | 1443B | 0/12 | 5/5 (dense-A NO / seed68 NO / fingerprint NO / clear-0 NO / noise NO) |
| isolated tap (`live` tap prefix, NEW) | 4 | `131`×4 / 0 / 0% | 0/0 ×4 (ranges 908.0/915.0/923.0/935.0 in _04.._01 enroll order) | 1443B | 0/12 | 5/5 (same 5 categories, all NO) |
| isolated press2 (`live` press2 prefix) | 4 | `131`×4 / 0 / 0% | 0/0 ×4 (ranges 495.0/495.3/500.3/490.9) | 1443B | 0/12 | 5/5 (same 5 categories, all NO) |
| `live8` repeated control | 8 | `131`×8 / 0 / 0% | 0/0 ×8 | 1443B | 0/12 | 5/5 (same 5 categories, all NO) |
| `combo8pt` (8 DISTINCT press+tap) | 8 | `131`×8 / 0 / 0% | 0/0 ×8 | 1443B | 0/12 | 5/5 (press2 rows held out of enroll and also NO — cross-burst generalization fails too) |
| `combo12` (12 DISTINCT all bursts) | 12 | `131`×12 / 0 / 0% | 0/0 ×12 | 1443B | 0/12 (per-frame scores all 0 — see score excerpt) | 5/5 (dense-A NO / seed68 NO / fingerprint NO / clear-0 NO / noise NO) |
| `densectrl` positive control (same binary) | 8 | `0`×8 / 1..8 / 12%..100% | n/a (dense base) | 22822B (≈23110B ticket-72) | dense self-match 100; live 0/12 | 4/4 (seed68 NO / fingerprint NO / clear-0 NO / noise NO; dense-A is the self-match, excluded from negatives) |

Commands run (repo root, final binary `/tmp/opencode/enroll81`, all exit 0):

```text
gcc -O2 -o /tmp/opencode/enroll81 legacy-experiments/test_enroll_live_burst.c -lm
timeout 180 /tmp/opencode/enroll81 1.0 live legacy-experiments/live_burst_press
timeout 180 /tmp/opencode/enroll81 1.0 live legacy-experiments/live_burst_tap
timeout 180 /tmp/opencode/enroll81 1.0 live legacy-experiments/live_burst_press2
timeout 180 /tmp/opencode/enroll81 1.0 live8
timeout 180 /tmp/opencode/enroll81 1.0 combo8pt
timeout 180 /tmp/opencode/enroll81 1.0 combo12
timeout 180 /tmp/opencode/enroll81 1.0 densectrl
```

Key pasted output (combo12 enroll tail + score matrix, `gain=1.0`):

```text
[touch 1/12] add_res=131 stitched=0 progress=0% q_status=[100,100]
...
[touch 12/12] add_res=131 stitched=0 progress=0% q_status=[100,100]
[enrol] packed=1443 bytes pack_res=0
legacy-experiments/live_burst_press_01.pgm     | range=  702.7 active= 392 | q= 0 ov= 0 | score=    0 NO
legacy-experiments/live_burst_press2_01.pgm    | range=  490.9 active= 272 | q= 0 ov= 0 | score=    0 NO
legacy-experiments/live_burst_tap_01.pgm       | range=  935.0 active= 764 | q= 0 ov= 0 | score=    0 NO
legacy-experiments/live_dense_pad.pgm          | range=  727.4 active=5120 | q=12 ov=61 | score=    0 NO
legacy-experiments/live_dense_pad_seed68.pgm   | range=  703.8 active=5120 | q=14 ov=65 | score=    0 NO
legacy-experiments/fingerprint.pgm             | range=  394.1 active= 697 | q= 0 ov= 0 | score=    0 NO
legacy-experiments/clear-0.pgm                 | range=    0.0 active=   0 | q= 0 ov= 0 | score=    0 NO
white noise (synthetic)                        | range=      - active=   - | q=100 ov=100 | score=    0 NO
[result] live: 0/12 MATCH; non-live reject: 5/5
```

Key pasted output (densectrl control, same binary):

```text
[touch 1/8] add_res=0 stitched=1 progress=12% q_status=[100,100]
...
[touch 8/8] add_res=0 stitched=8 progress=100% q_status=[100,100]
[enrol] packed=22822 bytes pack_res=0
[control] dense self-match=yes-100 packed=22822B (ticket-72 template 23110B)
[result] live: 0/12 MATCH; non-live reject: 4/4; control self-match (dense-vs-dense): ok
```

## Verdict and closure

**Falsified (touch-count explanation).** Each isolated burst remains
`add_res=131`, and — decisively — the combined independent-burst sets also
return `131` on every touch (`combo8pt` 131×8, `combo12` 131×12,
`stitched=0`, 1443B degenerate, 0/12 including self) while the dense control
on the same binary stays healthy (`0`×8, 22822B, self-100, rejects intact).
Touch count across independent presses does not rescue enrollment.

Why not `inconclusive-because-provenance`: `touch 1/8` (combo8pt) and
`touch 1/12` (combo12) are byte-identical `press_04` input and `131` result
to isolated `touch 1/4`, running against a fresh `enrolStartEx` context with
no prior touches — no cross-touch identity comparison has occurred, so
`131` is per-frame rejection (extraction/quality gate), not inter-finger
mismatch. Count cannot rescue zero per-frame acceptance; dense touch-1
proves first-touch success is possible. Finger-identity ambiguity could at
most affect touches 2..N stitching, which is never reached.

No rank wiring, driver change, build, patch regen, or hardware-verify claim.
The single next experiment is the device/offline **enroll-time shaping
comparison** (same single-variable discipline: shaping/stitching-threshold
isolation only, enrollment floor `16` and ticket-76 rank interface
unchanged, offline first). Do not relitigate residual-range ranking or the
minutiae floor without new data.
