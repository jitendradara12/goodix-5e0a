"""Offline cache extraction: corruption rejection and least-data export.

Known checksum values are additionally checked against actual wbdi.dll
instructions by calibration_contract.py. No real biometric fixtures are stored.
"""

import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/extract_goodix_calibration.py"
SPEC = importlib.util.spec_from_file_location("calibration_export", SCRIPT)
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


def record(name, data):
    header = (name + "\0").encode("utf-16-le").ljust(128, b"\0")
    return header + struct.pack("<II", len(data), EXPORT.crc32_mpeg2(data)) + data


class CalibrationCacheTests(unittest.TestCase):
    def setUp(self):
        self.image = struct.pack("<5120H", *(i % 4096 for i in range(5120)))
        self.data = (
            b"NLVF"
            + record("Otp", b"omit-this-payload")
            + record("ImageBase", self.image)
        )

    def test_vendor_crc_known_answers(self):
        for data, expected in [
            (b"", 0xFFFFFFFF),
            (b"123456789", 0x0376E6E7),
            (bytes(range(256)), 0x494A116A),
        ]:
            self.assertEqual(EXPORT.crc32_mpeg2(data), expected)

    def test_export_preserves_pixels_and_omits_other_payloads(self):
        files, metadata = EXPORT.calibration_export(self.data)
        self.assertEqual(set(files), {"background_raw.pgm", "calibration.json"})
        pixels = struct.unpack(">5120H", files["background_raw.pgm"].split(b"\n", 3)[3])
        self.assertEqual(pixels, struct.unpack("<5120H", self.image))
        self.assertEqual(metadata["omitted_record_payloads"], ["Otp"])
        self.assertNotIn(b"omit-this-payload", b"".join(files.values()))

    def test_state_is_exported_as_opaque_data_with_size_metadata(self):
        state = bytes(EXPORT.ENGINE_STATE_BYTES)
        files, metadata = EXPORT.calibration_export(
            self.data + record("CaliData", state)
        )
        self.assertEqual(files["calibration_state.bin"], state)
        self.assertTrue(metadata["state_size_matches_reviewed_engine"])
        self.assertEqual(json.loads(files["calibration.json"]), metadata)

    def test_record_lookup_is_case_insensitive_and_case_duplicates_rejected(self):
        files, _ = EXPORT.calibration_export(b"NLVF" + record("imagebase", self.image))
        self.assertIn("background_raw.pgm", files)
        with self.assertRaises(ValueError):
            EXPORT.parse_nlvf(self.data + record("imagebase", self.image))

    def test_corrupt_and_truncated_inputs_rejected(self):
        damaged = self.data[:-1] + bytes([self.data[-1] ^ 1])
        for data in [
            b"wrong",
            self.data[:10],
            self.data[:-1],
            self.data + b"\0",
            damaged,
            self.data + record("ImageBase", self.image),
            b"NLVF" + b"X\0" * 64 + bytes(8),
        ]:
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                EXPORT.parse_nlvf(data)

    def test_wrong_geometry_and_out_of_range_image_rejected(self):
        for image in [bytes(5120), struct.pack("<5120H", *([4096] * 5120))]:
            with self.assertRaises(ValueError):
                EXPORT.calibration_export(b"NLVF" + record("ImageBase", image))

    def test_cli_preserves_source_and_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "goodix.dat", root / "calibration.zip"
            source.write_bytes(self.data)
            command = [sys.executable, str(SCRIPT), str(source), "--out", str(output)]
            subprocess.run(command, check=True, capture_output=True)
            original_export = output.read_bytes()
            repeat = subprocess.run(command, check=False, capture_output=True)
            self.assertNotEqual(repeat.returncode, 0)
            self.assertEqual(source.read_bytes(), self.data)
            self.assertEqual(output.read_bytes(), original_export)


if __name__ == "__main__":
    unittest.main()
