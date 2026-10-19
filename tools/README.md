# Tools

Helper scripts for extracting the hardware sensor key and testing the driver.

- `extract_psk_whitebox.py`: Preferred Linux-only recovery. Finds the whitebox
  record from the DPAPI structure length and requires a matching sensor SHA-256
  before saving a private key file. Requires Python 3.10+, pyusb and either
  python-cryptography or OpenSSL. No sensor provisioning or persistent writes.
- `dump_dpapi_blob.py`: Reads the locked key file from the sensor over USB in Linux.
- `decrypt_psk.ps1`: Unlocks the key file in Windows and writes `goodix-5e0a.psk`.
- `test-hardware.sh`: Builds and runs the current driver, or the explicit
  Jet-Soup capture candidate, with private enrollments and automatic restoration.
  See [hardware test instructions](../docs/HARDWARE_TEST.md).

Start with [key recovery](../docs/psk-extraction.md) on both dual-boot and
Linux-only machines. Key extraction and fingerprint matching are separate checks.
