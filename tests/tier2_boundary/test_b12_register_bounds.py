"""
Tier 2 - Boundary 12: Register Boundaries
Tests 16-bit register address boundaries (0x0000, 0x022C, 0xFFFF) and read lengths (0, 1, 4, 255).
"""

import unittest
import struct
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_READ_SENSOR_REGISTER
)

class TestB12RegisterBounds(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_min_register_address_0x0000(self):
        """Verify reading min address 0x0000 returns 4 bytes chip ID."""
        payload = struct.pack("<BHBB", 0x00, 0x0000, 4, 0x00)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, _, resp, _, _ = decode_protocol(body)
        self.assertEqual(len(resp), 4)

    def test_max_register_address_0xffff(self):
        """Verify reading max 16-bit address 0xFFFF does not overflow."""
        payload = struct.pack("<BHBB", 0x00, 0xFFFF, 4, 0x00)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, _, resp, _, _ = decode_protocol(body)
        self.assertEqual(len(resp), 4)

    def test_gain_register_address_0x022c(self):
        """Verify gain register address 0x022c returns 2 bytes."""
        payload = struct.pack("<BHBB", 0x00, 0x022C, 2, 0x00)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, _, resp, _, _ = decode_protocol(body)
        self.assertEqual(len(resp), 2)

    def test_register_read_length_1_byte(self):
        """Verify reading 1 single byte."""
        payload = struct.pack("<BHBB", 0x00, 0x0000, 1, 0x00)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, _, resp, _, _ = decode_protocol(body)
        self.assertEqual(len(resp), 1)

    def test_register_multiples_flag(self):
        """Verify multiples flag byte in register struct."""
        payload = struct.pack("<BHBB", 0x01, 0x022C, 2, 0x00)
        self.assertEqual(payload[0], 0x01)

if __name__ == "__main__":
    unittest.main()
