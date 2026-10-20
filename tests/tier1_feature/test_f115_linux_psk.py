"""Linux PSK recovery with synthetic encrypted records; no USB or real keys."""

import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from tests.tier1_feature.test_f111_dpapi_and_diagnostics import make_dummy_dpapi_blob

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("extract_psk_whitebox", ROOT / "tools/extract_psk_whitebox.py")
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)
from goodix_whitebox import sec_white_encrypt, sec_white_decrypt

KEY = bytes(range(32))
RECORD = sec_white_encrypt(KEY)
HEADER = struct.pack("<II", TOOL.RECORD_TAG, len(RECORD))


class Sensor:
    def __init__(self, blob=None, *, hash_value=None, record=RECORD, max_read=400):
        self.blob = make_dummy_dpapi_blob() if blob is None else blob
        self.area = self.blob + HEADER + record
        self.hash_value = hashlib.sha256(KEY).digest() if hash_value is None else hash_value
        self.max_read = max_read
        self.calls = []
        self.closed = False

    def nop(self):
        self.calls.append("nop")

    def disconnect(self):
        self.closed = True

    def preset_psk_read(self, tag, length, offset):
        self.calls.append((tag, length, offset))
        if tag == TOOL.HASH_TAG:
            return True, tag, self.hash_value
        if tag != TOOL.AREA_TAG or length > self.max_read:
            return False, None, None
        return True, tag, self.area[offset:offset + length]


class LinuxPskTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sensor.psk"
        self.stdout = io.StringIO()

    def run_tool(self, sensor, extra=()):
        deps = (types.SimpleNamespace(Device=lambda *args: sensor),
                types.SimpleNamespace(USBProtocol=object), sec_white_decrypt)
        with mock.patch.object(TOOL, "load_dependencies", return_value=deps), contextlib.redirect_stdout(self.stdout):
            return TOOL.main(["--out", str(self.path), *extra])

    def test_verified_key_uses_sensor_hash_and_private_output(self):
        sensor = Sensor()
        self.assertEqual(self.run_tool(sensor), 0)
        self.assertEqual(self.path.read_text(), KEY.hex() + "\n")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertNotIn(KEY.hex(), self.stdout.getvalue())
        self.assertTrue(sensor.closed)
        self.assertEqual(sensor.calls, ["nop", (TOOL.HASH_TAG, 32, 0),
                                      (TOOL.AREA_TAG, 400, 0), (TOOL.AREA_TAG, 104, 324)])

    def test_offset_follows_valid_dpapi_length_instead_of_324(self):
        for description in (b"\0" * 100, b"\0" * 600):
            with self.subTest(description_length=len(description)):
                sensor = Sensor(make_dummy_dpapi_blob(desc=description))
                self.assertEqual(TOOL.find_record_offset(sensor), len(sensor.blob))
                self.assertEqual(TOOL.read_record(sensor, len(sensor.blob)), RECORD)

    def test_256_byte_read_fallback_completes_dpapi(self):
        sensor = Sensor(max_read=256)
        self.assertEqual(TOOL.find_record_offset(sensor), 324)
        self.assertIn((TOOL.AREA_TAG, 68, 256), sensor.calls)

    def test_payload_only_at_end_accepts_short_combined_response(self):
        self.assertEqual(TOOL.read_record(Sensor(), 332), RECORD)

    def test_payload_only_retries_when_firmware_rejects_overread(self):
        sensor = Sensor()
        original = sensor.preset_psk_read
        sensor.preset_psk_read = lambda tag, length, offset: (
            (False, None, None) if offset == 332 and length == 104 else original(tag, length, offset))
        self.assertEqual(TOOL.read_record(sensor, 332), RECORD)

    def test_manual_offset_skips_dpapi_discovery(self):
        sensor = Sensor(blob=b"invalid DPAPI" * 25)
        self.assertEqual(self.run_tool(sensor, ["--offset", hex(len(sensor.blob))]), 0)
        self.assertNotIn((TOOL.AREA_TAG, 400, 0), sensor.calls)

    def test_wrong_sensor_hash_preserves_old_key_even_with_force(self):
        self.path.write_bytes(b"existing verified key")
        sensor = Sensor(hash_value=bytes(32))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.run_tool(sensor, ["--force", "--print-key"])
        self.assertEqual(self.path.read_bytes(), b"existing verified key")
        self.assertNotIn(KEY.hex(), self.stdout.getvalue())
        self.assertTrue(sensor.closed)

    def test_missing_short_and_nonbyte_hash_never_create_file(self):
        for value in (b"", bytes(31), None, 32):
            with self.subTest(value_type=type(value).__name__):
                sensor = Sensor()
                sensor.hash_value = value
                with self.assertRaises(ValueError):
                    self.run_tool(sensor)
                self.assertFalse(self.path.exists())
                self.assertTrue(sensor.closed)

    def test_damaged_hmac_never_creates_file(self):
        bad = RECORD[:-1] + bytes([RECORD[-1] ^ 1])
        with self.assertRaisesRegex(ValueError, "HMAC"):
            self.run_tool(Sensor(record=bad))
        self.assertFalse(self.path.exists())

    def test_wrong_record_length_and_truncated_record_are_rejected(self):
        for area in (make_dummy_dpapi_blob() + struct.pack("<II", TOOL.RECORD_TAG, 80) + RECORD,
                     make_dummy_dpapi_blob() + HEADER + RECORD[:-1]):
            sensor = Sensor()
            sensor.area = area
            with self.assertRaises(ValueError):
                TOOL.read_record(sensor, 324)

    def test_invalid_or_excessive_dpapi_does_not_guess_offset(self):
        for blob in (b"\0" * 400, make_dummy_dpapi_blob(desc=b"\0" * 5000)):
            sensor = Sensor(blob=blob)
            with self.assertRaises(ValueError):
                TOOL.find_record_offset(sensor)
            self.assertLessEqual(len(sensor.calls), 18)
            self.assertTrue(all(offset + length <= TOOL.MAX_AREA for tag, length, offset in sensor.calls))

    def test_read_bounds_reject_before_usb(self):
        sensor = Sensor()
        for length, offset in ((401, 0), (32, -1), (104, 4090), (0, 0)):
            with self.assertRaises(ValueError):
                TOOL.read_region(sensor, TOOL.AREA_TAG, length, offset)
        self.assertEqual(sensor.calls, [])

    def test_existing_output_refused_before_opening_sensor(self):
        self.path.write_bytes(b"keep me")
        with mock.patch.object(TOOL, "load_dependencies") as load:
            with self.assertRaises(FileExistsError):
                TOOL.main(["--out", str(self.path)])
            load.assert_not_called()
        self.assertEqual(self.path.read_bytes(), b"keep me")

    def test_force_replace_failure_preserves_old_key_and_cleans_temporary(self):
        self.path.write_bytes(b"old valid key")
        with mock.patch.object(TOOL.os, "replace", side_effect=OSError("injected failure")):
            with self.assertRaises(OSError):
                TOOL.write_key(self.path, KEY, force=True)
        self.assertEqual(self.path.read_bytes(), b"old valid key")
        self.assertEqual(list(self.path.parent.glob(".goodix-psk-*")), [])

    def test_force_fsync_failure_preserves_old_key(self):
        self.path.write_bytes(b"old valid key")
        with mock.patch.object(TOOL.os, "fsync", side_effect=OSError("injected failure")):
            with self.assertRaises(OSError):
                TOOL.write_key(self.path, KEY, force=True)
        self.assertEqual(self.path.read_bytes(), b"old valid key")
        self.assertEqual(list(self.path.parent.glob(".goodix-psk-*")), [])

    def test_no_clobber_handles_file_appearing_during_extraction(self):
        self.path.write_bytes(b"concurrent output")
        with self.assertRaises(FileExistsError):
            TOOL.write_key(self.path, KEY)
        self.assertEqual(self.path.read_bytes(), b"concurrent output")

    def test_symlink_target_is_never_overwritten(self):
        target = self.path.parent / "target"
        target.write_bytes(b"keep target")
        self.path.symlink_to(target)
        with self.assertRaises(FileExistsError):
            TOOL.write_key(self.path, KEY)
        TOOL.write_key(self.path, KEY, force=True)
        self.assertFalse(self.path.is_symlink())
        self.assertEqual(target.read_bytes(), b"keep target")
        self.assertEqual(self.path.read_text(), KEY.hex() + "\n")

    def test_shared_vendor_import_with_eager_annotations_needs_no_hardware(self):
        # Also run this test with Python 3.12. USB is stubbed; real vendor and
        # transport modules are imported, so absent Protocol annotations regress.
        code = '''import sys, types
sys.path[:0] = [sys.argv[1], sys.argv[2]]
usb = types.ModuleType("usb"); usb.__path__ = []
core = types.ModuleType("usb.core"); usb.core = core
sys.modules["usb"] = usb; sys.modules["usb.core"] = core
import goodix_protocol
sys.modules["protocol"] = goodix_protocol
import goodix
assert callable(goodix.Device)
'''
        subprocess.run([sys.executable, "-c", code, str(ROOT / "legacy-experiments"),
                        str(ROOT / "legacy-experiments/vendor")], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
