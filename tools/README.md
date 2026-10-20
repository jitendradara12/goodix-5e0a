# Tools

Helper scripts for sensor PSK extraction and driver hardware testing.

- `extract_psk_whitebox.py`: Recommended Linux-only PSK recovery tool. Recovers and validates the sensor key directly over USB without Windows. See [docs/psk-extraction.md](../docs/psk-extraction.md).
- `dump_dpapi_blob.py`: Reads the Windows DPAPI blob from the sensor over USB in Linux (fallback method).
- `decrypt_psk.ps1`: Decrypts the DPAPI blob in Windows and generates `goodix-5e0a.psk`.
- `test-hardware.sh`: Convenience wrapper around `hardware_session.py` to run isolated driver hardware tests with separate enrollment storage and automatic OTP calibration. See [docs/HARDWARE_TEST.md](../docs/HARDWARE_TEST.md).
- `hardware_session.py`: Isolated hardware test runner with temporary fprintd storage drop-ins and automatic restoration.

`experiments/jet-soup-capture.patch` preserves the original wire comparison.
The runner no longer applies it; the driver now selects that profile itself.
