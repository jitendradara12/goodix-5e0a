# 70 — Enrollment Coverage Lane (Position Guidance / Stage-Count Revisit)

**What to build:** TBD — either enrollment position-guidance change or stage-count revisit within FAR budget. Successor of 69's firm-(a) verdict. Starts as spec + hardware-verify, one variable per build.

**Blocked by:** 69 (closed — cause (a) confirmed: verified stage-2 duplicates match 16–22/14 incl. 24→22/14; casual taps occasionally land between enrolled samples, e.g. 20→13/14; pipeline exonerated).

**Status:** ready-for-agent

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
