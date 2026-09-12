# 70 — Enrollment Coverage Lane (Position Guidance / Stage-Count Revisit)

**What to build:** TBD — either enrollment position-guidance change or stage-count revisit within FAR budget. Successor of 69's firm-(a) verdict. Starts as spec + hardware-verify, one variable per build.

**Blocked by:** 69 (closed — cause (a) confirmed: verified stage-2 duplicates match 16–22/14 incl. 24→22/14; casual taps occasionally land between enrolled samples, e.g. 20→13/14; pipeline exonerated).

**Status:** closed (verdict: inconclusive-because-[no-probe≥20-tap-on-a-live-observed-gallery] — operator-closed 2026-09-12; N=14 ships, next experiment named below)

---

## 1. Problem & Evidence

Ticket 69 hardware runs (2026-09-12, §§6–8): faithful firm-center duplicates match 16–22/14 consistently, while casual taps at varied angles occasionally miss (B2 20→max 13/14) and off-position duplicates miss entirely (§6 A-set 0/3 incl. 23→12). The 10-stage ladder covers 10 pressure/angle/flank samples; taps landing between them have no overlapping template (Bozorth ≤10% stretch, ≤11°).

Two candidate lanes (pick ONE — one variable per build):
- (a1) Position guidance: steer enroll/verify presses toward enrolled coverage (no matcher/gallery change).
- (a2) Stage-count revisit: more/finer stages within ticket-65 FAR budget (K=10→1.09%, K=20→2.18% at threshold 14; ticket-43's K=96 blowout stays off-limits).

## 2. Invariants & Guardrails (AGENTS.md)

- Floor stays 16, threshold stays 14. 0x32 timeout 0, 0x34 finite guard/re-issue, TLS park TTLs, CANCELLED non-reissue untouched.
- One variable per build. Verify protocol (Phase 1 + Phase 2, no exceptions) and rule-7 smoke on every hardware run.

## 3. Predicted journal signatures

- Lane success: casual-tap genuine yield clearly above 69's band with `probe 20+ -> score 15+/14 verify-match` on first taps; `gallery_len` reflects the chosen lane; no `timed out|Invalid ACK|verify-unknown-error|failed to` outside the ticket-47/53 tolerant path.

---

## 4. Lane decision (2026-09-12): (a2) stage-count 10→14, (a1) declined

**Picked (a2).** Journal-backed reason (frozen-code rule): ticket 69 §8 gives
A-duplicates 3/3 at 16–22/14 (pipeline pairs at ~92% yield when skin overlaps
template) against B-casual 2/3 with B2 `probe 20 -> max 13/14` — exactly one
point short of threshold. The miss signature is a missing overlapping template
inside Bozorth tolerance (≤10% stretch, ≤11°), not blur. Densifying gallery
sampling in the natural-pressure central band directly targets that 1-point
gap with a single integer, a computable FAR cost, and a crisp
`gallery_len=14` journal signature.

**(a1) position guidance declined for this build** (not rejected forever):
- Verify-side steering is architecturally closed: `fpi_image_device_retry_scan`
  in verify deadlocks PAM (ticket 19) and is banned driver-wide (ticket 53) —
  the driver cannot steer a verify press in real time.
- Enroll-side per-stage steering needs stage visibility the driver does not
  have (core owns the stage counter; the driver sees only
  `FPI_DEVICE_ACTION_ENROLL`) plus new user-visible retry codes — at least two
  variables (visibility plumbing + guidance policy) with vague success
  criteria, against the one-variable rule.
- The ticket-65 pressure ladder already IS out-of-band position guidance; (a2)
  extends it (§6) rather than re-litigating it.
- If (a2) falsifies (casual probe≥20 taps still miss at 14 stratified stages),
  (a1) guidance is the named next lane — recorded, not lost.

## 5. FAR math (executed `python3 -c`, FMR=0.0011 premise ex tickets 43/65)

```text
K= 10 FAR=1.09%  P3(3-tap)=3.25%   (status quo, 1 finger x 10)
K= 14 FAR=1.53%  P3(3-tap)=4.52%   (THIS TICKET, 1 finger x 14)
K= 20 FAR=2.18%  P3(3-tap)=6.39%   (ticket-65 envelope cap, single finger)
K= 28 FAR=3.03%  P3(3-tap)=8.83%   (2 fingers x 14 — advise <=2 slots)
K= 96 FAR=10.03% P3(3-tap)=27.17%  (at threshold-14 FMR; the ticket-43 ~70%
                                    blowout was threshold-11 FMR~1.2% x K=96 —
                                    that regime stays off-limits regardless)
```

Single-finger K=14 → 1.53% sits inside the ticket-65 K≤20 (≤2.18%) envelope
with +0.44pp cost for +40% sampling. Two-finger K=28 → 3.03%: noted, still
~23× below the ticket-43 blowout; runbook advises ≤2 enrolled slots.

## 6. Prescribed 14-stage enrollment ladder (extends ticket-65 §3)

- Stages 1–3: central pad, **firm** (unchanged; stage 2 = firm-center
  reference for A-duplicate taps).
- Stages 4–6: central pad, **natural/medium** with slight rotation (±~5°) and
  millimeter shift (NEW density — was 2 samples, now 3; the B2-casual band).
- Stages 7–8: **light** pressure / slight offset.
- Stages 9–10: upper **tip + angled** pad.
- Stages 11–12: left/right **flanks** / tilt.
- Stages 13–14: user's own habitual **casual taps**, twice (captures the true
  natural placement distribution, no coaching).

