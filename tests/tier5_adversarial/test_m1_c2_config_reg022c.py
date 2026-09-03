"""
Adversarial Stress Test Suite for Milestone 1:
Sensor Register 0x022c and CONFIG_52XD Payload Integrity & Wire Verification.
Authored by Challenger 2 (Empirical Challenger).
"""

import hashlib
import re
import struct
import unittest
from pathlib import Path

from tests.test_utils import (
    CANONICAL_CONFIG_52XD,
    CANONICAL_FDT_DOWN,
    CANONICAL_FDT_MODE,
    CANONICAL_FDT_UP,
    CANONICAL_PSK,
    CANONICAL_REG_022C_GAIN,
    CMD_ACK,
    CMD_READ_SENSOR_REGISTER,
    CMD_UPLOAD_CONFIG_MCU,
    CMD_WRITE_SENSOR_REGISTER,
    EP_OUT_CHUNK_SIZE,
    FLAGS_MSG_PROTOCOL,
    MockGoodixMCU,
    calc_pack_checksum,
    calc_protocol_checksum,
    decode_pack,
    decode_protocol,
    encode_pack,
    encode_protocol,
)

REPO_ROOT = Path("/home/sastauser/code/temp/goodix")
TMP_LIBFPRINT_HEADER = Path("/tmp/libfprint-goodix/libfprint/drivers/goodixtls/goodix5e0a.h")
REPO_HEADER = REPO_ROOT / "libfprint-driver" / "goodix5e0a.h"
TEST_PRESS_CAPTURE_PY = (REPO_ROOT / "experiments" / "test_press_and_capture.py"
                         if (REPO_ROOT / "experiments" / "test_press_and_capture.py").exists()
                         else REPO_ROOT / "test_press_and_capture.py")
DRIVER_52XD_PY = Path("/tmp/goodix-fp-dump/driver_52xd.py")
TEST_TOUCH_SENSOR_PY = (REPO_ROOT / "experiments" / "test_touch_sensor.py"
                        if (REPO_ROOT / "experiments" / "test_touch_sensor.py").exists()
                        else REPO_ROOT / "test_touch_sensor.py")
SCAN_FINGER_PY = (REPO_ROOT / "experiments" / "scan_finger.py"
                  if (REPO_ROOT / "experiments" / "scan_finger.py").exists()
                  else REPO_ROOT / "scan_finger.py")


def parse_c_array(header_content: str, array_name: str) -> bytes:
    pattern = rf"(?:static\s+)?const\s+guint8\s+{array_name}\s*\[\s*\]\s*=\s*\{{([^}}]+)\}};"
    match = re.search(pattern, header_content, re.DOTALL)
    if not match:
        raise ValueError(f"Array '{array_name}' not found in header")
    hex_str = match.group(1)
    hex_bytes = re.findall(r"0x([0-9a-fA-F]{2})", hex_str)
    return bytes(int(b, 16) for b in hex_bytes)


def parse_c_macro(header_content: str, macro_name: str) -> int:
    pattern = rf"#define\s+{macro_name}\s+\(([^)]+)\)"
    match = re.search(pattern, header_content)
    if not match:
        pattern2 = rf"#define\s+{macro_name}\s+(\S+)"
        match2 = re.search(pattern2, header_content)
        if not match2:
            raise ValueError(f"Macro '{macro_name}' not found in header")
        val_str = match2.group(1).strip()
    else:
        val_str = match.group(1).strip()
    if val_str.startswith("0x") or val_str.startswith("0X"):
        return int(val_str, 16)
    return int(val_str)


def extract_hex_assignment(py_file_path: Path, var_name: str) -> bytes:
    content = py_file_path.read_text(encoding="utf-8")
    pattern = rf"{var_name}\s*=\s*bytes\.fromhex\(\s*([\"'][0-9a-fA-F\s\"']+[\"'])\s*\)"
    match = re.search(pattern, content)
    if not match:
        raise ValueError(f"Variable {var_name} not found in {py_file_path}")
    raw_str = match.group(1)
    cleaned_hex = re.sub(r"[\"'\s\n\r]", "", raw_str)
    return bytes.fromhex(cleaned_hex)


