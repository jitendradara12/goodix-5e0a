# 94: Measure resident-daemon resource cost

**What to build:** A small read-only sampler for fprintd's idle memory and CPU cost with `--no-timeout`.

**Blocked by:** None.
**Status:** closed
**Verdict:** confirmed, software-only sampler and fixture tests; live idle resource cost remains unmeasured.
**Owns:** Resource sampler and isolated fixtures; no driver or service changes.

- [x] Sample RSS/PSS and CPU-time deltas from process counters over a configurable interval. Report unavailable metrics and PID changes explicitly.
- [x] Test parsing, missing permissions and process exit with fixtures. Mock values validate the tool, not real resource cost.
- [x] Report wakeups only if measurable; do not infer power consumption or invent a stock-daemon baseline. Supply one optional command for the final batch.

**Evidence:** Confirm an idle baseline only with an unchanged PID and no claims in the interval; otherwise mark the sample inconclusive.
**Done:** Tool and offline tests pass. Live measurements can wait until the end; keep `--no-timeout` unchanged.

## Implementation, 2026-09-17

- `scripts/sample_fprintd_resources.py` uses Python stdlib and read-only `/proc` files. By default it queries `systemctl show fprintd.service --property=MainPID --value` at each endpoint, with a 5-second query timeout. It never starts a daemon, changes a service or contacts a fingerprint device.
- JSON includes UTC bounds, actual monotonic elapsed time, raw user/system CPU ticks, clock tick frequency, RSS/PSS endpoints in KiB and CPU deltas in seconds. CPU percentage uses one core as 100%, includes process threads and excludes children. Memory endpoints are not peaks or averages.
- PID and starttime changes suppress CPU deltas. Each endpoint brackets memory/cmdline reads with stat identity checks; exits, zombies, missing fields and permission denial are explicit. Missing PSS is not replaced with RSS. `--pid` selects a fixed process instead of following systemd and does not authenticate it as fprintd.
- `no_timeout_argument` records the observed `--no-timeout` or `-t` argument; it does not change configuration. Wakeups and power are explicitly not measured. There is no stock-daemon comparison.
- Exit 0 means complete resource counters, not a confirmed idle baseline. Exit 1 means incomplete counters; Ctrl-C emits the first sample with an interrupted verdict and exits 130. Missing initial identity returns immediately without sleeping.

## Software validation

```bash
python3 -m unittest tests.tier4_realworld.test_resource_sampler -v
python3 scripts/sample_fprintd_resources.py --help
```

21 tests passed in 0.045s. Fixtures cover stat command names containing spaces and parentheses, exact memory keys/units, CPU interval arithmetic, PID replacement/reuse, exit during and between snapshots, zombies, denied stat/memory/cmdline, missing and malformed PSS, read-only bounded systemd lookup, bad CLI inputs and interruption. CLI tests mock both sampling and sleep. These numbers validate the tool, not live resource cost. Help and whitespace checks passed. No master runner, driver, service or other ticket was edited by this work. No live measurement or hardware operation was run.

## Optional batch95 command

From the repository root, with `$out` already set to the batch evidence directory:

```bash
python3 scripts/sample_fprintd_resources.py --interval 20 > "$out/idle-resources.json"
```

Run this separately from all claim, authentication, touch and suspend phases. Leave the existing `--no-timeout` service unchanged. If PSS access is denied, retain the incomplete JSON rather than adding privilege automatically. The sampler does not collect journals or detect claims. Retain independent, full-interval journal/claim evidence with the JSON; an empty ordinary journal alone does not prove no claims were made.

### Predicted signatures for the later run

- Confirm an idle resource baseline only when `identity` is `unchanged`, `resource_sample` is `complete`, both argument observations are true, and independent evidence establishes no existing or new claims and no suspend throughout the timestamp bounds. A sufficiently complete claim trace must have no claim/activation/verification/enrollment activity in that interval and no daemon stop/start. Review the numbers as observations, with no invented cost threshold.
- Falsify the no-claims premise if the interval contains a Claim, activation, verify or enrollment event. Do not label those counters idle. A service exit/start, `pid-changed` or `starttime-changed-pid-reused` falsifies the stable-process premise, not a resource-cost budget.
- Inconclusive-because-[flaw] for unavailable metrics, interrupted sampling, identity loss, missing flag evidence, suspend or missing claim coverage. The JSON always leaves the idle verdict inconclusive because `/proc` does not establish absence of claims. Do not promote exit 0 to hardware verification.

The hands-off/hold hardware protocol is not relevant to these offline parser tests; no hardware run occurred. Single next experiment: the optional isolated 20-second idle sample during batch95, with full-interval claim evidence.
