"""
Tier 1 - Feature 12: Hardware FDT UP Release Detection
Requirements: Mock 39-byte UP fixture via CMD 0x34 (byte 26=0x00 flag).
Fixture only: frozen hardware uses the 35-byte table (goodix5e0a.h:100-104).
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
        """Verify mock FDT UP fixture is exactly 39 bytes (harness shape, not hardware)."""
        self.assertEqual(len(CANONICAL_FDT_UP), 39)

    def test_fdt_up_release_indicator_byte_26(self):
        """Verify mock fixture byte index 26 is 0x00 (Release flag in 39B layout)."""
        self.assertEqual(CANONICAL_FDT_UP[26], 0x00)

    def test_fdt_up_command_encoding(self):
        """Verify FDT UP command packet (CMD 0x34) framing of the 39B mock payload."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_UP)
        self.assertEqual(len(payload), 39)

    def test_fdt_up_blocking_interrupt_behavior(self):
        """Verify mock answers FDT UP with its canned release reply (no hardware/blocking involved)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, cmd, payload, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_UP)
        self.assertEqual(payload[0], 0x00)  # Release signal
        self.assertTrue(self.mcu.fdt_up_active)

    def test_fdt_down_vs_up_single_bit_differential(self):
        """Verify mock DOWN and UP fixtures are identical except for byte 26 (harness shape)."""
        self.assertEqual(len(CANONICAL_FDT_DOWN), len(CANONICAL_FDT_UP))
        differences = [i for i in range(len(CANONICAL_FDT_DOWN)) if CANONICAL_FDT_DOWN[i] != CANONICAL_FDT_UP[i]]
        self.assertEqual(differences, [26], f"Unexpected differences between FDT DOWN and UP at indices {differences}")
        self.assertEqual(CANONICAL_FDT_DOWN[26], 0x01)
        self.assertEqual(CANONICAL_FDT_UP[26], 0x00)

if __name__ == "__main__":
    unittest.main()
