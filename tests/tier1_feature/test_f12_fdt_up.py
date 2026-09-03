"""
Tier 1 - Feature 12: Hardware FDT UP Release Detection
Requirements: Asynchronous blocking capacitive release interrupt via CMD 0x34 (39-byte payload, byte 26=0x00).
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP, CANONICAL_FDT_DOWN
)

class TestF12FDTUp(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_fdt_up_payload_length(self):
        """Verify FDT UP payload is exactly 39 bytes."""
        self.assertEqual(len(CANONICAL_FDT_UP), 39)

    def test_fdt_up_release_indicator_byte_26(self):
        """Verify byte index 26 is 0x00 (Finger Release indicator)."""
        self.assertEqual(CANONICAL_FDT_UP[26], 0x00)

    def test_fdt_up_command_encoding(self):
        """Verify FDT UP command packet (CMD 0x34, 39B payload)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_UP)
        self.assertEqual(len(payload), 39)

    def test_fdt_up_blocking_interrupt_behavior(self):
        """Verify FDT UP returns release notification."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, cmd, payload, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_UP)
        self.assertEqual(payload[0], 0x00)  # Release signal
        self.assertTrue(self.mcu.fdt_up_active)

    def test_fdt_down_vs_up_single_bit_differential(self):
        """Verify FDT DOWN and FDT UP tables are identical except for byte 26."""
        self.assertEqual(len(CANONICAL_FDT_DOWN), len(CANONICAL_FDT_UP))
        differences = [i for i in range(len(CANONICAL_FDT_DOWN)) if CANONICAL_FDT_DOWN[i] != CANONICAL_FDT_UP[i]]
        self.assertEqual(differences, [26], f"Unexpected differences between FDT DOWN and UP at indices {differences}")
        self.assertEqual(CANONICAL_FDT_DOWN[26], 0x01)
        self.assertEqual(CANONICAL_FDT_UP[26], 0x00)

if __name__ == "__main__":
    unittest.main()
