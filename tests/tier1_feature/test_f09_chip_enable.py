"""
Tier 1 - Feature 9: Chip Enable & Driver State
Requirements: Enable analog frontend via CMD 0x96 and set driver state.
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_ENABLE_CHIP, CMD_ACK
)

class TestF09ChipEnable(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_chip_enable_command_encoding(self):
        """Verify enable chip command (CMD 0x96, enable=0x01)."""
        payload = bytes([0x01, 0x00])
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ENABLE_CHIP, payload))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, p_payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_ENABLE_CHIP)
        self.assertEqual(p_payload[0], 0x01)

    def test_chip_disable_command_encoding(self):
        """Verify disable chip command (CMD 0x96, enable=0x00)."""
        payload = bytes([0x00, 0x00])
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ENABLE_CHIP, payload))
        self.mcu.handle_out_packet(pkt)
        self.assertFalse(self.mcu.chip_enabled)

    def test_chip_enable_ack_response(self):
        """Verify MCU responds with ACK upon receiving CMD 0x96."""
        payload = bytes([0x01, 0x00])
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ENABLE_CHIP, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, cmd, p_payload, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_ACK)
        self.assertEqual(p_payload[0], CMD_ENABLE_CHIP)

    def test_mcu_state_reflection(self):
        """Verify internal simulator state reflects chip enable flag."""
        self.assertFalse(self.mcu.chip_enabled)
        payload = bytes([0x01, 0x00])
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ENABLE_CHIP, payload))
        self.mcu.handle_out_packet(pkt)
        self.assertTrue(self.mcu.chip_enabled)

    def test_repeated_chip_enable_idempotency(self):
        """Verify repeatedly enabling chip remains stable and enabled."""
        payload = bytes([0x01, 0x00])
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ENABLE_CHIP, payload))
        self.mcu.handle_out_packet(pkt)
        self.mcu.handle_out_packet(pkt)
        self.assertTrue(self.mcu.chip_enabled)

if __name__ == "__main__":
    unittest.main()