Old 10-stage enrollments must be deleted first (`fprintd-delete`), or the
gallery stays len 10.

## 7. Acceptance criteria

- [ ] `libfprint-driver/goodix5e0a.c`: `dev_class->nr_enroll_stages = 14;`
  (+ rationale comment per rule 4). Nothing else in the driver changes:
  floor 16, threshold 14, burst (4), 0x32=0 / 0x34-guard / park TTLs /
  CANCELLED-non-reissue untouched, no new `g_message`.
- [ ] Pins synced: `test_f47` + `test_m2` + `test_f23` → 14.
- [ ] Unified patch regenerated from repo sources, byte-synced to
  `/home/sastauser/NixOS-Hyprland/modules/goodix/`; `test_m1_c1` SHA rolled.
- [ ] Build tree `/tmp/libfprint-goodix` in sync; ninja drivers-only clean.
- [ ] Full suite `bash tests/run_all_tests.sh` green.
- [ ] Hardware verify (§9): `gallery_len=14`, all `gallery[i]_nrows >= 16`,
  casual-tap yield above 69 §8's 2/3 band, rule-7 smoke per §9.

## 8. Predicted journal signatures (refined for N=14)

- Confirm: `5e0a bz3 match start: probe_nrows=20+ gallery_len=14`, first-tap
  `verify-match` on casual placements including previously-missing angles;
  B-set 3/3 (min bar: overall ≥5/6 with no probe≥20 capped at ≤13/14).
- Falsify: casual probe≥20 taps still score <14 despite 14 stratified stages
  → densification insufficient; next lane (a1) guidance (no re-litigation of
  floor/threshold/pipeline without new evidence).

## 9. Hardware runbook (user only — one go, paste the whole block)

Same shape as the ticket-69 §5 runner (local-time `SINCE`, debug env for
`fp_dbg` match blocks, no `set -e` since misses exit nonzero), extended to a
14-stage ladder enroll + 3 A-duplicate (stage-2) + 3 B-casual taps:

