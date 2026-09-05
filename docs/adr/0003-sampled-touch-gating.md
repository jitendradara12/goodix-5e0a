# Sampled touch gating, not a blocking wait

The finger-down command is sampled: an idle reply schedules a short re-sample, while channel energy proving real touch reports finger presence and advances to capture immediately.

## Considered Options

- **Infinite blocking wait on finger-down**: rejected — the MCU answers in milliseconds even on empty air, so a blocking wait either returns instantly on stale data or hangs the state machine on the first command collision.
- **Status-byte gating**: rejected — the status byte reads the same value for idle air and poor contact on hardware; only channel energy separates them.
- **Zero-polling pure interrupt model**: rejected — no interrupt exists on this transport; the re-sample timer is the polling floor, kept short and silent.

## Consequences

Cancellation must disarm the re-sample timer and the scan state machine together, and verification latency work builds on prompt capture rather than on removing a wait that was never there.
