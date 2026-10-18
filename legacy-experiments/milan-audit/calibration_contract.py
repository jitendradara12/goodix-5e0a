"""Check the recovered Windows calibration cache contract against real code.

Only the archived CRC and NLVF record-reader functions execute under Unicorn.
File operations use an in-memory byte stream, and _wcsicmp uses ASCII key
comparison. No Windows process, file write, sensor or service is involved.
"""

import argparse
import importlib.util
import io
import json
import struct
import tempfile
from pathlib import Path

from emulator import Engine
from preprocess import GuardedBuffer
from run import ROOT, archived, digest
from unicorn.x86_const import UC_X86_REG_RAX

WBDI_SHA256 = "ce541d886983e628914aa7317f90711a363a5008ce250bceb40b64de9a45ce92"


class CacheEngine(Engine):
    FILE = 0x123456

    def __init__(self, path):
        super().__init__(path)
        # The base emulator's diagnostic locations describe the engine DLL.
        # Restore those bytes, then bypass only wbdi's logger and cookie check.
        for address in self.bypass:
            self.u.mem_write(address, self.pe.get_data(address - self.base, 1))
        self.bypass = {self.base + 0xC1620: "logger", self.base + 0xC5EB0: "cookie"}
        for address in self.bypass:
            self.u.mem_write(address, b"\xc3")
        self.stream = io.BytesIO()
        self.errno_address = self.put(bytes(4))

    def wide_key(self, address):
        units = []
        for offset in range(64):
            value = struct.unpack("<H", self.u.mem_read(address + offset * 2, 2))[0]
            if value == 0:
                return "".join(map(chr, units)).lower()
            if value > 127:
                raise RuntimeError("Only ASCII cache keys are supported by this check")
            units.append(value)
        raise RuntimeError("Unterminated cache key in vendor call")

    def hook(self, u, address, size, data):
        name = self.shims[address]
        if name not in {"fseek", "ftell", "fread", "_wcsicmp", "_errno"}:
            return super().hook(u, address, size, data)
        self.seen[name] = self.seen.get(name, 0) + 1
        args = self.args(4)
        if name == "_errno":
            result = self.errno_address
        elif name == "_wcsicmp":
            first, second = self.wide_key(args[0]), self.wide_key(args[1])
            result = (first > second) - (first < second)
        elif name == "fseek":
            assert args[0] == self.FILE
            offset = args[1] if args[1] < 2**63 else args[1] - 2**64
            self.stream.seek(offset, args[2])
            result = 0
        elif name == "ftell":
            assert args[0] == self.FILE
            result = self.stream.tell()
        else:
            assert args[3] == self.FILE
            if args[1] * args[2] > 64 * 1024 * 1024:
                raise RuntimeError("Unexpected file read size")
            payload = self.stream.read(args[1] * args[2])
            if payload:
                u.mem_write(args[0], payload)
            result = len(payload) // args[1] if args[1] else 0
        u.reg_write(UC_X86_REG_RAX, result & 0xFFFFFFFFFFFFFFFF)

    def read_record(self, data, name, size):
        self.stream = io.BytesIO(data)
        handle = self.put(struct.pack("<Q", self.FILE))
        output = GuardedBuffer(self, bytes(size))
        length = GuardedBuffer(self, bytes(4))
        code = self.call(
            self.base + 0xC5090,
            [
                handle,
                self.put((name + "\0").encode("utf-16-le")),
                output.address,
                size,
                length.address,
            ],
        )
        return code & 0xFFFFFFFF, output.read(), struct.unpack("<I", length.read())[0]


def check_contract():
    data = archived("legacy-experiments/windows_driver/wbdi.dll")
    if digest(data) != WBDI_SHA256:
        raise ValueError("Unreviewed wbdi DLL")
    spec = importlib.util.spec_from_file_location(
        "calibration_export", ROOT / "tools/extract_goodix_calibration.py"
    )
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    with tempfile.TemporaryDirectory(prefix="goodix-cache-contract-") as temporary:
        path = Path(temporary) / "wbdi.dll"
        path.write_bytes(data)
        engine = CacheEngine(str(path))
        calls = {
            0x892BC: 0x7C574,
            0x7C72D: 0x37094,
            0x371BE: 0xC8D80,
            0x80C84: 0x4A18C,
            0x36F0A: 0xC84F0,
        }
        for source, target in calls.items():
            instruction = engine.pe.get_data(source, 5)
            assert instruction[0] == 0xE8
            assert source + 5 + struct.unpack("<i", instruction[1:])[0] == target
        keys = {
            0x1982D0: "Goodix\\goodix.dat",
            0x198320: "ImageBase",
            0x198338: "CaliData",
        }
        for address, value in keys.items():
            assert engine.pe.get_data(address, len(value) * 2 + 2) == (
                value + "\0"
            ).encode("utf-16-le")
        crc_vectors = []
        for payload, expected in [
            (b"", 0xFFFFFFFF),
            (b"123456789", 0x0376E6E7),
            (bytes(range(256)), 0x494A116A),
        ]:
            actual = (
                engine.call(
                    engine.base + 0xC2C80, [engine.put(payload or b"\0"), len(payload)]
                )
                & 0xFFFFFFFF
            )
            assert actual == exporter.crc32_mpeg2(payload) == expected
            crc_vectors.append({"bytes": len(payload), "crc": hex(actual)})

        def record(name, payload):
            key = (name + "\0").encode("utf-16-le").ljust(128, b"\0")
            return (
                key
                + struct.pack("<II", len(payload), exporter.crc32_mpeg2(payload))
                + payload
            )

        background = struct.pack("<5120H", *(i % 4096 for i in range(5120)))
        cache = (
            b"NLVF" + record("Otp", b"not-exported") + record("ImageBase", background)
        )
        code, returned, length = engine.read_record(cache, "imagebase", len(background))
        assert code == 1 and returned == background and length == len(background)
        parsed = exporter.parse_nlvf(cache)
        assert parsed["ImageBase"] == returned
        corrupt = cache[:-1] + bytes([cache[-1] ^ 1])
        assert engine.read_record(corrupt, "ImageBase", len(background))[0] == 0
        assert engine.read_record(cache[:-1], "ImageBase", len(background))[0] == 0
        assert engine.read_record(cache, "Missing", len(background))[0] == 0
        imports = dict(engine.seen)
    return {
        "hardware_run": False,
        "wbdi_sha256": WBDI_SHA256,
        "binary_call_edges": {hex(k): hex(v) for k, v in calls.items()},
        "cache_path": "C:\\ProgramData\\Goodix\\goodix.dat",
        "cache_keys": ["ImageBase", "CaliData"],
        "crc_vectors_executed": crc_vectors,
        "vendor_record_reader_matches_extractor": True,
        "case_insensitive_ascii_key_lookup": True,
        "vendor_record_reader_rejects_crc_damage_truncation_missing_key": True,
        "vendor_record_reader_output_guards_intact": True,
        "imports": imports,
        "boundary": "Synthetic cache; actual wbdi record reader and CRC; in-memory stdio and ASCII _wcsicmp shims; no real cache or sensor identity validation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = check_contract()
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Windows calibration cache contract passed; saved {args.out}")


if __name__ == "__main__":
    main()
