# 24 — Remove per-frame debug file dumps from capture hot path

**What to build:** Delete the unconditional per-frame disk writes in
`goodix5e0a_on_read_img` (`libfprint-driver/goodix5e0a.c:382-387`: two
`g_file_set_contents` of the full frame to `/dev/shm/live_frame.raw` and
`/tmp/live_frame.raw` plus the `fp_info` saved-line), keeping the `declen`
`g_message` observability. One variable only: the base-class one-shot dump
(`goodix5xx.c:354-358`, `static frame_saved` gate) stays for a separate run.

**Blocked by:** None (hardware verify slot; implement + rebuild + redeploy).

**Status:** ready-for-agent

## Settled facts (do not re-litigate)
1. Both dump sites are pure side effects: `g_file_set_contents` reads `data`
   read-only (`NULL` error arg, fire-and-forget); no scan/match logic consumes
   the files. Removal cannot change minutiae or scores by construction.
2. Ticket 08 prescribed this exact cleanup ("per-frame `g_message` logging ...
   until acceptance, then remove the log line in the same ticket"); acceptance
   happened (Runs 14–18, tickets 17–18 verified). The removal never happened.
3. Upstream will not take unconditional `/tmp` writes in a driver (same class
   as the `fp-image.c` debug-spam hunks already flagged for the patch split).

## Proposed diff (driver only; patch regenerated from base after)
```diff
--- a/libfprint-driver/goodix5e0a.c
+++ b/libfprint-driver/goodix5e0a.c
@@ -382,6 +382,3 @@ goodix5e0a_on_read_img: drop per-frame file dumps
   if (data && len > 0)
     {
-      g_file_set_contents ("/dev/shm/live_frame.raw", (const gchar *) data, len, NULL);
-      g_file_set_contents ("/tmp/live_frame.raw", (const gchar *) data, len, NULL);
-      fp_info ("5e0a saved /dev/shm/live_frame.raw (%u bytes)", len);
     }
```
(If the block empties, drop the `if` too. No other lines touched.)

## Predicted journal signatures
- Confirm branch: `saved /dev/shm/live_frame.raw` lines vanish;
  `5e0a frame stats:` (active/min/max/range/declen), `get_minutiae` counts,
  `bz3 match` scores, and `verify-match (done)` are byte-identical in
  behavior to the pre-change build across the standard 2-verify run.
- Falsify branch: any change in frame stats, minutiae counts, or match
  outcomes vs the pre-change build → the dumps were NOT inert → revert
  immediately and report; do not pile further tweaks on.

## Rollback / packaging notes
- After the driver edit, regenerate the unified patch from the base tree and
  re-sync all deployed copies (SHA parity per ticket 19 §5). Until then, F25
  patch-sync and the pinned-SHA test will fail — expected, not a regression.
- Keep base-class one-shot dump (`goodix5xx.c:354-358`) untouched in this run.

## Acceptance (hardware verify protocol, no exceptions)
Phase 1 hands-off 60s + Phase 2 press-hold 60s with pasted client lines and
`journalctl -u fprintd` grep output per AGENTS.md; conclude only
confirmed / falsified / inconclusive-because-[flaw] + single next experiment.
