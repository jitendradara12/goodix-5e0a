"""
Tier 1 - Feature 11: Hardware FDT DOWN Touch Detection
Requirements: Mock 39-byte DOWN fixture via CMD 0x32 (byte 26=0x01 flag).
Fixture only: frozen hardware uses 35-byte tables (goodix5e0a.h:82-96).
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
        """Verify mock FDT DOWN fixture is exactly 39 bytes (harness shape, not hardware)."""
        self.assertEqual(len(CANONICAL_FDT_DOWN), 39)

    def test_fdt_down_touch_indicator_byte_26(self):
        """Verify mock fixture byte index 26 is 0x01 (Down flag in 39B layout)."""
        self.assertEqual(CANONICAL_FDT_DOWN[26], 0x01)

    def test_fdt_down_command_encoding(self):
        """Verify FDT DOWN command packet (CMD 0x32) framing of the 39B mock payload."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_DOWN)
        self.assertEqual(len(payload), 39)

    def test_fdt_down_blocking_interrupt_behavior(self):
        """Verify mock answers FDT DOWN with its canned touch reply (no hardware/blocking involved)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, cmd, payload, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_DOWN)
        self.assertEqual(payload[0], 0x01)  # Touch signal
        self.assertTrue(self.mcu.fdt_down_active)

    def test_fdt_down_gain_parameters_embedded(self):
        """Verify mock fixture bytes 28-29 are 0x05/0x03 (fixture only, not the frozen header)."""
        self.assertEqual(CANONICAL_FDT_DOWN[28], 0x05)
        self.assertEqual(CANONICAL_FDT_DOWN[29], 0x03)

if __name__ == "__main__":
    unittest.main()
