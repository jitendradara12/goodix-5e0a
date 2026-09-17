# 95: Integrate results and prepare one final hardware batch

**What to build:** One short checklist using the tools from 89–94, so the user tests the merged work once at the end.

**Blocked by:** None. The user's final hardware batch ran 2026-09-17 17:28–17:45 IST.
**Status:** closed

**Verdict:** software integration confirmed (368 local / 366 clean-clone,
explicit skips named); hardware run completed with evidence folder
`/home/sastauser/goodix-final-20260917-172810-qt3hNS`. Per-ticket hardware
conclusions below. The batch was aborted mid-flow by the operator's
fingerprint-gated sudo and repaired inline; see deviations.

**Owns:** Integration report and batch checklist; no driver changes.

- [x] Record the combined software suite and unresolved defects, reusing the prior passing integration run rather than rerunning it for documentation-only changes.
- [x] Provide configurable commands for labeled matching samples, resume recovery, activation timing and idle resource sampling. Keep privileged operations, fingerprint claims and suspend user-only.
- [x] Reuse existing tools, isolate idle sampling from claims, and save evidence together. No per-ticket user checkpoints or hardcoded finger required.

## Hardware run record, 2026-09-17 (folder goodix-final-20260917-172810-qt3hNS)

- Setup: `--no-timeout` confirmed in ExecStart; daemon restarted 17:29:20,
  PID 29796, which remained MainPID for the entire batch (pre-sleep,
  post-resume and post-claim snapshots identical). This also re-confirms
  ticket 88 on this build: the resident daemon survived the sleep cycle.
- Ticket 94 idle sample: identity unchanged, RSS 11600→11600 KiB,
  CPU 0.0%; `pss_kib: permission-denied` as non-root, so `resource_sample`
  is `incomplete` and the idle baseline is `inconclusive-because-metrics-
  unavailable` per the sampler's own contract. Zero fprintd journal lines in
  the window support the no-claims premise; no power/wakeup verdict is
  claimed.
- Ticket 89 samples: 2 genuine labeled claims (pre-sleep, post-resume),
  both `verify-no-match (done)`, both `journal-and-milan-consistent`:
  first-touch success 0/2, first-decision miss 1/1 per decision denominator.
  This is an observed miss rate at n=2, not a population FRR estimate.
- Ticket 93 timing: cold-start 431.680ms; TTL-expired recovery 427.478ms.
  No in-TTL reuse intervals exist in this run (post-resume claim began
  17:44:09, after the ~17:41:52 park expiry), so the earlier warm-path
  attribution could not be re-confirmed on this run; the saved journals from
  tickets 87/88 remain the only warm samples. Zero transport-error greps
  (`timed out|Invalid ACK|verify-unknown|failed to`) in the 421-line batch
  journal.
- Ticket 90 sleep scenario: park at 17:36:52 (line 196), desktop suspend
  boundary 17:40:15→17:40:59 with identical MainPID/start timestamp, claim
  17:44:09. Because the claim crossed the 300s TTL, the journal shows
  `unhealthy (expired), full re-handshake` (`reason=ttl-expired`) rather than
  a disposal-specific signature. Disposal therefore stays
  **inconclusive-because-claim-followed-TTL-expiry**: the run confirms clean
  full re-handshake and working post-sleep capture (no transport errors, scan
  completed, re-parked gen=4) but cannot separate suspend disposal from
  ordinary expiry. The software-side idle-dispatch bypass defect stands
  unchanged; this run neither fixes nor falsifies it.

## Deviations during the run

- The operator's `sudo -v` triggered PAM fingerprint authentication before
  the batch start; Ctrl-C + password completed it. Pre-restart, outside the
  measured windows; recorded here rather than hidden.
- `journalctl --since` rejected `date --iso-8601=ns`'s comma nanoseconds
  (`Failed to parse timestamp`), leaving empty journals. Repaired live for
  idle, pre-sleep and post-resume by converting the first comma to a period
  (`${var/,/.}`); all three evidence files are complete. The checklist's
  three `journalctl` lines are fixed in this commit.
- Cleanup ran only via the operator's later interactive sudo (fingerprint
  prompt, then password); the scripted `sudo -n` correctly refused and
  warned. Ticket 91's contract held: the failure was explicit, evidence
  intact, and no hidden auth occurred inside measured windows.
- Wrong-finger sample skipped by the operator; no rejection data collected.

## Conclusions

- Ticket 89: tool confirmed on real evidence (2/2 samples fully attributed);
  accuracy conclusion deliberately not drawn at n=2. Single next experiment:
  a larger labeled set (≥20 genuine, ≥10 wrong) using the same claim block.
- Ticket 90: unchanged — disposal invariant untested on hardware this run;
  the recorded experiment remains valid for a later run if the claim is
  issued inside the TTL (sleep within 5 minutes of the park).
- Ticket 93: cold/expiry envelopes reproduce; warm attribution remains based
  on the 87/88 samples; no tuning is proposed.
- Ticket 94: sampler works; idle baseline inconclusive-because-PSS-denied.
- Ticket 91: cleanup failure surfaced explicitly; no extra PAM prompts inside
  any measured claim window.
- Ticket 92: unchanged; CI does not run hardware.

Single next experiment for the repo: the ≥20-sample labeled reliability set
above. No driver, threshold or service change is proposed by this ticket.
