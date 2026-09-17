# Ticket 93: pre-touch activation timing

Software verdict: confirmed. The offline tool and eleven synthetic tests pass. The saved warm samples consistently put almost all of the reuse-to-finger-wait-send interval inside chip-enable and D6 command envelopes. Their internal transport/device timing remains unmeasured. No new hardware run, driver change, protocol change, or timing change was made. This is not a hardware-verified verdict.

## Evidence and method

Tool: `scripts/analyze_activation_timing.py`. It reads saved `journalctl -o short-precise` text and emits JSON with source paths, line numbers, separate candidate/reuse markers, command envelopes, and action-to-first-finger-wait-send summaries. It uses only Python's standard library.

All inputs below are `/home/sastauser/<directory>/journal.txt`, from September 17, 2026. Each range starts at an explicit `start verification device` and ends at the first `Running command: 0x32`. Later touch responses and retries are excluded.

| Directory | Lines | Path | Start to 0x32 send marker, ms |
| --- | --- | --- | ---: |
| goodix-ticket88-20260917-105801 | 51–153 | cold-start | 429.325 |
| goodix-ticket88-20260917-110002 | 51–153 | cold-start | 429.916 |
| goodix-ticket88-20260917-110051 | 50–152 | cold-start | 429.046 |
| goodix-ticket88-20260917-110051 | 249–280 | parked TLS reused | 28.176 |
| goodix-ticket88-20260917-110502 | 50–152 | cold-start | 430.004 |
| goodix-ticket88-20260917-110502 | 220–251 | parked TLS reused | 27.771 |
| goodix-ticket85-expiry-20260917-112923 | 449–551 | cold-start | 431.343 |
| goodix-ticket85-expiry-20260917-112950 | 50–152 | cold-start | 431.214 |
| goodix-ticket85-expiry-20260917-113015 | 50–152 | cold-start | 431.139 |
| goodix-ticket85-expiry-20260917-113015 | 249–353 | TTL-expired full activation | 426.769 |

The beginning of the 112923 journal contains activation traffic without an explicit action start. The tool excludes it rather than guessing its boundary. Earlier experiment files can contain interrupted user workflows; a complete pre-touch interval does not establish successful verification or completion of that experiment's hands-off/holding protocol.

Seven cold-start intervals span 429.046 to 431.343 ms, median 430.004 ms. There is one TTL-expired sample. There are only two actual parked-reuse samples, both after about 90.2 seconds parked, in different daemon processes. There are no measured warm-config/new-handshake samples in these files.

### What the timestamps mean

- `candidate fresh, health-checking` only says the parked session is eligible for a health check. It does not prove reuse.
- `5e0a TLS session reused` follows a successful health-check callback. It does not imply the scan's finger-wait command has been sent.
- `Running command: 0x32` is the finger-wait command-send marker. In `libfprint-driver/goodix.c`, logging precedes packet encoding and `goodix_send_pack`. It is not USB transfer completion, sensor readiness, a physical touch timestamp, or even proof that the write succeeded.
- `Completed command: 0x00` is misleading for nonzero commands: `goodix_receive_done` calls `goodix_reset_state` before printing the opcode. The tool pairs the first completion with the preceding serial command in the same host/PID/action, not with the printed completion opcode. TLS relay read completions following D0 are not additional D0 completion time.
- A command envelope includes encoding, host scheduling, transport and firmware response handling. These logs do not separate those costs. No USB-ready or device-execution estimate is claimed.

Source timestamps have six decimal places. Tables preserve their 0.001 ms display resolution so the arithmetic can be reproduced. That is not an accuracy claim. Quantization alone allows approximately ±0.001 ms per timestamp difference if timestamps share a stable clock; logging delay, batching, and wall-clock accuracy have no measured bound here. Ranges below are observed min/max margins, not confidence intervals. The parser rejects coarse timestamps and backward timestamps rather than inventing submillisecond precision or correcting clock jumps.

## Warm breakdown

| Journal suffix | Candidate to actual reuse | Actual reuse to 0x32 send | Candidate to 0x32 send |
| --- | ---: | ---: | ---: |
| 110051 | 0.547 ms | 27.616 ms | 28.163 ms |
| 110502 | 0.573 ms | 27.182 ms | 27.755 ms |

Actual reuse to send is therefore about 27.4 ms, with observed variation of roughly ±0.22 ms about the two-sample midpoint. Candidate-to-reuse belongs outside that interval.

| Serial operation | Send to completion, observed range, ms | Completion to next command, ms |
| --- | ---: | ---: |
| 0xae candidate health check, before reuse | 0.500–0.520 | 0.010 |
| 0x96 chip enable, after reuse | 13.189–13.290 | 0.014–0.054 |
| 0xae scan MCU-state query | 0.598–0.656 | 0.006–0.009 |
| 0xd6 session command | 13.300–13.653 | 0.009–0.010 |

For 110051, reuse-to-send is 0.005 ms to chip-enable launch + 13.290 ms chip-enable envelope + 0.054 ms gap + 0.598 ms query envelope + 0.006 ms gap + 13.653 ms D6 envelope + 0.010 ms gap = 27.616 ms.

For 110502, the same partition is 0.005 + 13.189 + 0.014 + 0.656 + 0.009 + 13.300 + 0.009 = 27.182 ms.

