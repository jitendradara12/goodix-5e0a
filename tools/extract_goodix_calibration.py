#!/usr/bin/env python3
"""Read a Windows Goodix NLVF cache and export only its calibration records.

Standard-library-only, offline, read-only access to the input file. This does
not access the sensor, fingerprint enrollments, PSK storage, or any service.
The source is normally C:\\ProgramData\\Goodix\\goodix.dat on the same laptop
that produced the raw captures. No driver installation or new scan is needed.
"""

import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path

WIDTH, HEIGHT = 64, 80
MAX_FILE_BYTES = 64 * 1024 * 1024
RECORD_HEADER = 0x88
ENGINE_STATE_BYTES = 0x224B0


def crc32_mpeg2(data):
    """Vendor NLVF checksum: non-reflected 0x04c11db7, init FFFFFFFF, no xorout."""
    crc = 0xFFFFFFFF
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
    return crc


def parse_nlvf(data):
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File exceeds the 64 MiB calibration-cache limit")
    if data[:4] != b"NLVF":
        raise ValueError("Not the supported Windows Goodix NLVF cache format")
    records = {}
    names = set()
    position = 4
    while position < len(data):
        if len(records) >= 128:
            raise ValueError("Too many cache records")
        if len(data) - position < RECORD_HEADER:
            raise ValueError("Truncated NLVF record header")
        header = data[position : position + RECORD_HEADER]
        units = struct.unpack("<64H", header[:128])
        try:
            end = units.index(0)
        except ValueError as error:
            raise ValueError("Unterminated NLVF record name") from error
        name = header[: end * 2].decode("utf-16-le")
        if not name or name.casefold() in names:
            raise ValueError("Empty or duplicate NLVF record name")
        names.add(name.casefold())
        length, expected_crc = struct.unpack_from("<II", header, 128)
        position += RECORD_HEADER
        if length > len(data) - position:
            raise ValueError(f"Truncated NLVF record: {name!r}")
        payload = data[position : position + length]
        if crc32_mpeg2(payload) != expected_crc:
            raise ValueError(f"NLVF checksum mismatch: {name!r}")
        records[name] = payload
        position += length
    return records


def calibration_export(data):
    records = parse_nlvf(data)
    # NlvFsRead compares names with _wcsicmp, including the ASCII cache keys.
    by_name = {name.casefold(): value for name, value in records.items()}
    image = by_name.get("imagebase")
    if image is None or len(image) != WIDTH * HEIGHT * 2:
        raise ValueError("Need a 10,240-byte ImageBase for a 64x80 Milan sensor")
    pixels = struct.unpack(f"<{WIDTH * HEIGHT}H", image)
    if max(pixels) > 4095:
        raise ValueError("ImageBase contains values outside the expected 12-bit range")
    # PGM uses big-endian samples; the cache's uint16 image is little-endian.
    pgm = b"P5\n64 80\n4095\n" + struct.pack(f">{WIDTH * HEIGHT}H", *pixels)
    files = {"background_raw.pgm": pgm}
    state = by_name.get("calidata")
    if state:
        files["calibration_state.bin"] = state
    metadata = {
        "format": "goodix-windows-calibration-export-v1",
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "source_format": "NLVF; UTF-16LE names; CRC-32/MPEG-2 checked",
        "source_record_sizes": {name: len(value) for name, value in records.items()},
        "export_sha256": {
            name: hashlib.sha256(value).hexdigest() for name, value in files.items()
        },
        "image_geometry": {"width": WIDTH, "height": HEIGHT, "maximum": 4095},
        "image_geometry_role": "PGM container dimensions; ImageBase record sample order is preserved, not inferred",
        "image_alignment": "Unverified against driver frames; establish orientation before using as calibration",
        "background_min_max": [min(pixels), max(pixels)],
        "calibration_state_bytes": len(state) if state else 0,
        "state_size_matches_reviewed_engine": bool(
            state and len(state) == ENGINE_STATE_BYTES
        ),
        "provenance": "Windows cached ImageBase; operator must confirm same sensor as the captures",
        "boundary": "Cache format/CRC validation does not prove background freshness or sensor identity",
        "omitted_record_payloads": sorted(
            name for name in records if name.casefold() not in {"imagebase", "calidata"}
        ),
    }
    files["calibration.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
    return files, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Same laptop's Windows ProgramData/Goodix/goodix.dat"
    )
    parser.add_argument("--out", type=Path, default=Path("goodix-calibration.zip"))
    args = parser.parse_args()
    if args.source.resolve() == args.out.resolve():
        parser.error("Output must differ from the source file")
    try:
        with args.source.open("rb") as source:
            data = source.read(MAX_FILE_BYTES + 1)
        files, metadata = calibration_export(data)
        # Never overwrite an earlier export or the source cache.
        with zipfile.ZipFile(
            args.out, "x", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name, value in files.items():
                archive.writestr(name, value)
    except (OSError, ValueError, UnicodeError, struct.error) as error:
        parser.exit(1, f"Calibration export failed: {error}\n")
    print(f"Saved {args.out}: {', '.join(files)}")
    if not metadata["state_size_matches_reviewed_engine"]:
        print(
            "Calibration state is missing or differs in size; keep the metadata with the background export."
        )
    print("The source file, sensor, driver and enrollments were not changed.")


if __name__ == "__main__":
    main()
