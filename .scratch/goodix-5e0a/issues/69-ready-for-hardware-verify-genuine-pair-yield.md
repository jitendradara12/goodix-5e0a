# 69 — Genuine-Pair Yield Shortfall (Rich Probe + Rich Gallery, Score < 14)

**What to build:** TBD by experiment below — either enrollment-coverage change or image-pipeline change. This ticket starts as a discriminating hardware experiment, not a code change.

**Blocked by:** 68 (floor verified at 16; unlock-consistency falsified — this is the prescribed falsify-branch successor).

**Status:** ready-for-hardware-verify

---

## 1. Problem & Evidence

Across tickets 65/68 hardware runs, probes with 15–23 minutiae against galleries with all templates 16–25 minutiae repeatedly score 3–11/14 (two probe>=20 misses: 20->11, 21->8). Genuine success ≈ 2/9 attempts. Pairing yield (~30–50%) sits far below the ≥87.5% needed for a 16-minutiae probe to clear 14. The floor is exonerated (no dead templates remain); the shortfall is pairing failure or image quality.

Two candidate causes:
- (a) Coverage/placement: natural taps land on pad regions/angles/pressures the 10-stage ladder did not capture (Bozorth tolerates ≤10% stretch, ≤11°).
- (b) Image quality: 3×3 residual contrast or bilinear 2× upscale blurs/clips ridges so minutiae pair poorly even on overlapping skin.

## 2. Discriminating experiment (user only, no code change)

1. `fprintd-delete`, re-enroll the 10-stage ladder, noting which stage is the firm-center pad press.
2. Attempt A (position duplicate): place the finger as exactly as possible like the firm-center enroll press, 3 taps. Paste `5e0a bz3 match` blocks.
3. Attempt B (natural): 3 casual taps at varied angles. Paste blocks.
- If A matches (≥14) but B misses → cause (a): enrollment coverage. Next lane: ladder/position guidance or stage-count revisit (within FAR budget, ticket 65 math).
- If even A misses despite probe>=20 → cause (b): image quality. Next lane: offline contrast/upscale analysis on captublack frames (no driver change until a dose wins on hardware pairs).
- Conclude only: (a) / (b) / inconclusive-because-[flaw] + the single next lane.

## 3. Invariants & Guardrails (AGENTS.md)

- Floor stays 16, threshold stays 14, stages stay 10. No driver change in this ticket until the experiment discriminates.
- Verify protocol in full every run (Phase 1 hands-off 60s + Phase-2 taps, AGENTS.md no-exceptions) and rule-7 smoke greps apply to every hardware run.

## 4. Predicted journal signatures

- Cause (a): `probe 20+ -> gallery[N] 15+/14 verify-match` on duplicated position; `probe 20+ -> max 8-11/14` on casual angles.
- Cause (b): `probe 20+ -> max < 14` on ALL attempts including careful duplicates.

---

## 5. Agent prep (2026-09-12 — no code change, runbook ready)

Frozen-state check (repo root, verified this session):

- `git status --porcelain` clean except this ticket; HEAD `2b93725` (ticket 68 closure).
- `libfprint-driver/goodix5e0a.h:45` `GOODIX_5E0A_ENROLL_MIN_MINUTIAE (16)`; `h:63` `GOODIX_5E0A_FRAMES_PER_TOUCH (4)`; `goodix5e0a.c:1688` `nr_enroll_stages = 10`; `c:1697` `bz3_threshold = 14`.
- `5e0a bz3 match` lines are `fp_dbg` (unified patch +4465/+4475) — debug env REQUIRED or Attempt blocks will be missing. `5e0a enrollment touch rejected` is `g_message` (c:1003) — always on.
- No driver/test/patch edits in this ticket. One variable per build: nothing.

### Runbook (user only — one go, paste the whole block)

One paste writes the runner, then executes it with the terminal as stdin
(prompts need a tty — bare `read` lines inside a raw paste would eat the
pasted lines themselves). The runner counts down the 60s hands-off,
prompts before each tap, survives `verify-no-match` (no `set -e` — misses
exit nonzero by design), and saves everything to `$LOG` for paste-back.