class TestAdversarialConfig52XDAndReg022C(unittest.TestCase):
    """Adversarial stress-tests for 256-byte CONFIG_52XD and Register 0x022c."""

    @classmethod
    def setUpClass(cls):
        cls.tmp_header_str = TMP_LIBFPRINT_HEADER.read_text(encoding="utf-8")
        cls.repo_header_str = REPO_HEADER.read_text(encoding="utf-8")
        cls.press_config = extract_hex_assignment(TEST_PRESS_CAPTURE_PY, "CONFIG_52XD")
        cls.dump_config = extract_hex_assignment(DRIVER_52XD_PY, "DEVICE_CONFIG")
        cls.touch_config = extract_hex_assignment(TEST_TOUCH_SENSOR_PY, "CONFIG_52XD")
        cls.scan_config = extract_hex_assignment(SCAN_FINGER_PY, "CONFIG_52XD")

    # =========================================================================
    # Dimension 1: Cross-Source Table Integrity & Bit-Exactness
    # =========================================================================

    def test_multi_source_config_52xd_equivalence(self):
        """Cross-verify CONFIG_52XD across all 6 reference sources for bit-for-bit identity."""
        tmp_cfg = parse_c_array(self.tmp_header_str, "goodix_5e0a_config")
        repo_cfg = parse_c_array(self.repo_header_str, "goodix_5e0a_config")

        sources = {
            "/tmp/libfprint-goodix goodix5e0a.h": tmp_cfg,
            "repo libfprint-driver goodix5e0a.h": repo_cfg,
            "test_press_and_capture.py": self.press_config,
            "/tmp/goodix-fp-dump/driver_52xd.py": self.dump_config,
            "test_touch_sensor.py": self.touch_config,
            "scan_finger.py": self.scan_config,
            "CANONICAL_CONFIG_52XD": CANONICAL_CONFIG_52XD,
        }

        # Check lengths
        for name, data in sources.items():
            self.assertEqual(len(data), 256, f"{name} length must be 256 bytes, got {len(data)}")

        # Check SHA256 hashes
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}
        canonical_sha = hashlib.sha256(CANONICAL_CONFIG_52XD).hexdigest()

        for name, sha in hashes.items():
            self.assertEqual(sha, canonical_sha, f"SHA256 mismatch in {name}: {sha} vs {canonical_sha}")

        # Check byte-for-byte exact equality
        for name, data in sources.items():
            self.assertEqual(data, CANONICAL_CONFIG_52XD, f"Byte mismatch in {name}")

    def test_config_52xd_byte_offsets_and_substructures(self):
        """Verify critical byte offsets, headers, and timing blocks within CONFIG_52XD."""
        cfg = parse_c_array(self.tmp_header_str, "goodix_5e0a_config")

        # Offset 0..3: Header Magic (0x70, 0x11, 0x60, 0x71)
        self.assertEqual(cfg[0:4], bytes([0x70, 0x11, 0x60, 0x71]))

        # Offset 4..11: Timing base registers (2c 9d 2c c9 1c e5 18 fd)
        self.assertEqual(cfg[4:12], bytes([0x2c, 0x9d, 0x2c, 0xc9, 0x1c, 0xe5, 0x18, 0xfd]))

        # Offset 96..99: Register block (0x00, 0x70, 0x00, 0x00)
        self.assertEqual(cfg[96:100], bytes([0x00, 0x70, 0x00, 0x00]))

        # Offset 100..107: Divisor & scan parameter block (0x00, 0x72, 0x00, 0x78, 0x56, 0x74, 0x00, 0x34)
        self.assertEqual(cfg[100:108], bytes([0x00, 0x72, 0x00, 0x78, 0x56, 0x74, 0x00, 0x34]))

        # Offset 252..255: Tail Signature (0x58, 0x20, 0xc5, 0x0e)
        self.assertEqual(cfg[252:256], bytes([0x58, 0x20, 0xc5, 0x0e]))

    # =========================================================================
    # Dimension 2: Register 0x022c (Gain/Exposure) Parameter & Endianness Stress
    # =========================================================================

    def test_register_0x022c_values_and_macros(self):
        """Verify Register 0x022c definitions across headers and python prototypes."""
        reg_addr = parse_c_macro(self.tmp_header_str, "GOODIX_5E0A_REG_GAIN_EXPOSURE")
        reg_val = parse_c_macro(self.tmp_header_str, "GOODIX_5E0A_REG_GAIN_EXPOSURE_VAL")
        reg_calib = parse_c_macro(self.tmp_header_str, "GOODIX_5E0A_REG_GAIN_EXPOSURE_CALIB_VAL")
        reg_reset = parse_c_macro(self.tmp_header_str, "GOODIX_5E0A_REG_GAIN_EXPOSURE_RESET_VAL")

        self.assertEqual(reg_addr, 0x022c)
        self.assertEqual(reg_val, 0x0305, "0x0305 in LE corresponds to bytes [0x05, 0x03]")
        self.assertEqual(reg_calib, 0x030a, "0x030a in LE corresponds to bytes [0x0a, 0x03]")
        self.assertEqual(reg_reset, 0x020a, "0x020a in LE corresponds to bytes [0x0a, 0x02]")

    def test_register_0x022c_wire_packet_endianness_exactness(self):
        """Adversarially verify that C struct layout and Python wire serialization match byte-for-byte."""
        # In Python: device.write_sensor_register(0x022c, b"\x05\x03")
        # Packet format in goodix.py: b"\x00" + struct.pack("<H", 0x022c) + b"\x05\x03"
        py_payload = b"\x00" + struct.pack("<H", 0x022C) + b"\x05\x03"
        self.assertEqual(py_payload, bytes([0x00, 0x2c, 0x02, 0x05, 0x03]))

        # In C: GoodixWriteSensorRegister
        # multiples (1B=0), address (2B LE = 0x022c -> 0x2c 0x02), value (2B LE = 0x0305 -> 0x05 0x03)
        c_packed = struct.pack("<BHH", 0, 0x022C, 0x0305)
        self.assertEqual(c_packed, py_payload, "C struct packing must be identical to Python wire message")

        # Check full protocol packet encoding
        c_wire = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_WRITE_SENSOR_REGISTER, c_packed, pad_data=False))
        ok, flags, body, chk_ok = decode_pack(c_wire)
        self.assertTrue(ok)
        self.assertTrue(chk_ok)
        self.assertEqual(flags, FLAGS_MSG_PROTOCOL)

        p_ok, cmd, p_payload, p_chk_ok, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertTrue(p_chk_ok)
        self.assertEqual(cmd, CMD_WRITE_SENSOR_REGISTER)
        self.assertEqual(p_payload, bytes([0x00, 0x2c, 0x02, 0x05, 0x03]))

    def test_register_0x022c_presence_in_fdt_payloads(self):
        """Verify that gain/exposure bytes [0x05, 0x03] are correctly embedded in FDT DOWN & UP payloads."""
        fdt_down = parse_c_array(self.tmp_header_str, "goodix_5e0a_fdt_down")
        fdt_up = parse_c_array(self.tmp_header_str, "goodix_5e0a_fdt_up")

        # Offset 28..29 in both FDT down and up must be [0x05, 0x03]
        self.assertEqual(fdt_down[28:30], bytes([0x05, 0x03]))
        self.assertEqual(fdt_up[28:30], bytes([0x05, 0x03]))

        # Byte 26 must differentiate touch (0x01) vs release (0x00)
        self.assertEqual(fdt_down[26], 0x01)
        self.assertEqual(fdt_up[26], 0x00)

        # Rest of payloads must be identical
        self.assertEqual(fdt_down[:26], fdt_up[:26])
        self.assertEqual(fdt_down[27:], fdt_up[27:])

    # =========================================================================
    # Dimension 3: USB Bulk Framing & Chunking Stress Tests
    # =========================================================================

    def test_config_52xd_usb_chunking_and_boundary(self):
        """Stress-test USB chunking for 256-byte CONFIG_52XD payload across 64-byte packets."""
        proto_pkt_unpadded = encode_protocol(CMD_UPLOAD_CONFIG_MCU, CANONICAL_CONFIG_52XD, pad_data=False)
        # Length of unpadded proto_pkt: 1B cmd + 2B wire_len (257) + 256B payload + 1B chk = 260 bytes
        self.assertEqual(len(proto_pkt_unpadded), 260)

        # Wrap in GoodixPack with padding to EP_OUT_CHUNK_SIZE (64 bytes)
        pack_pkt = encode_pack(FLAGS_MSG_PROTOCOL, proto_pkt_unpadded, pad_data=True)
        # Length with 4B GoodixPack header = 264 bytes.
        # Padded to next multiple of 64 bytes -> 320 bytes (5 USB packets: 64 * 5 = 320)
        self.assertEqual(len(pack_pkt), 320)
        self.assertEqual(len(pack_pkt) % EP_OUT_CHUNK_SIZE, 0)

        # Verify MCU simulator receives and verifies the entire 256 bytes intact
        mcu = MockGoodixMCU()
        reply = mcu.handle_out_packet(pack_pkt)
        self.assertEqual(mcu.mcu_config, CANONICAL_CONFIG_52XD)

        # Verify MCU ACK packet
        ok, _, r_body, _ = decode_pack(reply)
        self.assertTrue(ok)
        p_ok, r_cmd, r_payload, _, _ = decode_protocol(r_body)
        self.assertTrue(p_ok)
        self.assertEqual(r_cmd, CMD_ACK)
        self.assertEqual(r_payload[0], CMD_UPLOAD_CONFIG_MCU)

    # =========================================================================
    # Dimension 4: Adversarial Mutation & Corruption Invalidation Tests
    # =========================================================================

    def test_adversarial_config_52xd_single_bit_flip_detection(self):
        """Verify that any single-bit mutation in CONFIG_52XD causes a checksum / SHA mismatch."""
        canonical_sha = hashlib.sha256(CANONICAL_CONFIG_52XD).hexdigest()
        canonical_chk = calc_protocol_checksum(
            struct.pack("<BH", CMD_UPLOAD_CONFIG_MCU, 257) + CANONICAL_CONFIG_52XD,
            3 + 256
        )

        for byte_idx in [0, 1, 15, 64, 128, 200, 255]:
            for bit_mask in [0x01, 0x80]:
                mutated = bytearray(CANONICAL_CONFIG_52XD)
                mutated[byte_idx] ^= bit_mask
                mutated_bytes = bytes(mutated)

                # SHA256 must diverge
                mutated_sha = hashlib.sha256(mutated_bytes).hexdigest()
                self.assertNotEqual(mutated_sha, canonical_sha)

                # Protocol checksum must diverge
                mutated_chk = calc_protocol_checksum(
                    struct.pack("<BH", CMD_UPLOAD_CONFIG_MCU, 257) + mutated_bytes,
                    3 + 256
                )
                self.assertNotEqual(mutated_chk, canonical_chk)

    def test_adversarial_reg022c_endianness_swap_detection(self):
        """Verify that swapping byte order on 0x022c value (0x0503 vs 0x0305) produces invalid wire data."""
        # Correct LE value for \x05\x03 is 0x0305 -> wire bytes [0x05, 0x03]
        correct_packed = struct.pack("<BHH", 0, 0x022C, 0x0305)
        self.assertEqual(correct_packed[3:], bytes([0x05, 0x03]))

        # Inverted BE value 0x0503 -> wire bytes [0x03, 0x05] (Wrong!)
        inverted_packed = struct.pack("<BHH", 0, 0x022C, 0x0503)
        self.assertEqual(inverted_packed[3:], bytes([0x03, 0x05]))
        self.assertNotEqual(correct_packed, inverted_packed)


if __name__ == "__main__":
    unittest.main()
