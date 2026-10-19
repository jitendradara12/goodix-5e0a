# 115: Linux-only PSK recovery and separate Jet-Soup capture candidate

**Status:** ready-for-hardware-verify

## Scope

Integrate Jet-Soup's Linux-only PSK recovery from issue #12, hardening record
discovery, Python compatibility, verification and output publication. Prefer
the Linux route in setup documentation while retaining the DPAPI fallback.
Keep their wire-only capture settings in an explicit temporary test candidate;
do not globally replace settings already working on the owner's/ptrip7's units.

Contributor source: https://github.com/jitendradara12/goodix-5e0a/issues/12#issuecomment-6263682686

## Software evidence

- Patch reviewed against `690cc75`; import failure reproduced with Python
  3.12, payload-only overread rejection reproduced, and forced-write failure
  shown to delete the previous key in the original contribution.
- Recovery now derives the candidate offset from bounded DPAPI parsing,
  reuses the existing whitebox decryptor and requires a same-sensor SHA-256.
- Output is published with mode 0600, atomic replacement/no-clobber behavior,
  no default key printing and cleanup on failure. Python vendor annotations
  are deferred to support the documented Python 3.10+ route.
- The temporary hardware runner reuses the earlier isolation/recovery design
  with the merged matching pipeline. Current settings are the default; the
  separate Jet-Soup patch changes only capture data and preserves both payload
  definitions. Normal driver sources and matching policy are unchanged.
- Software checks and CI results are recorded in the PR. No new deployed-driver
  hardware run has occurred; the reported upstream matching fix is not a new
  verification of this candidate.

## Single next experiment: maintainer regression

From this PR run `bash tools/test-hardware.sh --capture-settings current`.
Record hands off + timestamp for 20 seconds, then holding + timestamp for
20 seconds, latency and advances; finish 12-touch enrollment and five genuine
and five wrong-finger attempts. The runner isolates enrollments and restores
the original setup, saving an allowlisted numerical report.

**Confirm:** no hands-off result activity; the journal's `enrollment stage`
advance/client `enroll-stage-passed` occurs once during the steady hold, then
waits for release; all 12 stages complete; `Milan verify: match=1 pts=>0` for
genuine attempts and `match=0 pts=0` for wrong-finger attempts.

**Falsify:** spurious hands-off results/capture cycles, repeated hold advances,
valid fresh enrollment followed by genuine failures, or any wrong-finger match.

**Inconclusive-because-[flaw]:** setup/build error, failed isolation, old/mixed
enrollment, missing phases or interruption. Conclude only confirmed / falsified /
inconclusive-because-[flaw], with the single next experiment chosen from that report.

After maintainer confirmation, the next experiment is the same guided run on
Jet-Soup's unit with `--capture-settings jet-soup`. Its predicted signatures
are the same, with patch/library hashes and capture settings recorded. Only
that run can support a fix for their live matching problem. Failed genuine
matching with clean capture remains a failure of this combination, not proof
that vendor calibration is required. A successful owner run alone is insufficient.
