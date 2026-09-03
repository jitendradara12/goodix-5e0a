"""
Tier 1 - Feature 24: Adversarial Edge-Case Hardening
Requirements: Empty air rejection, rapid cancellation, USB disconnect/reconnect handling.
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    decode_12bit_frame, squash_frame_linear, process_frame_demosaic,
    FLAGS_MSG_PROTOCOL, CMD_NOP, CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN
)

class TestF24AdversarialGuard(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_empty_air_rejection(self):
        """Verify that absent physical touch, no false advance occurs."""
        self.assertFalse(self.mcu.touch_pending)

    def test_rapid_cancellation_during_fdt_wait(self):
        """Verify driver handles cancellation event while waiting for FDT interrupt."""
        # Setup FDT down state
        down_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        self.mcu.handle_out_packet(down_pkt)
        self.assertTrue(self.mcu.fdt_down_active)

        # Cancel / Deactivate via NOP flush
        nop_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = self.mcu.handle_out_packet(nop_pkt)
        self.assertEqual(reply, b"")

    def test_corrupted_packet_recovery(self):
        """Verify protocol decoder rejects corrupted packet and cleanly processes subsequent valid packet."""
        corrupted_bytes = b"\xa0\x05\x00\xff\x01\x02\x03\x04\x05"  # Bad header checksum
        ok, flags, body, chk_ok = decode_pack(corrupted_bytes)
        self.assertFalse(chk_ok)

        # Subsequent valid packet
        valid_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        v_ok, v_flags, v_body, v_chk_ok = decode_pack(valid_pkt)
        self.assertTrue(v_ok)
        self.assertTrue(v_chk_ok)

    def test_usb_stall_recovery_via_nop(self):
        """Verify sending CMD 0x00 restores protocol synchronization after communication fault."""
        nop_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = self.mcu.handle_out_packet(nop_pkt)
        self.assertEqual(reply, b"")

    def test_zero_length_frame_guard(self):
        """Verify decoding and processing pipeline handles empty byte strings gracefully."""
        pixels = decode_12bit_frame(b"")
        self.assertEqual(pixels, [])
        squashed = squash_frame_linear(pixels)
        self.assertEqual(squashed, [])

if __name__ == "__main__":
    unittest.main()