```bash
mkdir -p /tmp/opencode
cat > /tmp/opencode/t70-verify.sh <<'T70EOF'
#!/bin/bash
# Ticket 70 one-go verify. No `set -e`: misses exit nonzero by design.
sudo -v
LOG=/tmp/opencode/t70-verify-$(date -u +%Y%m%d-%H%M%SZ).log
SINCE=$(date +"%Y-%m-%d %H:%M:%S")
echo "=== T70 run SINCE=$SINCE ===" | tee "$LOG"

# 1. Match-block logging (required — bz3 lines are fp_dbg)
sudo systemctl set-environment G_MESSAGES_DEBUG=all
sudo systemctl restart fprintd

# 2. Fresh 14-stage ladder enroll per ticket-70 §6 (1-3 firm, 4-6
#    natural+rotation, 7-8 light, 9-10 tip+angle, 11-12 flanks,
#    13-14 habitual casual). NOTE the firm-center stage number (expect 2).
#    Glancing touches should reject: minutiae_count=N < 16.
read -rp "ENTER to delete + re-enroll (14 stages): "
fprintd-delete "$USER" || true
fprintd-enroll || true

# 3. Phase 1: hands off 60s, expect silence (blocking 0x32 wait, no timeouts)
date -u +"%Y-%m-%d %H:%M:%S UTC hands-off" | tee -a "$LOG"
echo "Hands off the sensor for 60s..."
for i in $(seq 60 -1 1); do printf "\r  %ss left " "$i"; sleep 1; done; echo
date -u +"%Y-%m-%d %H:%M:%S UTC hands-off-end" | tee -a "$LOG"

# 4. Attempt A x3: EXACT duplicate of the firm-center enroll press
for n in 1 2 3; do
  read -rp "Attempt A$n READY (finger placed like firm-center), ENTER to verify: "
  date -u +"%Y-%m-%d %H:%M:%S UTC attempt-A${n}-holding" | tee -a "$LOG"
  fprintd-verify || true
  sleep 3
done

# 5. Attempt B x3: casual taps, varied angles (the ticket-69 miss band)
for n in 1 2 3; do
  read -rp "Attempt B$n READY (casual placement), ENTER to verify: "
  date -u +"%Y-%m-%d %H:%M:%S UTC attempt-B${n}-holding" | tee -a "$LOG"
  fprintd-verify || true
  sleep 3
done

# 6+7. Collect match blocks + rule-7 smoke (tap verifies only, no held-finger
#    test here; smoke must be empty — ticket-53 scoping note).
{
echo "--- match blocks ---"
journalctl -u fprintd --since "$SINCE" --no-pager | grep -E "5e0a bz3 match|verify-match|verify-no-match|enrollment touch rejected|enroll-completed"
echo "--- rule-7 smoke (empty = PASS) ---"
journalctl -u fprintd --since "$SINCE" --no-pager | grep -E "timed out|Invalid ACK|verify-unknown-error|failed to"
echo "(smoke section end)"
} | tee -a "$LOG"

# 8. Debug off
sudo -v
sudo systemctl unset-environment G_MESSAGES_DEBUG
sudo systemctl restart fprintd
echo "DONE. Paste back $LOG + firm-center stage number."
T70EOF
bash /tmp/opencode/t70-verify.sh
```

Verdict per §8 branch logic (confirm / falsify / inconclusive-because-[flaw]
+ the single next lane). Deploy first if unsure the driver is live:
`cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# &&
sudo systemctl restart fprintd` — then confirm `gallery_len=14` in the log.

---

## 10. Agent implementation (2026-09-12 — code complete, awaiting hardware verify)

- Lane: (a2), one variable only: `dev_class->nr_enroll_stages` 10→14
  (`libfprint-driver/goodix5e0a.c:1685-1691`, +5/-3 comment lines stating the
  ticket-69 journal reason, Bozorth tolerance, and single-finger FAR).
  Untouched: floor 16, threshold 14, burst (4), contrast 1.0f, 0x32=0 /
  0x34-guard / park TTLs / CANCELLED-non-reissue, no new `g_message`.
  Non-empty LOC 1507/1525 (test_m2 budget holds).
- Tests: `test_f47` (docstrings + pin), `test_m2` (vtable literal), `test_f23`
  (name + docstrings incl. stale "12 stages" Requirements drift + pin) →
  14; `test_m1_c1` patch SHA rolled `c7fc32c2…` → `7f4718a1…`. Mock
  `range(1,9)` enroll loops left alone per ticket-31 (protocol, not count).
- Docs: README operating point 5→14 stages (was stale two tickets behind);
  PROGRESS staged-patch line rolled to new SHA + ticket-70 state.
- Patch: `goodix5e0a.c` new-file section regenerated from repo source
  (`/tmp/opencode/regen_5e0a_c_section.py`; hunk `+1,1702`→`+1,1704`, index
  blob `45ae1bb`→`f892649` ex `git hash-object`); `.h` section untouched;
  repo patch `sha256sum 7f4718a1…` byte-identical to
  `/home/sastauser/NixOS-Hyprland/modules/goodix/`; `test_f25` 9/9 OK.
