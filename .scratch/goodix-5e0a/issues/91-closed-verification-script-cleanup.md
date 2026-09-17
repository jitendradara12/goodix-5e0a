# 91: Make verification cleanup predictable

**What to build:** Verification scripts that save evidence and exit cleanly without surprise fingerprint prompts during cleanup.

**Blocked by:** None.
**Status:** closed

**Verdict:** confirmed, software-only mocked validation; not hardware verified.
**Owns:** Existing verification scripts and isolated shell fixtures; not the master test runner.

- [x] Preserve the test's exit status and save journals on success, error and interruption.
- [x] Avoid interactive authentication in cleanup; if privilege expired, print an explicit cleanup command and warning. Do not claim debug settings were restored when they were not.
- [x] Mock sudo expiry, timeout, cancellation and successful cleanup. Keep setup authentication separate from measured claims.

**Evidence:** Confirm logs end at the measured claim and cleanup status is explicit; falsify on hidden cleanup failure, lost evidence or extra PAM prompts inside the test result.
**Done:** Mock checks pass; no hardware run required for implementation.

## Software verdict, 2026-09-17

Confirmed by 59 fully mocked runs. No deployed-driver verification, actual sudo,
fprintd claim, hardware access, suspend, native build, stage or commit performed.

Both existing scripts had the same cleanup defect. Ticket 87 registered its
trap after privileged setup and swallowed client failures, including the second
claim. Ticket 88 replaced failure statuses with 1. Both could prompt through
sudo during cleanup and captured an unbounded journal.

Changes in `scripts/verify-ticket87.sh` and `scripts/verify-ticket88.sh`:

- Install EXIT, INT, TERM and HUP handling before authentication. Use explicit
  setup `sudo -v`, then only `sudo -n` for privileged operations.
- Capture journals through a fixed end timestamp before cleanup. Successful
  setup resets the start boundary after restart, excluding setup authentication.
  Setup failures retain the earlier start boundary for diagnosis.
- Preserve original nonzero test/client status, including 124/137 timeouts and
  130/143/129 signals. Completed no-match remains a valid park probe. Evidence
  or cleanup failure changes an otherwise successful run to exit 1.
- Save partial journals, journal errors, cleanup diagnostics and separate exit
  fields in `status.txt`. Cleanup failure prints a warning and the manual
  `sudo systemctl unset-environment G_MESSAGES_DEBUG` command. Successful
  cleanup says only that the manager environment was unset, not that the
  running daemon's debug state was restored.
- Use unique private evidence directories so same-second reruns cannot overwrite
  earlier evidence.

## Exact offline checks

Run from repository root:

```bash
bash -n scripts/verify-ticket87.sh scripts/verify-ticket88.sh
python3 tests/fixtures/verify_cleanup/check.py
git diff --check -- scripts/verify-ticket87.sh scripts/verify-ticket88.sh
```

All exit 0. The fixture runs ticket 87 and both ticket 88 gap options, 90 and
310 seconds. PATH contains mocked sudo/systemctl/timeout/journalctl/sleep/client
commands and only allowlisted local text/filesystem tools. No inherited PATH
fallback can invoke a real privileged or hardware command. Python stdlib only.

Cases cover match, completed no-match, malformed completion, first/second timeout,
forced timeout kill status, arbitrary client error, expired cleanup credentials,
partial failed journal capture, combined cleanup/journal/client failure, direct
INT/TERM/HUP signals, setup authentication/set/restart failure and absent service
flag. Checks require retained evidence, exact exit status, bounded journal capture
before cleanup, no sudo between the first claim and journal capture, and explicit
warning/manual command on cleanup failure.

Confirm signature: `status.txt` retains `test_exit`, records `journal_exit` and
`cleanup_exit`, and the bounded journal precedes noninteractive cleanup. Falsify:
interactive sudo outside setup, missing/overwritten evidence, lost original
failure status, or a cleanup-success message after failed unset.

## Limitations and later CLI

Mock signals target the script process, not a real terminal process group. Mock
sleep and timeout do not establish real timing or child-process teardown. SIGKILL,
power loss, disk failure, journal permission loss/rotation and wall-clock jumps
cannot be repaired by an EXIT trap. Existing manager environment is unset, not
snapshotted/restored; the running daemon is deliberately not restarted in cleanup.
No master runner, driver, native build or other ticket was edited.

Offline batch integration command:

```bash
python3 tests/fixtures/verify_cleanup/check.py
```

User-only probe entry points, for later testing, unchanged apart from cleanup:

```bash
bash scripts/verify-ticket87.sh
bash scripts/verify-ticket88.sh 90
bash scripts/verify-ticket88.sh 310
```

Do not batch these hardware commands in unattended agent runs. Exit 0 means the
script and cleanup completed, not that parked reuse or hardware reliability was
verified. The single next experiment is a later user-run probe with journal
review; ticket 91 needs no hardware run to close its software scope.
