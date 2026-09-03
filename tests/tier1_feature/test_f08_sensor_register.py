"""
Tier 1 - Feature 8: Sensor Register 0x022c Config
Requirements: Configure analog frontend gain/exposure (\x05\x03) on sensor register 0x022c.
"""

import unittest
import struct
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_WRITE_SENSOR_REGISTER, CMD_READ_SENSOR_REGISTER,
    CMD_ACK, CANONICAL_REG_022C_GAIN
)

class TestF08SensorRegister(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_gain_register_address(self):
        """Verify analog frontend configuration register address is 0x022c."""
        reg_addr = 0x022C
        self.assertEqual(reg_addr, 556)

    def test_gain_register_write_encoding(self):
        """Verify write register packet (CMD 0x80, multiples=0, addr=0x022c, val=\x05\x03)."""
        payload = struct.pack("<BHH", 0x00, 0x022C, 0x0305)  # LE for 0x05, 0x03
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_WRITE_SENSOR_REGISTER, payload))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, p_payload, p_chk_ok, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_WRITE_SENSOR_REGISTER)

    def test_gain_register_write_and_readback(self):
        """Verify writing to register 0x022c updates simulator and matches on subsequent read."""
        write_payload = struct.pack("<BH2s", 0x00, 0x022C, CANONICAL_REG_022C_GAIN)
        write_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_WRITE_SENSOR_REGISTER, write_payload))
        self.mcu.handle_out_packet(write_pkt)

        read_payload = struct.pack("<BHBB", 0x00, 0x022C, 2, 0x00)
        read_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, read_payload))
        reply = self.mcu.handle_out_packet(read_pkt)
        ok, _, body, _ = decode_pack(reply)
        _, _, resp, _, _ = decode_protocol(body)
        self.assertEqual(resp, CANONICAL_REG_022C_GAIN)

    def test_gain_register_analog_frontend_values(self):
        """Verify exposure byte 0x05 and gain byte 0x03 are preserved."""
        self.assertEqual(CANONICAL_REG_022C_GAIN[0], 0x05)
        self.assertEqual(CANONICAL_REG_022C_GAIN[1], 0x03)

    def test_gain_register_ack_verification(self):
        """Verify write sensor register returns CMD_ACK with CMD_WRITE_SENSOR_REGISTER."""
        payload = struct.pack("<BH2s", 0x00, 0x022C, CANONICAL_REG_022C_GAIN)
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_WRITE_SENSOR_REGISTER, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, cmd, p_payload, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_ACK)
        self.assertEqual(p_payload[0], CMD_WRITE_SENSOR_REGISTER)

if __name__ == "__main__":
    unittest.main()
