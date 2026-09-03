"""
Tier 1 - Feature 3: Read Register & Chip ID
Requirements: Read register 0x0000 (returns 4 bytes chip identifier 27c6:5e0a).
"""

import unittest
import struct
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_READ_SENSOR_REGISTER, CHIP_ID_VAL
)

class TestF03ChipID(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_read_sensor_register_0x0000_encoding(self):
        """Verify register read payload structure (multiples:1B, addr:2B LE, len:1B, pad:1B)."""
        # struct { multiples:8, addr:16, len:8, pad:8 }
        payload = struct.pack("<BHBB", 0x00, 0x0000, 4, 0x00)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, payload))
        ok, flags, body, chk_ok = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, p_payload, p_chk_ok, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_READ_SENSOR_REGISTER)
        self.assertEqual(len(p_payload), 5)

    def test_chip_id_4byte_response_payload(self):
        """Verify response from register 0x0000 read is exactly 4 bytes."""
        payload = struct.pack("<BHBB", 0x00, 0x0000, 4, 0x00)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, flags, body, _ = decode_pack(reply)
        p_ok, cmd, resp, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(len(resp), 4)

    def test_chip_id_matches_goodix_specification(self):
        """Verify returned chip ID corresponds to hardware VID/PID bytes."""
        payload = struct.pack("<BHBB", 0x00, 0x0000, 4, 0x00)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, flags, body, _ = decode_pack(reply)
        _, _, resp, _, _ = decode_protocol(body)
        self.assertEqual(resp, CHIP_ID_VAL)

    def test_read_register_with_null_checksum(self):
        """Verify protocol decoder accepts null checksum (0x88) on register reads."""
        payload = struct.pack("<BHBB", 0x00, 0x0000, 4, 0x00)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, payload, calc_checksum=False))
        ok, flags, body, _ = decode_pack(pkt)
        p_ok, cmd, p_payload, p_chk_ok, is_null = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertTrue(is_null)

    def test_arbitrary_register_read(self):
        """Verify MCU simulator handles arbitrary register reads dynamically."""
        self.mcu.registers[0x1234] = bytes([0xDE, 0xAD, 0xBE, 0xEF])
        payload = struct.pack("<BHBB", 0x00, 0x1234, 4, 0x00)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, flags, body, _ = decode_pack(reply)
        _, _, resp, _, _ = decode_protocol(body)
        self.assertEqual(resp, bytes([0xDE, 0xAD, 0xBE, 0xEF]))

if __name__ == "__main__":
    unittest.main()
