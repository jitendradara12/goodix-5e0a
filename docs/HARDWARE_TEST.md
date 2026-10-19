# Hardware Verification Guide

The repository includes an isolated hardware test runner (`tools/test-hardware.sh`) to verify driver functionality on live hardware.

It builds a temporary driver instance, isolates fprintd storage, and runs a protocol-compliant test session without altering existing fingerprints or system files.

## Running the Test

Run the test runner from the repository root:

```bash
bash tools/test-hardware.sh
```

The script builds the driver and requests `sudo` for the temporary test session.

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

- Logs and report archives are saved to `/var/tmp/goodix-5e0a-reports/`.
- Original fprintd service and fingerprint storage are restored automatically upon exit or Ctrl-C.
- If interrupted abruptly, restore system state manually:
  ```bash
  bash tools/test-hardware.sh --restore
  ```