- Build tree: `/tmp/libfprint-goodix` `goodix5e0a.c/h` `diff -q` in sync;
  ninja drivers-only clean (`[3/3] Linking target libfprint-2.so.2.0.0`).
- Suite: `bash tests/run_all_tests.sh` → 459 passed / 0 failed / 1 skipped
  (env-gated native C harness absent, same as tickets 65/68); touched
  modules singly 43 OK + 1 skip.
- FAR table (§5) and the ticket-43 regime check (FMR=1.2% × K=96 → 68.6%,
  matches 43's ~70%) both from executed `python3 -c`, not copied text.
- Independent reviews: two general subagents (driver/invariants +
  tests/patch/docs) — reports below.
- Review 1 (driver/invariants — `ses_f6ae49a7affeVPXObAFk2zwuEx`): PASS, no
  load-bearing issues. Verified in code: 0x32 stays 0 (c:1187-1190, :751-753),
  0x34 guard/normal 2000/5000 + still-down re-issue + release-arms-DOWN
  untouched, park TTLs + destroy-branch-only clears intact (rule 3),
  CANCELLED never re-issues on all three loops, floor/threshold/burst
  unchanged, no new `g_message`, rationale comment present (rule 4);
  `git diff -- libfprint-driver/` = single hunk (one variable);
  FAR table recomputed independently, exact match; no driver-side
  gallery/stage array sized for 10 (only unrelated `data[10]` byte index).
  Nit recorded-not-applied: "between the 10 samples" → "the former 10
  samples" — rejected as churn: the clause already scopes to the prior
  ladder via "the ticket-65 ladder" + past-tense ticket-69 citation, and any
  comment touch forces a patch regen + SHA roll for zero behavior gain.
- Review 2 (tests/patch/docs — `ses_f6ae49a78ffeL68u8EKQ0jQcY8`): FAIL with
  one must-fix, now fixed: `README.md:61` "Known limitations" still claimed
  "enrolls 5 stages" (stale since ticket 65, missed by the agent's
  `10-stage`-pattern grep) contradicting the new operating point — fixed
  `5`→`14` (README is not embedded in the patch: SHA `7f4718a1…` stands, no
  regen). Otherwise PASS: zero stale pins repo-wide (f47:123, m2:47,
  f23:23 all assert 14; `range(1,9)` mock loops confirmed count-independent
  per ticket 31); `.c` section independently reconstructed byte-identical
  (1704 `+` lines, hunk matches, blob `f892649` == `git hash-object`);
  repo↔NixOS patch byte-identical; `.h` section untouched; ARCHITECTURE.md /
  PROGRESS history rows / ORIGINAL_REQUEST correctly left frozen; affected
  modules re-run 43 OK + 1 env skip.
- Hardware verify: user-only per §9 runbook (needs `nixos-rebuild switch`
  + `fprintd-delete` + 14-stage ladder; agent never touches hardware).

### Hardware verify protocol (user only — do NOT run as agent)

Paste the §9 block in one go. Deploy first if the driver may be stale
(`cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# &&
sudo systemctl restart fprintd`), confirm `gallery_len=14` in the log, then
conclude only per §8 (confirm / falsify / inconclusive-because-[flaw] +
the single next lane).

### Agent re-verify (2026-09-12 — in-progress → ready-for-hardware-verify)

- Re-ran acceptance: `python3 -m unittest
  tests.tier1_feature.test_f47_verify_retry_release_guard
  tests.tier1_feature.test_m2_driver_refactoring
  tests.tier1_feature.test_f23_pam_reliability
  tests.tier5_adversarial.test_m1_c1_lifecycle_adversarial` → 34 tests OK
  (1 env skip); `bash tests/run_all_tests.sh` → 459 passed / 0 failed /
  1 skipped (env-gated native C harness absent).
- Driver diff single hunk (`@@ -1682,10 +1682,12 @@`, `nr_enroll_stages`
  10→14 + rule-4 comment); no `g_message` change; no stale `= 10` pins
  (`goodix511.c:315 = 20` is the unrelated 511 driver).
- Patch `sha256sum 7f4718a1…` repo-side byte-identical to
  `/home/sastauser/NixOS-Hyprland/modules/goodix/`; build-tree `.c`/`.h`
  `diff -q` in sync; forced ninja drivers-only rebuild clean
  (`[3/3] Linking target libfprint-2.so.2.0.0`).
- Transition: filename + Status header moved together per AGENTS.md
  (`70-in-progress-…` → `70-ready-for-hardware-verify-…`). No driver/test
  content changed in this transition.

### Live check (2026-09-12 — user-run, NOT full §9 verify)

- Pasted user output (`/tmp/opencode/t70-live-20260912-165638Z.log`):
  14× `enroll-stage-passed` (+6× `enroll-swipe-too-short` retries on
  light/tip/flank placements) → `enroll-completed`; single verify
  `verify-match (done)`.
- Journal: `5e0a bz3 match start: probe_nrows=19 gallery_len=14
  (probe_len=136)`; `gallery[0]_nrows=28 score=17/14`; smoke section empty.
- Meaning: deployed driver is live at N=14; first-tap 19→17/14 clears
  threshold 14 (positive signal toward §8 confirm branch, but N=1 tap only —
  no A/B yield, no Phase 1, no floor sweep). Status stays
  `ready-for-hardware-verify`; full §9 (3×A + 3×B) still required for
  confirm/falsify verdict.

### Follow-up taps (2026-09-12 — unscored, debug-off)

- User ran 4× `fprintd-verify` after the live script exited: 2×
  `verify-match`, 2× `verify-no-match` (client text only, no scores).
- Pulled `journalctl --since "30 min ago" | grep -E "5e0a bz3 match|
  verify-match|verify-no-match" | tail -n 30`: the only scored blocks are
  (a) 22:25:15 pid 197644 probe 22 → visible max 10/14 `verify-no-match`
  (gallery[0..6] cut off by tail), (b) 22:25:20 pid 197644 full block
  probe 20 → max 13/14 (gallery[13]) `verify-no-match`, (c) 22:27:11 pid
  198922 probe 19 → gallery[0] 17/14 `verify-match`.
- Timeline (corrected after re-enroll confirmation): (a)+(b) are gallery A
  (pre-live-check, pid 197644, `gallery_len=14` per the 22:25:20 start line)
  — unobserved enrollment, so its probe-20→13 miss is a flag, not a verdict
  (see Second-firm-pair section). (c) is the in-script tap on gallery B. The 4 post-script
  taps ran after step-8 `unset-environment + restart` (debug off), so they
  left no `bz3` blocks — new-gallery yield stands at 3/5 client-side (1
  scored match + 2 unscored matches vs 2 unscored misses) =
  inconclusive-because-[misses-unscored]. Verdict still requires scored
  casual taps on the current gallery (debug on).

### Scored triple (2026-09-12 ~22:32 IST, pid 202907, gallery_len=14)

- User pasted 3× `verify-no-match` with full blocks, all `gallery_len=14`:
  probe 12 → max 7/14 (gallery[1]); probe 18 → max 8/14 (gallery[9]);
  probe 14 → max 6/14 (gallery[2]). No probe≥20 → below the §8 falsify bar
  (casual probe≥20 capped ≤13); these are weak-probe misses, not lane-(a2)
  evidence either way.
- Floor holds on the new gallery: nrows 28/18/22/26/23/17/25/17/16/24/16/
  25/18/24, all ≥16 (§7 floor check passes for this enrollment).
- Scored new-gallery tally: 1/4 (19→17/14 match + 12/18/14 weak misses);
  with the 4 unscored post-script taps (2/2) the client-side total is 3/8.
  Verdict: still inconclusive-because-[no probe≥20 scored tap on the new
  gallery]. Discriminating next: 2–3 FIRM center-press taps (enroll-1–3
  duplicates) with debug on — matches at 15+ would show the gallery pairs
  when skin overlaps, isolating these misses to placement/pressure.

### Firm-press pair (2026-09-12 ~22:33 IST, pid 203518, gallery_len=14)

- 2× firm-center taps: probe 16 → max 11/14 (gallery[1]) + 10/14
  (gallery[11]) `verify-no-match`; probe 17 → gallery[0]_nrows=28 score
  17/14 `verify-match` (early exit, same template as the 22:27 19→17 match).
- Scored new-gallery tally now 2/6 (matches: 19→17, 17→17 both on
  gallery[0]; misses: 12/18/14 weak + 16→11 mid). Still zero probe≥20
  scored taps on the new gallery → §8 confirm/falsify bar unreached:
  inconclusive-because-[taps landing 12–19, no strong-probe sample].
  Pattern so far: gallery pairs at 17 when skin overlaps gallery[0], scores
  fall to ≤11 otherwise — placement/pressure spread, not yet a gallery-gap
  verdict. Next (if willing): 2–3 full-pad firm presses held ~1s to push
  probe≥20, then score per §8.

### Second firm pair (2026-09-12 ~22:35 IST, pid 204990, gallery_len=14)

- 2× firm presses, both `verify-match`: probe 19 → max 14/14
  (gallery[11]_nrows=23); probe 19 → max 15/14 (gallery[13]_nrows=23).
  Same-tap runner-up 13/14 (gallery[7]) on tap 2 — pairing across
  flank/tip templates, not just gallery[0].
- ANOMALY RESOLVED 22:36+ IST: user confirmed a from-scratch re-enroll at
  ~22:34–22:35. Three distinct N=14 galleries tonight: (A) pre-live-check
  (pid 197644), (B) live-check enroll 22:27 (gallery[0]=28…), (C) current
  re-enroll (gallery[11/13]=23…). Restarts never changed anything.
- FLAG on gallery A (unobserved enroll, ladder compliance unknown): its
  22:25:20 block is `gallery_len=14`, probe 20 → max 13/14 (gallery[13])
  `verify-no-match`; 22:25:15 probe 22 → visible max 10/14 over
  gallery[7..13] only ([0..6] cut off by tail, max unassertable). The
  probe-20→13 point literally matches the §8 falsify signature — but single
  tap on a deleted gallery from an unobserved enrollment, so a caution flag,
  not a verdict. Follow-up must be probe≥20 taps on gallery C.
- Grouped standing: A 0/2 scored (both strong-probe misses); B 2/6 scored
  (19→17, 17→17 matches; 12/18/14 weak + 16→11 mid misses) + 4 unscored
  client-side taps (2/2); C 2/3 scored (19→14, 19→15 matches + 16→10
  miss). No probe≥20 on B or C — §8 bar unreached on any live gallery.
  Status unchanged.

## 11. Close (2026-09-12 — inconclusive, operator-closed tonight)

Scored record on N=14 galleries (all `gallery_len=14`, floor ≥16 everywhere):

| gallery | probe→max | result | weight |
|---|---|---|---|
| A (unobserved enroll, deleted) | 20→13, 22→≤10 (partial block) | 0/2 miss | flag only |
| B (§6 ladder enroll 22:27) | 19→17 match; 12→7, 18→8, 14→6, 16→11 miss; 17→17 match | 2/6 | full |
| B unscored (debug off) | client text only | 2/2 | none |
| C (re-enroll ~22:35) | 16→10 miss; 19→14, 19→15 match | 2/3 | full |

- Confirm bar (§8: B-set 3/3, min overall ≥5/6, no probe≥20 capped ≤13):
  NOT met — scored total 4/11, no casual-tap set.
- Falsify bar (§8: casual probe≥20 still <14 on stratified N=14): NOT met —
  sole probe≥20→13 datum is gallery A (unobserved enroll, deleted, n=1).
- Verdict: **inconclusive-because-[operator's taps land probe 12–19; zero
  probe≥20 taps on any live observed gallery, and full §9 declined]**.
  Lane (a2) neither confirmed nor falsified. N=14 ships as-is: floor holds
  on all three enrollments, firm overlapping presses pair 4/5 (17, 17, 14,
  15), no regressions in rule-7 smoke (empty in every scoped window).
- Single next experiment (gallery C still enrolled, ~3 min whenever
  convenient): debug-on session, 3 firm full-pad ~1s presses; confirm on
  ≥2/3 match with any probe≥20 scoring 15+, falsify on any probe≥20 capped
  ≤13. If falsified, named lane is (a1) guidance per §4.
