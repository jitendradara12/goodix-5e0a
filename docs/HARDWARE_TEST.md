# Hardware Verification Guide

The repository includes an isolated hardware test runner (`tools/test-hardware.sh`) to verify driver functionality on live hardware.

It builds a temporary driver instance, isolates fprintd storage, and runs a protocol-compliant test session using separate enrollment storage. It checks the original storage after cleanup.

## Running the Test

For a PR, check out its latest branch first. Run from the repository root:

```bash
bash tools/test-hardware.sh
```

The script builds the driver and requests `sudo` for the temporary test session.
Capture settings are selected automatically from OTP; no extra flag is needed.
Fingerprint login is temporarily unavailable during the test.

## Test Protocol

1. **Phase 1: Hands off (20 seconds)**
   Do not touch the sensor. Verifies no phantom touches or false trigger loops.
2. **Phase 2: Press and hold steady (20 seconds)**
   Hold one finger steadily on the sensor. Verifies a single advance and contact release guarding.
3. **Phase 3: Enrollment**
   Complete the 12-touch enrollment with that same finger, lifting between touches.
4. **Phase 4: Verification**
   - Touch the enrolled finger 5 times (expected: 5 matches).
   - Touch an unenrolled finger 5 times (expected: 5 rejections).

## Results & Cleanup

- Attach the ZIP path printed at the end to the PR, including a failed or interrupted run. It contains numerical results, not keys, images or templates. If no ZIP was created, paste the error.
- Stop after one run so the result can be reviewed before another test.
- Original fprintd service and fingerprint storage are restored automatically upon exit or Ctrl-C.
- If interrupted abruptly, restore system state manually:
  ```bash
  bash tools/test-hardware.sh --restore
  ```
