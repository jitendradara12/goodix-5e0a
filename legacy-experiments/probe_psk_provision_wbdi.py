#!/usr/bin/env python3
"""One-shot probe script: Goodix 5e0a PSK Verification, Provisioning, and Activation.

Based on reverse engineering of wbdi.dll (Geneva module GFUSB_GM168SEC_APP_10036):
  1. Tag 0xbb020001 is SHA256(operational_psk) stored in the MCU.
  2. Tag 0xbb010002 is the host-sealed DPAPI blob.
  3. Tag 0xbb010003 is the WhiteBox encrypted PSK (SecWhiteEncrypt).
  4. Command 0xe0 wire format:
       10B magic: 56 a5 bb 95 6b 7c 8d 9e 00 00
       TLV1 (0xbb010002): host sealed blob
       TLV2 (0xbb010003): 96B WhiteBox payload
       Chunked with 12B chunk header: total_len, chunk_len, chunk_offset.

Usage:
  # Diagnostic read (safe, read-only):
  PYTHONPATH=/home/sastauser/code/temp/goodix:legacy-experiments nix-shell -p python3Packages.pyusb python3Packages.cryptography openssl --run "python3 legacy-experiments/probe_psk_provision_wbdi.py"

  # Provision write (only if needed):
  PYTHONPATH=/home/sastauser/code/temp/goodix:legacy-experiments nix-shell -p python3Packages.pyusb python3Packages.cryptography openssl --run "python3 legacy-experiments/probe_psk_provision_wbdi.py --provision"
"""

import argparse
import hashlib
import struct
import sys
from pathlib import Path

# Repo imports
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "experiments"))
sys.path.insert(0, str(repo_root / "experiments" / "vendor"))

import goodix_protocol
sys.modules['protocol'] = goodix_protocol
import goodix
from goodix_whitebox import sec_white_encrypt, build_psk_write_payload, chunk_psk_write_payload

HOST_KEY = bytes.fromhex("d853ad1941b2dc5350c766cd726ef7a5df7d5fa39053bfac269ce752d7a8b2ab")
EXPECTED_MCU_HASH = hashlib.sha256(HOST_KEY).digest()


