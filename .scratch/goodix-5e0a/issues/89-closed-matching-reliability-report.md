# 89: Measure first-touch matching reliability

**What to build:** A small report that separates genuine-finger misses, wrong-finger rejections and aborted claims using labeled results and journals. Existing unlabeled no-matches are not proof of false rejection.

**Blocked by:** None.
**Status:** closed — confirmed software; hardware accuracy pending ticket 95
**Owns:** New reliability-report tool and its fixtures; no matcher or enrollment changes.

- [x] Report attempt counts and first-touch success by labeled finger/contact; exclude unknown labels and cancellations from accuracy rates.
- [x] Test match, no-match, retry and missing-data cases offline. Do not retain raw biometric images/templates.
- [x] Supply an optional collection mode for the final batch; do not wait for user data to finish implementation.

**Evidence:** Confirm with labeled outcomes matching `Milan verify`/`report_verify_status`; falsify if duplicate statuses inflate attempts or unlabeled misses count as genuine rejects.
**Done:** Tool and tests pass. Real-world accuracy remains pending the final batch; thresholds stay unchanged.

## Software result, 2026-09-17

Confirmed for software. Added `scripts/matching_reliability.py` and isolated synthetic fixtures/tests in `tests/tier1_feature/test_f89_matching_reliability.py`. No driver, matcher, enrollment, master runner, or other ticket edits. No hardware operations, privileged commands, captures, staging, or commits.

Checks passed:

- `python3 -m unittest discover -s tests/tier1_feature -p test_f89_matching_reliability.py -v`: 12 tests passed, no skips.
- `python3 scripts/matching_reliability.py --help`: passed.
- Scoped `git diff --check`: passed. New files also exercised through imports and subprocess CLI tests.

One unique claim ID counts as one attempt. Repeated statuses and identical duplicate records do not inflate attempts; conflicting duplicate IDs fail validation. Report groups use operator-provided label, presented-finger token, and contact token. Unknown metadata, cancellations, errors, incomplete evidence, and conflicting sources are excluded from rates. Retry-first completed claims lower first-touch success but are not genuine misses. Decision-only rates exclude retries. Zero denominators emit JSON null, never a success percentage.

## CLI handoff for ticket 95

After the user-only final batch saves one isolated claim's client output and optional plain-text journal excerpt:

```sh
python3 scripts/matching_reliability.py collect \
  --samples "$out/matching-samples.jsonl" \
  --id "$claim_id" --label "$label" --finger "$presented_finger_label" \
  --contact "$contact_label" \
  --results "$out/$claim_id.txt" --journal "$out/$claim_id-journal.txt"
python3 scripts/matching_reliability.py report "$out/matching-samples.jsonl" \
  > "$out/matching-report.json"
```

Use `genuine`, `wrong`, or `unknown` for `$label`. Genuine means known to match the selected enrollment; wrong means a known different finger. Tokens must be anonymous ASCII letters/digits, dot, underscore, or hyphen, up to 80 characters. Use a fresh claim ID. Supply `--cancelled` for timeout/interruption, even if a partial result exists. Both evidence options are optional; a record without evidence is incomplete. Collection only imports saved files and retains normalized statuses, never raw logs, scores, images, or templates. Input evidence is not modified.

Confirm branch: labeled `Milan verify: match=1/0` agrees with `report_verify_status: result verify-match/verify-no-match`, and optional client `Verify result` agrees with the journal. Duplicate lines leave attempt and rate denominators unchanged.

Falsify branch: duplicates inflate attempts, unknown no-matches become genuine misses, or contradictory status/Milan results enter rates. Fixtures cover each branch. Missing/interrupted samples are inconclusive, not biometric failures.

Limitations: first-touch is the first reported status of a complete isolated claim, not a measured physical contact. The caller must supply correctly labeled, non-overlapping, complete claim windows; the tool cannot detect identical claims imported under different IDs, infer cancellations from arbitrary prose, or recover omitted first results. A status-only result is reported without claiming Milan corroboration. Repeated identical retries are collapsed, so this tool does not count physical retry touches. Collection assumes one writer. Hardware accuracy is unverified; no thresholds changed.

## Review follow-up

Client match/no-match now requires the explicit `(done)` marker. Missing or truncated completion markers produce an incomplete record and exclude the claim, including when another source has a terminal result. Journal `report_verify_status` match/no-match is terminal in this driver's format, so it does not require the client marker.

After collapsing adjacent identical duplicates, any terminal decision followed by another status excludes the sample as mixed claims. Contradictory Milan decisions also exclude it. Identical adjacent terminal lines remain duplicates, not additional attempts; separate same-result claims without boundaries cannot be distinguished and still require isolated input windows. Existing normalized records imported by the earlier parser must be recollected from saved text to check completion markers.

`python3 -m unittest discover -s tests/tier1_feature -p test_f89_matching_reliability.py -v`: 14 tests passed, no skips, including incomplete client lines, conflicting terminal decisions, terminal-then-retry, and duplicate terminal lines through public assess/report functions. No dependencies added. The standalone `pytest` command was unavailable; this suite uses stdlib unittest.

Single next experiment: run the combined user-only ticket-95 batch with labeled claims, using the repository's hands-off/steady-hold protocol where relevant. No per-ticket hardware gate.
