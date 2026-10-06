#!/usr/bin/env python3
"""Goodix 27c6:5e0a DPAPI Blob & MCU Hash Dumper (Linux).

This read-only utility reads:
  1. Slot 0xbb020001: The SHA-256 hash of the MCU operational PSK (saved to mcu_hash.txt)
  2. Slot 0xbb010002: The Windows DPAPI-sealed PSK blob (saved to dpapi_blob.bin)

Neither read modifies device state or hardware configuration.

Prerequisites:
  sudo systemctl stop fprintd
  Ensure USB access permissions (run with sudo or add udev rules)
  Python module 'pyusb' (sudo apt install python3-usb / pip install pyusb)

Output files:
  dpapi_blob.bin - Encrypted DPAPI payload to be decrypted in Windows.
  mcu_hash.txt   - Expected SHA-256 hash for verification.
"""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "legacy-experiments"))
sys.path.insert(0, str(repo_root / "legacy-experiments" / "vendor"))

try:
    import usb.core
except ImportError:
    print("ERROR: python package 'pyusb' is required.", file=sys.stderr)
    print("Install it with: sudo apt install python3-usb (Debian/Ubuntu) or pip install pyusb", file=sys.stderr)
    sys.exit(1)

try:
    import goodix_protocol
    sys.modules["protocol"] = goodix_protocol
    import goodix
except ImportError as e:
    print(f"ERROR: Failed to import Goodix protocol helpers: {e}", file=sys.stderr)
    sys.exit(1)


def main():
    print("=" * 65)
    print("Goodix 27c6:5e0a DPAPI Blob & Key Hash Extractor")
    print("=" * 65)

    try:
        device = goodix.Device(0x5e0a, goodix_protocol.USBProtocol)
    except Exception as e:
        print(f"ERROR: Cannot open Goodix 27c6:5e0a USB device: {e}")
        print("Make sure 'fprintd' is stopped (sudo systemctl stop fprintd)")
        print("and run this script as root (sudo python3 tools/dump_dpapi_blob.py).")
        sys.exit(1)

    try:
        device.nop()
        print("[+] Device communication verified (NOP OK)")
    except Exception as e:
        print(f"[-] NOP command failed: {e}")
        sys.exit(1)

    try:
        fw_data = device.firmware_version()
        fw_ver = fw_data.decode("ascii", errors="ignore").rstrip("\x00")
        print(f"[+] Firmware version: {fw_ver}")
    except Exception as e:
        print(f"[-] Could not read firmware version: {e}")

    # 1. Read slot 0xbb020001 (MCU SHA-256 hash)
    mcu_hash = None
    try:
        reply = device.preset_psk_read(0xbb020001, 32, 0)
        if reply and reply[0]:
            mcu_hash = reply[2]
            hash_hex = mcu_hash.hex()
            print(f"[+] Slot 0xbb020001 (MCU Key Hash): {hash_hex}")
            Path("mcu_hash.txt").write_text(hash_hex + "\n")
            print("    -> Saved to mcu_hash.txt")
        else:
            print("[-] MCU returned error reading slot 0xbb020001")
    except Exception as e:
        print(f"[-] Exception reading slot 0xbb020001: {e}")

    # 2. Read slot 0xbb010002 (Windows DPAPI sealed blob)
    sealed_blob = None
    try:
        reply = device.preset_psk_read(0xbb010002, 256, 0)
        if reply and reply[0]:
            sealed_blob = reply[2]
            print(f"[+] Slot 0xbb010002 (DPAPI Sealed Blob): {len(sealed_blob)} bytes read")
            Path("dpapi_blob.bin").write_bytes(sealed_blob)
            print("    -> Saved to dpapi_blob.bin")
        else:
            print("[-] MCU returned error reading slot 0xbb010002 (slot empty or unprovisioned)")
    except Exception as e:
        print(f"[-] Exception reading slot 0xbb010002: {e}")

    print("\n" + "=" * 65)
    if sealed_blob:
        print("Extraction complete! Next steps:")
        print("  1. Copy 'dpapi_blob.bin' (and optionally 'mcu_hash.txt') to your Windows drive.")
        print("  2. In Windows (PowerShell as Administrator), run:")
        print("     powershell -ExecutionPolicy Bypass -File .\\tools\\decrypt_psk.ps1")
        print("  3. It will decrypt the key and create 'goodix-5e0a.psk'.")
        print("  4. Copy 'goodix-5e0a.psk' back to Linux at /etc/libfprint/goodix-5e0a.psk.")
    else:
        print("Extraction failed: could not retrieve the sealed DPAPI blob from MCU.")
    print("=" * 65)


if __name__ == "__main__":
    main()
