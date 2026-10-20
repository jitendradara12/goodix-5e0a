#!/usr/bin/env python3
"""Recover a 27c6:5e0a PSK on Linux without pairing or writing to the sensor.

Based on Jet-Soup's issue #12 contribution: the MCU refuses whitebox tag
0xbb010003 by name, but returns its record through a read at the end of the
DPAPI blob in the 0xbb010002 area. Decryption reuses goodix_whitebox.py.
Only a key matching the same sensor's 0xbb020001 SHA-256 is saved.
"""

import argparse
import contextlib
import hashlib
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "legacy-experiments"))
sys.path.insert(0, str(ROOT / "legacy-experiments/vendor"))

RECORD_TAG = 0xBB010003
HASH_TAG = 0xBB020001
AREA_TAG = 0xBB010002
RECORD_LEN = 96
MAX_AREA = 4096


def load_dependencies():
    try:
        import usb.core  # noqa: F401
        import goodix_protocol
        sys.modules["protocol"] = goodix_protocol
        import goodix
        import goodix_whitebox
    except ImportError as error:
        raise RuntimeError(f"Missing extraction dependency: {error}. See docs/psk-extraction.md") from error
    if not goodix_whitebox.HAVE_CRYPTOGRAPHY and not shutil.which("openssl"):
        raise RuntimeError("Install python3-cryptography or OpenSSL before extracting the key")
    return goodix, goodix_protocol, goodix_whitebox.sec_white_decrypt


def read_region(device, tag, length, offset, *, allow_short=False):
    if not 0 <= offset < MAX_AREA or not 0 < length <= 400 or offset + length > MAX_AREA:
        raise ValueError("Read exceeds the bounded 4096-byte record area")
    # Vendor helpers print protocol traces; never include them in normal output.
    with contextlib.redirect_stdout(io.StringIO()):
        reply = device.preset_psk_read(tag, length, offset)
    if not isinstance(reply, (tuple, list)) or len(reply) != 3 or not reply[0]:
        raise ValueError("Sensor rejected the read or returned a malformed response")
    if not isinstance(reply[2], (bytes, bytearray, memoryview)):
        raise ValueError("Sensor returned a non-byte payload")
    data = bytes(reply[2])
    if not data or len(data) > length or (not allow_short and len(data) != length):
        raise ValueError(f"Invalid read length: requested {length}, received {len(data)}")
    return data


def find_record_offset(device):
    """Locate the next record from DPAPI lengths, without assuming 324 bytes."""
    from dump_dpapi_blob import parse_dpapi_blob_length

    data = bytearray()
    for length in (400, 256):
        try:
            data.extend(read_region(device, AREA_TAG, length, 0, allow_short=True))
            break
        except (ValueError, OSError, SystemError):
            continue
    if len(data) < 48 or int.from_bytes(data[:4], "little") != 1:
        raise ValueError("Cannot read a DPAPI version-1 header; no record offset was guessed")
    while True:
        total, complete = parse_dpapi_blob_length(data)
        if total is not None and not 48 <= total <= MAX_AREA - RECORD_LEN - 8:
            raise ValueError("DPAPI structure exceeds the bounded record area")
        if complete:
            return total
        if len(data) >= MAX_AREA - RECORD_LEN - 8:
            raise ValueError("Cannot determine a bounded DPAPI length")
        needed = total - len(data) if total is not None else 256
        length = min(256, needed, MAX_AREA - RECORD_LEN - 8 - len(data))
        if length <= 0:
            raise ValueError("Invalid DPAPI structure length")
        data.extend(read_region(device, AREA_TAG, length, len(data), allow_short=True))


def read_record(device, offset):
    """Accept a tagged 104-byte record or an exactly addressed 96-byte payload."""
    # Preserve the contributor's tested combined read. Some firmware rejects
    # reading eight bytes past a payload-only record; retry that form at 96.
    try:
        data = read_region(device, AREA_TAG, RECORD_LEN + 8, offset, allow_short=True)
    except (ValueError, OSError, SystemError):
        data = read_region(device, AREA_TAG, RECORD_LEN, offset)
    if int.from_bytes(data[:4], "little") == RECORD_TAG:
        if len(data) < 8 or int.from_bytes(data[4:8], "little") != RECORD_LEN:
            raise ValueError("Whitebox record has an invalid length")
        if len(data) < RECORD_LEN + 8:
            data += read_region(device, AREA_TAG, RECORD_LEN + 8 - len(data), offset + len(data))
        return data[8:RECORD_LEN + 8]
    if len(data) < RECORD_LEN:
        raise ValueError("Whitebox payload is truncated")
    # The shared decryptor validates prefix, length, HMAC and padding.
    return data[:RECORD_LEN]


def write_key(path, key, force=False):
    """Publish a complete 0600 file; failed replacements preserve the old key."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".goodix-psk-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write((key.hex() + "\n").encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            # Replace the directory entry, including a symlink itself, atomically.
            os.replace(temporary, path)
        else:
            # Atomic no-clobber publication; an existing file/symlink is untouched.
            os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def bounded_offset(value):
    offset = int(value, 0)
    if not 0 <= offset <= MAX_AREA - RECORD_LEN - 8:
        raise argparse.ArgumentTypeError("Offset must be between 0 and 3992")
    return offset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("goodix-5e0a.psk"))
    parser.add_argument("--offset", type=bounded_offset,
                        help="Expert override: record or payload offset; default: parse DPAPI length")
    parser.add_argument("--force", action="store_true", help="Atomically replace an existing output")
    parser.add_argument("--print-key", action="store_true", help="Also print the verified secret key")
    args = parser.parse_args(argv)
    if not args.force and os.path.lexists(args.out):
        raise FileExistsError(f"{args.out} exists; use --force only to replace it intentionally")
    goodix, protocol, decrypt = load_dependencies()
    device = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            device = goodix.Device(0x5e0a, protocol.USBProtocol)
            device.nop()
        expected = read_region(device, HASH_TAG, 32, 0)
        offset = args.offset if args.offset is not None else find_record_offset(device)
        key = decrypt(read_record(device, offset), expected_len=32)
        if len(key) != 32 or hashlib.sha256(key).digest() != expected:
            raise ValueError("Recovered key does not match this sensor's SHA-256; nothing written")
        write_key(args.out, key, args.force)
        print(f"Verified this sensor's key; saved to {args.out} (mode 0600).")
        if args.print_key:
            print(key.hex())
        return 0
    finally:
        if device is not None:
            with contextlib.suppress(Exception), contextlib.redirect_stdout(io.StringIO()):
                device.disconnect()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        print(f"Extraction stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
