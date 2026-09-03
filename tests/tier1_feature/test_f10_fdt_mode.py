"""
Tier 1 - Feature 10: Hardware FDT Mode Configuration
Requirements: Configure FDT operating mode via CMD 0x36 (27-byte payload).
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_MCU_SWITCH_TO_FDT_MODE, CMD_ACK, CANONICAL_FDT_MODE
)

class TestF10FDTMode(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_fdt_mode_payload_length(self):
        """Verify FDT mode configuration payload is exactly 27 bytes."""
        self.assertEqual(len(CANONICAL_FDT_MODE), 27)

    def test_fdt_mode_header_bytes(self):
        """Verify FDT mode header sequence (0x0d, 0x01, 0x27, 0x01, 0x21, 0x01, 0x27, 0x01, 0x23, 0x01)."""
        expected_header = bytes([0x0D, 0x01, 0x27, 0x01, 0x21, 0x01, 0x27, 0x01, 0x23, 0x01])
        self.assertEqual(CANONICAL_FDT_MODE[:10], expected_header)

    def test_fdt_mode_command_encoding(self):
        """Verify FDT mode command packet (CMD 0x36)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_MODE)
        self.assertEqual(len(payload), 27)

    def test_fdt_mode_mcu_receipt(self):
        """Verify MCU receives and stores the 27-byte FDT mode payload."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE))
        self.mcu.handle_out_packet(pkt)
        self.assertEqual(self.mcu.fdt_mode, CANONICAL_FDT_MODE)

    def test_fdt_mode_ack_reply(self):
        """Verify MCU returns ACK for CMD 0x36."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, cmd, payload, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_ACK)
        self.assertEqual(payload[0], CMD_MCU_SWITCH_TO_FDT_MODE)

if __name__ == "__main__":
    unittest.main()