```bash
mkdir -p /tmp/opencode
cat > /tmp/opencode/t69-verify.sh <<'T69EOF'
#!/bin/bash
# Ticket 69 one-go verify. No `set -e`: misses exit nonzero by design.
sudo -v
LOG=/tmp/opencode/t69-verify-$(date -u +%Y%m%d-%H%M%SZ).log
# NOTE: local time — journalctl --since parses local tz; date -u once
# widened the window 5.5h and pulled stale sessions (fixed 2026-09-12, §6).
SINCE=$(date +"%Y-%m-%d %H:%M:%S")
echo "=== T69 run SINCE=$SINCE ===" | tee "$LOG"

# 0. Precondition: ticket-68 driver (gallery_len=10). If unsure, deploy first:
#    cd ~/NixOS-Hyprland && sudo nixos-rebuild switch --flake .# && sudo systemctl restart fprintd

# 1. Match-block logging (required — bz3 lines are fp_dbg)
sudo systemctl set-environment G_MESSAGES_DEBUG=all
sudo systemctl restart fprintd

# 2. Fresh ladder enroll: stages 1-3 firm pad, 4-5 medium, 6 light/offset,
#    7-8 tip+angle, 9-10 flanks. NOTE the firm-center stage number.
#    Glancing touches should reject: minutiae_count=N < 16 (format c:1003 %u < %d).
read -rp "ENTER to delete + re-enroll: "
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

# 5. Attempt B x3: casual taps, varied angles
for n in 1 2 3; do
  read -rp "Attempt B$n READY (casual placement), ENTER to verify: "
  date -u +"%Y-%m-%d %H:%M:%S UTC attempt-B${n}-holding" | tee -a "$LOG"
  fprintd-verify || true
  sleep 3
done

# 6+7. Collect match blocks + rule-7 smoke (tap verifies only, no held-finger
#    test here; smoke must be empty — ticket-53 scoping note in §5 header).
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
T69EOF
bash /tmp/opencode/t69-verify.sh
```

9. Verdict: conclude only (a) / (b) / inconclusive-because-[flaw] + the single next lane, per §2 branch logic. Paste back `$LOG` plus the firm-center stage number. If a match block is missing, the debug env (step 1) was not active — re-run with it.

---

## 6. Hardware run 2026-09-12 09:48–09:50 UTC (one-go script — inconclusive)

Full protocol executed via the §5 block (`t69-verify-20260912-094820Z.log`,
6/6 attempts with per-tap timestamps). Script flaw, cosmetic: `SINCE` used
`date -u` but `journalctl --since` parses local time — the window opened
5.5h early and pulled two stale sessions (15:12:05 PID 390501 match blocks,
15:12:18–50 PID 390614 enroll+verify). Mapping below uses PID fencing +
`enroll-completed` 15:18:39 (PID 395679) + the six consecutive PID-396646
blocks; stale sessions excluded. Fixed in §5 (local-time `SINCE`).

- Floor: PASS — 7× `enrollment touch rejected` (9,11,14,13,15,15,12 < 16,
  15:18:29–38), `enroll-completed` 15:18:39, gallery
  [17,19,22,27,21,16,17,16,18,16], all ≥ 16.
- Phase 1 (09:48:39–09:49:39 UTC = 15:18:39–15:19:39 local): silent — no
  match/enrollment lines in-window; rule-7 smoke grep empty across the run
  (no `timed out|Invalid ACK|verify-unknown-error|failed to`). PASS.
- Attempts (client UTC → journal local, +5:30):

| attempt | client UTC | journal | probe | max | result |
| A1 duplicate | 09:49:47 | 15:19:50 | 18 | gallery[3] 12/14 | no-match |
| A2 duplicate | 09:49:57 | 15:20:00 | 23 | gallery[8] 12/14 | no-match |
| A3 duplicate | 09:50:13 | 15:20:13 | 14 | gallery[1] 12/14 | no-match |
| B1 casual | 09:50:18 | 15:20:19 | 18 | gallery[3] 11/14 | no-match |
| B2 casual | 09:50:23 | 15:20:24 | 19 | gallery[8] 9/14 | no-match |
| B3 casual | 09:50:28 | 15:20:29 | 23 | gallery[2] 15/14 | MATCH |

(B3 prints gallery[0..2] only — driver stops at first threshold clear; normal.)

Verdict: inconclusive-because-[firm-center-stage-unreported]. Branch (a)
needs an A-match (0/3 — not met); branch (b)'s trigger (A miss despite
probe≥20: A2 23→12) is literally met, BUT A-fidelity is unverifiable
without the reference stage number, and B3's casual 23→15/14 proves the
pipeline CAN pair on this gallery — contradicting pure (b) as sole cause.

Single next experiment (cheap, no re-enroll — gallery above persists): 3×
Attempt-A taps vs the current gallery, reporting the firm-center stage
number + per-tap placement notes, pasting the 3 blocks. If A still misses
at probe≥20 → (b) confirmed, lane = offline contrast/upscale analysis on
captublack frames. If A matches → the original duplicate was off-position,
(a) coverage, lane = ladder/position guidance.
