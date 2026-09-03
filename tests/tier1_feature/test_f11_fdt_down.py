"""
Tier 1 - Feature 11: Hardware FDT DOWN Touch Detection
Requirements: Asynchronous blocking capacitive touch interrupt via CMD 0x32 (39-byte payload, byte 26=0x01).
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN
)

class TestF11FDTDown(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_fdt_down_payload_length(self):
        """Verify FDT DOWN payload is exactly 39 bytes."""
        self.assertEqual(len(CANONICAL_FDT_DOWN), 39)

    def test_fdt_down_touch_indicator_byte_26(self):
        """Verify byte index 26 is 0x01 (Touch Enable / Down indicator)."""
        self.assertEqual(CANONICAL_FDT_DOWN[26], 0x01)

    def test_fdt_down_command_encoding(self):
        """Verify FDT DOWN command packet (CMD 0x32, 39B payload)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_DOWN)
        self.assertEqual(len(payload), 39)

    def test_fdt_down_blocking_interrupt_behavior(self):
        """Verify FDT DOWN returns interrupt reply upon physical touch."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, cmd, payload, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_DOWN)
        self.assertEqual(payload[0], 0x01)  # Touch signal
        self.assertTrue(self.mcu.fdt_down_active)

    def test_fdt_down_gain_parameters_embedded(self):
        """Verify exposure (0x05) and gain (0x03) values are embedded at bytes 28-29."""
        self.assertEqual(CANONICAL_FDT_DOWN[28], 0x05)
        self.assertEqual(CANONICAL_FDT_DOWN[29], 0x03)

if __name__ == "__main__":
    unittest.main()