Chip enable and D6 account for 97.45–97.56% of the interval. All time outside the three post-reuse command envelopes totals only 0.037–0.075 ms. The roughly 13 ms waits mostly precede their logged ACKs: chip-enable send-to-ACK is 13.176–13.257 ms, D6 send-to-ACK is 13.146–13.345 ms. D6 then has another 0.154–0.308 ms to its completion marker. This identifies the command boundaries, not why the device or transport takes that time.

## Cold comparison

Seven cold-start samples give the following estimates. The middle column is a command envelope when a completion is logged. The last column includes any later work before the next command and must not be read as command duration.

| Command / work | Send to first completion, median and observed range, ms | Send to next command, observed range, ms |
| --- | ---: | ---: |
| 0x00 NOP flush | not logged | 200.164–200.421 |
| 0xa8 firmware query | 1.097, 1.031–1.185 | 1.078–1.219 |
| 0xe4 PSK-slot read | 28.377, 28.154–28.519 | 30.133–33.125 |
| 0xd0 TLS request | 11.950, 11.868–12.092 | 157.598–158.896 |
| 0xd4 TLS-established notification | 16.399, 16.298–16.535 | 16.310–16.588 |
| 0x90 MCU configuration | 7.287, 7.127–7.579 | 7.140–7.625 |
| 0x96 chip enable | 0.749, 0.661–0.896 | 0.681–0.920 |
| 0xae scan query | 0.707, 0.601–0.813 | 0.608–0.826 |
| 0xd6 session command | 13.714, 13.333–13.807 | 13.354–13.842 |

NOP has no success-completion marker. Its 200 ms send-to-next-command window is consistent with `GOODIX_NOP_TIMEOUT = 200` and the tolerant timeout callback, but no exact timeout firing timestamp is logged. Do not turn that inference into a measured NOP completion.

D0 completion to D4 launch spans 145.717–146.953 ms of TLS handshake work, not an unexplained idle gap or a 158 ms D0 command. The 110502 journal, lines 81–117, logs handshake states, relay flights and acceptance inside it. PSK completion to D0 launch adds 1.635–4.862 ms, including TLS-server startup. The TTL-expired sample follows the same command sequence and reaches 0x32 in 426.769 ms.

Comparing the two parked-reuse action intervals against the seven cold-start intervals gives an observed difference of 400.870–403.572 ms. This is a path comparison across samples, not a controlled causal estimate. The absolute upper limit from removing the entire remaining warm pre-touch interval would be just 27.771–28.176 ms in these samples, and removing only post-reuse work cannot save more than 27.182–27.616 ms. Neither is a safe achievable optimization.

## Recommendation and next experiment

Do not change timing or command ordering for this gain. The existing parked path already avoids roughly 402 ms of cold activation. Eliminating the post-reuse scan query alone has less than 0.7 ms of measured command-envelope budget. The two larger operations establish chip and session state; these logs do not justify removing them. Cold chip-enable happens in under 0.9 ms while warm chip-enable takes about 13.2 ms, which is a useful observation but not evidence that shortening a timeout would help.

The single next experiment is to run this analyzer on ticket 95's combined batch journal, without a separate hardware checkpoint. Confirm the saved-data attribution if at least two complete actual-reuse actions repeat the 0x96 → 0xae → 0xd6 → 0x32 sequence and most of the reuse-to-send interval remains inside the chip-enable/D6 envelopes. Falsify the small-host-gap attribution if complete logs instead put most time outside those envelopes. If starts, completions or endpoints are missing, conclude inconclusive-because-missing-markers. If transport internals remain the question, recommend monotonic command/transfer instrumentation in a separate follow-up, not tuning based on these journal timestamps.

## Offline checks and handoff for ticket 95

Run from the repository root. Neither command below touches hardware or invokes privileged operations.

```sh
python3 -m unittest tests.tier1_feature.test_f93_activation_timing -v
python3 scripts/analyze_activation_timing.py "$EVIDENCE_DIR/journal.txt" > "$EVIDENCE_DIR/activation-timing.json"
```

For saved-data reproduction:

```sh
python3 scripts/analyze_activation_timing.py /home/sastauser/goodix-ticket88-20260917-*/journal.txt /home/sastauser/goodix-ticket85-expiry-20260917-*/journal.txt > /tmp/opencode/ticket93-timing.json
```

Eleven tests passed. They cover actual reuse versus candidate-only and config reuse, cold fallback, missing completion, TLS-read completion isolation, first-send cutoff before touches/retries, PID/action/file isolation, empty input, coarse timestamps, backward clocks, midnight rollover, CLI JSON and missing-file errors. All seven saved journals parsed successfully, producing ten complete explicit-action intervals. The scope-specific suite was run; the shared master runner and driver suites were left to ticket 95 integration.

JSON `attempts[].status` describes endpoint coverage, not authentication success or hardware readiness. Missing endpoints remain `incomplete:*` and are excluded from `summary`; empty inputs produce no samples. No-sample and unknown-path outputs need an inconclusive interpretation by ticket 95, even though parsing exits successfully. Inputs must be short-precise text; other formats fail with an explanatory error. Output paths are chosen by shell redirection, and the tool does not alter its input files.

No files were staged or committed, as requested by the delegating session. The report is present in the shared working tree for integration.