def main():
    parser = argparse.ArgumentParser(description="Probe Goodix 5e0a PSK state and wire provisioning.")
    parser.add_argument("--provision", action="store_true", help="Execute 0xe0 PSK provisioning write.")
    parser.add_argument("--reset-soft", action="store_true", help="Send Windows-style soft reset (CMD 0xa2, payload [0x02, 0x32]).")
    args = parser.parse_args()

    print("=" * 70)
    print("Goodix 5e0a PSK State & Provisioning Probe")
    print(f"Host Static PSK: {HOST_KEY.hex()}")
    print(f"Host SHA-256:    {EXPECTED_MCU_HASH.hex()}")
    print("=" * 70)

    try:
        device = goodix.Device(0x5e0a, goodix_protocol.USBProtocol)
    except Exception as e:
        print(f"ERROR: Failed to open USB device: {e}")
        print("Ensure fprintd is stopped (systemctl stop fprintd) and you have USB access permissions.")
        sys.exit(1)

    # 1. NOP
    try:
        device.nop()
        print("[1] NOP: SUCCESS")
    except Exception as e:
        print(f"[1] NOP failed: {e}")
        sys.exit(1)

    # 2. Firmware version
    fw_ver = "unknown"
    try:
        fw_data = device.firmware_version()
        fw_ver = fw_data.decode("ascii", errors="ignore").rstrip("\x00")
        print(f"[2] Firmware Version: {fw_ver}")
    except Exception as e:
        print(f"[2] Read FW version failed: {e}")

    # 3. Soft reset if requested
    if args.reset_soft:
        print("[*] Sending Windows-style MCU soft reset (CMD 0xa2, payload [0x02, 0x32])...")
        try:
            # Send 0xa2 with soft_reset_mcu=1, reset_sensor=0, sleep=50ms
            payload = bytes([0x02, 0x32])
            device.protocol.write(
                goodix.encode_message_pack(
                    goodix.encode_message_protocol(payload, 0xa2)))
            resp = device.protocol.read()
            print(f"[*] Soft reset response: {resp.hex() if resp else 'None'}")
        except Exception as e:
            print(f"[*] Soft reset error: {e}")

    # 4. Read slot 0xbb020001 (MCU SHA-256 hash slot)
    print("\n[3] Reading slot 0xbb020001 (MCU PSK SHA-256 Hash)...")
    mcu_hash = None
    try:
        reply = device.preset_psk_read(0xbb020001, 32, 0)
        if reply and reply[0]:
            mcu_hash = reply[2]
            print(f"    Raw MCU Hash read: {mcu_hash.hex()}")
            if mcu_hash == EXPECTED_MCU_HASH:
                print("    --> MATCH! The MCU holds our exact host PSK (d853ad...b2ab)!")
                print("    --> PROOF: The key is ALREADY provisioned in hardware memory.")
            else:
                print(f"    --> MISMATCH! Expected {EXPECTED_MCU_HASH.hex()}, got {mcu_hash.hex()}")
        else:
            print("    --> Read returned error from MCU")
    except Exception as e:
        print(f"    --> Exception reading 0xbb020001: {e}")

    # 5. Read slot 0xbb010002 (Host-sealed DPAPI blob)
    print("\n[4] Reading slot 0xbb010002 (Host Sealed Blob)...")
    sealed_blob = b""
    try:
        reply = device.preset_psk_read(0xbb010002, 128, 0)
        if reply and reply[0]:
            sealed_blob = reply[2]
            print(f"    Sealed blob length: {len(sealed_blob)} bytes")
            print(f"    Preview: {sealed_blob[:32].hex()}...")
        else:
            print("    Slot 0xbb010002 empty or rejected by MCU")
    except Exception as e:
        print(f"    Exception reading 0xbb010002: {e}")

    # 6. Provisioning if requested
    if args.provision:
        print("\n[5] Executing 0xe0 Wire Provisioning...")
        is_iap = ("IAP" in fw_ver or "TESTIAP" in fw_ver)
        print(f"    Firmware mode: {'IAP (writable)' if is_iap else 'APP (write-protected)'}")
        if not is_iap:
            print("    WARNING: MCU is in APP mode. Per wbdi.dll geneva.c (ProcessPsk),")
            print("    the MCU rejects 0xe0 in APP mode unless erased into IAP mode first.")

        full_payload = build_psk_write_payload(HOST_KEY, sealed_blob=b"")
        chunks = chunk_psk_write_payload(full_payload, chunk_size=256)
        print(f"    Prepared {len(full_payload)} bytes payload in {len(chunks)} chunk(s).")

        for idx, chunk in enumerate(chunks):
            print(f"    Sending chunk {idx + 1}/{len(chunks)} ({len(chunk)} wire bytes)...")
            try:
                # Direct protocol write of CMD 0xe0
                pkt = goodix.encode_message_pack(
                    goodix.encode_message_protocol(chunk, goodix.COMMAND_PRESET_PSK_WRITE_R))
                device.protocol.write(pkt)

                # Wait for ACK
                ack_raw = device.protocol.read()
                ack_dec = goodix.decode_message_pack(ack_raw)
                print(f"    ACK raw: {ack_raw.hex()}")

                # Wait for reply
                reply_raw = device.protocol.read()
                print(f"    Reply raw: {reply_raw.hex() if reply_raw else 'None'}")
            except Exception as e:
                print(f"    Chunk {idx} send failed: {e}")
                break

    print("\n" + "=" * 70)
    print("PROBE SUMMARY:")
    if mcu_hash == EXPECTED_MCU_HASH:
        print("  - Hardware Key State: PROVISIONED & VERIFIED (MCU holds host key).")
        print("  - Key Mismatch: NONE.")
        print("  - Handshake failures on cold boot are caused by activation lifecycle")
        print("    (e.g. CMD 0xa2 sensor reset), NOT by missing or corrupt PSK.")
    elif mcu_hash:
        print("  - Hardware Key State: UNEXPECTED KEY")
        print(f"    MCU has hash: {mcu_hash.hex()}")
    else:
        print("  - Hardware Key State: UNREADABLE")
    print("=" * 70)


if __name__ == "__main__":
    main()
