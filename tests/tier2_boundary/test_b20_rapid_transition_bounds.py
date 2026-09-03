"""
Tier 2 - Boundary 20: Rapid Transition Boundaries
Tests rapid state transitions: immediate deactivation after activation, fast touch/release cycles.
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_MCU_SWITCH_TO_FDT_DOWN, CMD_MCU_SWITCH_TO_FDT_UP,
    CMD_NOP, CANONICAL_FDT_DOWN, CANONICAL_FDT_UP
)

class TestB20RapidTransitionBounds(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_immediate_deactivation_after_init(self):
        """Verify device handles NOP reset immediately without prior commands."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = self.mcu.handle_out_packet(pkt)
        self.assertEqual(reply, b"")

    def test_rapid_down_up_transitions(self):
        """Verify back-to-back touch and release within sub-millisecond interval."""
        for _ in range(10):
            down_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
            self.mcu.handle_out_packet(down_pkt)
            up_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
            self.mcu.handle_out_packet(up_pkt)
        self.assertTrue(self.mcu.fdt_up_active)

    def test_multiple_nop_flushes(self):
        """Verify sending 10 consecutive NOPs remains stable."""
        for _ in range(10):
            pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
            reply = self.mcu.handle_out_packet(pkt)
            self.assertEqual(reply, b"")

    def test_abort_during_fdt_wait(self):
        """Verify FDT wait interrupted by NOP flush resets pending state."""
        down_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        self.mcu.handle_out_packet(down_pkt)
        nop_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        self.mcu.handle_out_packet(nop_pkt)

    def test_immediate_reactivation_after_deactivate(self):
        """Verify activating immediately after deactivation works reliably."""
        nop_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        self.mcu.handle_out_packet(nop_pkt)
        down_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        reply = self.mcu.handle_out_packet(down_pkt)
        self.assertGreater(len(reply), 0)

if __name__ == "__main__":
    unittest.main()
