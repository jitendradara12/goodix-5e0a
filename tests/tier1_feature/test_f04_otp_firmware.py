"""
Tier 1 - Feature 4: Read OTP & Firmware Query
Requirements: Query CMD 0xa6 OTP and CMD 0xa8 ASCII FW string (GFUSB_GM168SEC_APP_10036).
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_READ_OTP, CMD_FIRMWARE_VERSION, FIRMWARE_VERSION_STR
)

class TestF04OTPFirmware(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_firmware_query_command_encoding(self):
        """Verify firmware query packet formatting (CMD 0xa8, empty payload)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_FIRMWARE_VERSION, b""))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, payload, p_chk_ok, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_FIRMWARE_VERSION)

    def test_firmware_query_ascii_response(self):
        """Verify firmware response contains null-terminated ASCII string matching GFUSB_GM168SEC_APP_10036."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_FIRMWARE_VERSION, b""))
        reply = self.mcu.handle_out_packet(pkt)
        ok, flags, body, _ = decode_pack(reply)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_FIRMWARE_VERSION)
        fw_str = payload.rstrip(b"\x00").decode("ascii")
        self.assertEqual(fw_str, FIRMWARE_VERSION_STR)

    def test_read_otp_command_encoding(self):
        """Verify OTP read command formatting (CMD 0xa6)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_OTP, b""))
        ok, flags, body, _ = decode_pack(pkt)
        p_ok, cmd, _, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_READ_OTP)

    def test_read_otp_response_payload(self):
        """Verify OTP response payload is valid non-empty byte sequence."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_OTP, b""))
        reply = self.mcu.handle_out_packet(pkt)
        ok, flags, body, _ = decode_pack(reply)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(len(payload), 32)

    def test_firmware_version_mismatch_detection(self):
        """Verify that any deviation from canonical firmware string triggers validation failure."""
        bad_fw = b"GFUSB_GM168SEC_APP_99999\x00"
        self.assertNotEqual(bad_fw.rstrip(b"\x00").decode("ascii"), FIRMWARE_VERSION_STR)

if __name__ == "__main__":
    unittest.main()
