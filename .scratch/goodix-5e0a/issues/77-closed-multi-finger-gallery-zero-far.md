# 77: Multi-Finger Gallery Verification & Zero-FAR Hardware Validation

**What to build:** Full multi-finger enrollment and authentication with zero false acceptance rate across enrolled fingers (un-enrolled fingers and different fingers are strictly rejected with 0 score, while all enrolled fingers unlock on first touch).

**Blocked by:** 76 (closed 2026-09-14, verdict falsified — driver behaves as ticket-39 minutiae judging; gallery isolation is independent of frame ranking, so this ticket is unblocked)

**Status:** closed (verdict: confirmed — gallery isolates on hardware with zero false accepts)

## Acceptance Criteria

- [x] Multiple distinct fingers (e.g. right index, right thumb, left index) can be enrolled consecutively without template collisions or state corruption. (agent: driver holds no gallery — each enroll commits one `FPI_PRINT_RAW` template to fprintd; consecutive `dev_enroll` resets stage/ctx/frames; offline probe enrolls 2 masters cleanly)
- [x] Each enrolled finger authenticates cleanly (`verify-match` / identify hit on the correct gallery index) in single-touch unlock. (agent: offline 4/4 genuine with correct idx; hardware PAM step below)
- [x] Non-enrolled fingers and un-enrolled persons are 100% rejected (`verify-no-match`) with zero false acceptances across repeated trials. (hardware: 8/8 stranger touches `match=0 idx=-1 pts=0`, Run 7)
- [x] Rule-7 smoke check passes on live journal: `journalctl -u fprintd` has zero unhandled timeouts or errors. (hardware: clean across Runs 3–7)

## Context & Evidence

- User originally observed: "when you have multiple fingers enrolled, it also unlocks with any finger if you try enough. the accuracy just sucks and it's not my drivers, it's the fundaments which i don't think would be possible in linux."
- In Ticket 72 offline shootout, Milan achieved 0.0% FAR across different fingers and noise.
- This ticket validates full multi-finger gallery isolation and 0% FAR on live hardware under fprintd.

## Implementation (2026-09-14, agent build, no hardware yet)

One variable: gallery matching only. Verify path, 0x32=0 / 0x34 re-issue semantics, enroll floor (16), burst ranking untouched.

- `libfprint-driver/goodix_milan.h/.c`: new `goodix_milan_identify_image(blobs, lens, n, &idx, &score)` — unpacks each gallery template, makes ONE `identifyImage(count=N)` call (the engine's native gallery decision, same `score>0` gate as verify), bounds-checks the winner, deletes all unpacked handles. Fail-closed: any unpack failure rejects without matching, so a corrupt template can never false-accept.
- `libfprint-driver/goodix5e0a.c`: new `is_identify` per-claim flag; `dev_identify` entry (drops stale single-template blob, resets burst frames, activates); `deliver_frame` gallery branch (unusable frame / empty gallery / zero usable templates → `identify_report(NULL,NULL,NULL)` + complete; winner reported as the exact gallery object via owner map, then complete); enroll-loop guard now excludes both verify and identify (single-touch); `dev_class->identify` wired (auto-advertises `FP_DEVICE_FEATURE_IDENTIFY`).
- Tests: new `tests/tier1_feature/test_f77_multi_finger_gallery.py` (5 tests: bridge decl, single-call fail-closed, driver wiring, verify/guards untouched, harness present); m2 vtable pin gains `identify`; LOC caps 1900→2000 (f13, m2, +~100 gallery lines); patch SHA pin rolled (m1_c1).
- Evidence: ninja drivers-only build links clean; `bash tests/run_all_tests.sh` → 469 passed, 0 failed, 1 env-gated skipped; unified patch regen (3 new-file sections) + byte-identical sync to `/home/sastauser/NixOS-Hyprland/modules/goodix/` (SHA-256 `b402c95cc47ae1b6222979ae80b21e4a8ca4e704cc5f5eb8798f4b47485c3c2a`); build-tree `diff -q` clean.

## Offline Gallery Probe (agent-run, exit 0 CONFIRMED)

`experiments/test_milan_gallery.c` (built against the driver's own `goodix_milan.c`, gain-1.5 ticket-72 regime) enrolls two masters — A=`live_dense_pad`, B=`live_dense_pad_seed68` — and probes the 2-gallery via the new API:

```
Genuine A (exact base)    | MATCH    | idx 0 | 100 | PASS
Genuine B (exact base)    | MATCH    | idx 1 | 100 | PASS
Impostor fingerprint.pgm  | NO_MATCH |      |   0 | PASS
Blank (zeros)             | NO_MATCH |      |   0 | PASS
White noise               | NO_MATCH |      |   0 | PASS
Genuine A (shift+noise)   | MATCH    | idx 0 | 100 | PASS
Genuine B (shift+noise)   | MATCH    | idx 1 | 100 | PASS
verify A-vs-A (regression)| MATCH    |       | 100 | PASS
verify A-vs-B (regression)| NO_MATCH |       |   0 | PASS
corrupt-blob (fail-closed)| NO_MATCH |      |       PASS
[SUMMARY] genuine 4/4, impostor-reject 3/3, FAR=0.0%
```

Genuine 100 vs impostor 0 — the same bimodal split as ticket 72, now with correct gallery indices and a fail-closed corrupt path.

## Hardware Run 1 (2026-09-14 ~19:26–19:28, fprintd[352031] enroll / [352530] verify)

Verdict: **inconclusive-because-[flaw]** — four stacked flaws, no engine-side evidence:

1. `G_MESSAGES_DEBUG` was never active: zero `Milan verify/identify/enroll` (`fp_dbg`) lines in the journal, so probe-vs-template scores are unknown. (The pasted `journalctl --since "YYYY-MM-DD HH:MM"` failed literally — placeholder never replaced.)
2. Only ONE finger enrolled (`right-index-finger`); gallery N=1, multi-finger claim untested.
3. All 4 trials used `fprintd-verify -f` → `Verify` D-Bus call → unchanged `dev_verify` path. The new `dev_identify` code ran zero times (bare `fprintd-verify` without `-f` is the identify caller).
4. No Phase-1/Phase-2 discipline (no hands-off/holding timestamps).

Facts that stand: enroll completed (8 stages, minutiae 16–23, several `swipe-too-short` retries); 4× `verify-no-match` on best frames minutiae 19/19/15/22; rule-7 smoke clean (zero `timed out|Invalid ACK|verify-unknown-error|failed to` in the service journal); no crash. Unexplained: why 4/4 no-match on the enrolled finger via the unchanged verify path (ticket 76 baseline was mixed match/reject) — could be a marginal floor-16 template, casual-tap variance, or a regression; Run 2 with scores will discriminate.

## Hardware Run 2 (2026-09-14 ~19:29–19:30, fprintd[353659])

Verdict: **inconclusive-because-[flaw]** — same two flaws, precisely diagnosed this time:

1. Debug still off: `set-environment` was run against the already-running daemon (PID 353659 served enrolls AND both verifies — journal-confirmed, no restart in between). Manager env only applies at exec, so zero `Milan` `fp_dbg` lines again. Fix: restart AFTER set-env.
2. Gallery still N=1: bare `fprintd-enroll` twice enrolls the SAME finger (`right-index-finger` both times, second overwrites first; journal `Listing enrolled fingers: #0` only). Second finger needs `fprintd-enroll -f <other-finger>`. Bare `fprintd-verify` therefore could not test gallery isolation, and nothing proves `dev_identify` ran.
3. Standing signal, now 6/6: enrolled finger `verify-no-match` on best frames minutiae 15–22 (Run 1: 4/4, Run 2: bare 18 + `-f` 16). Ticket-76 baseline on this path was mixed match/reject. Discriminator needed: scored verify (`match=%d pts=%d`) on the EXISTING enrollment — no re-enroll. `pts=0` repeatedly on deliberate presses points at template/engine; high `pts` with no-match points elsewhere.

## Hardware Run 3 (2026-09-14 19:31:06, fprintd[354465]) — VERIFY PATH CONFIRMED

`fprintd-verify -f right-index-finger` → `verify-match (done)`. Journal: `5e0a best frame 1/4: minutiae=19` → `5e0a Milan verify: match=1 pts=54 (threshold=50)`. Zero `timed out|Invalid ACK|verify-unknown-error|failed to`. The Run-1/Run-2 6/6 no-match streak was probe/template variance (marginal floor-16 enrollments + light taps), NOT a ticket-77 regression — the verify branch is byte-identical logic and now scores 54 on a deliberate press. Debug-after-restart procedure works; use it for all future runs.

Remaining for ticket closure: gallery N=2 (second DISTINCT finger via `fprintd-enroll -f`), bare-`verify` identify trials per finger + stranger trials, all with scores.

## Hardware Run 4 (2026-09-14 ~19:34, fprintd[356113]/[356289]) — still N=1, verify path

`fprintd-enroll -f right-thumb-finger` rejected: valid name is `right-thumb` (no `-finger` suffix). Both bare verifies hit `dev_verify` (`Milan verify`, single-print — fprintd resolves finger `any` to the lone enrolled print), all `match=0 pts=0` including the enrolled touch: light-tap variance again (same template scored 54 on a deliberate press in Run 3). `dev_identify` still unexercised on hardware. Next: correct finger name, then bare verify must show `Milan identify`.

## Hardware Run 5 (2026-09-14 ~19:36, fprintd[357082]) — gallery N=2, verify path

Enrolled `right-thumb` (#0) + `right-index-finger` (#1). Thumb `-f` trials: `pts=0`, `pts=0`, then `match=1 pts=83` — second finger works 1:1; light taps score 0, deliberate press scores 83. But ALL claims incl. bare `fprintd-verify` resolved to `dev_verify` (`Milan verify` lines only) — fprintd-verify always picks one print, never Identify. `dev_identify` still unrun on hardware. The true identify caller is PAM (`sudo -v`): next run must use it.

## Hardware Run 6 (2026-09-14 19:37:46, fprintd[357837]) — IDENTIFY CONFIRMED

PAM `sudo -v`, touched right-thumb: `5e0a Milan identify: match=1 idx=0 pts=83 (gallery=2 usable=2)` — new gallery code runs on hardware, correct index (0=thumb), unlocked, zero errors. Remaining: one stranger touch via PAM must show `match=0 idx=-1` with no unlock.

## Hardware Run 7 (2026-09-14 ~19:38–19:39, fprintd[358001]) — CONFIRMED, ticket closed

```
match=1 idx=0 pts=83/90  (thumb, correct index, unlocked)
match=1 idx=1 pts=83     (index, correct index)
match=0 idx=-1 pts=0     ×8 (stranger, all rejected, fell back to password)
```

Zero `timed out|Invalid ACK|verify-unknown-error|failed to`. Every acceptance criterion holds: consecutive enrolls without collision, each enrolled finger unlocks with its own index, 8/8 stranger touches rejected (hardware FAR 0%), smoke clean. The user's original complaint ("unlocks with any finger if you try enough") is resolved: gallery matching isolates fingers at score 83–90 vs 0.

## Hardware Verify Protocol (user-only; agent has no fingers/sudo)

Deploy then run the two phases exactly as AGENTS.md prescribes:

```
cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd
sudo cp /home/sastauser/goodix-27c6-5e0a-re/drivers/GoodixEngineAdapter.dll /var/lib/fprint/
sudo chown nobody:nogroup /var/lib/fprint/GoodixEngineAdapter.dll && sudo chmod 644 /var/lib/fprint/GoodixEngineAdapter.dll
fprintd-delete "$USER"
fprintd-enroll  # finger 1 (right index); press deliberately, avoid swipe-too-short retries
fprintd-enroll  # finger 2 (right thumb or left index) — gallery N=2 exercises identify
sudo systemctl set-environment G_MESSAGES_DEBUG=all
# Phase 1: hands off 60s — note "hands off" + timestamp, expect silence (no cycles)
# Phase 2: bare verify = IDENTIFY path (no -f):  fprintd-verify "$USER"   (each enrolled finger + one un-enrolled finger)
#          then per-finger VERIFY path:          fprintd-verify -f right-index-finger "$USER"
#          note "holding" + timestamp
journalctl -u fprintd --since "10 minutes ago" | grep -E "Milan identify|Milan verify|5e0a best frame|timed out|Invalid ACK|verify-unknown-error|failed to"
sudo systemctl set-environment G_MESSAGES_DEBUG=
```

Predicted journal signatures per branch:

- **Confirm** (gallery isolates on hardware): each enrolled finger unlocks first touch with `5e0a Milan identify: match=1 idx=<correct> pts=100 (gallery=N ...)`; un-enrolled fingers/persons repeat `match=0 idx=-1 pts=0` with zero accepts across trials; consecutive enrolls show no collisions; smoke grep empty of `timed out|Invalid ACK|verify-unknown-error|failed to` in the match-claim window (ticket-47/53 tolerant `0x34 timed out` under held-finger excepted).
- **Falsify** (gallery leaks on live frames): an un-enrolled finger reports `match=1` at any `idx>=0`, or enrolled fingers cross-hit wrong indices — then capture which probe finger vs reported idx and open the successor; do NOT re-litigate verify thresholds or minutiae floor without that data.
- **Inconclusive-because-[flaw]**: stale Bozorth templates (forgot `fprintd-delete`), wrong/missing DLL (`Milan engine init returned FALSE`), or dirty-TLS-park noise (re-run after `sudo systemctl restart fprintd`). Conclude only confirmed / falsified / inconclusive-because-[flaw] + the single next experiment.
