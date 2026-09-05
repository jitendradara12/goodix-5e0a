"""
Tier 1 - Feature 23: Multi-Run PAM Verification & Enrollment Reliability
Requirements: Pass 100% of multi-stage enroll (8 stages) and consecutive verification tests on hardware.
"""

import unittest
from tests.repo_paths import repo
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_MCU_SWITCH_TO_FDT_DOWN, CMD_MCU_SWITCH_TO_FDT_UP,
    CMD_MCU_GET_IMAGE, CMD_NOP, CANONICAL_FDT_DOWN, CANONICAL_FDT_UP
)

class TestF23PAMReliability(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_enroll_stage_count_is_8(self):
        """Verify device driver specifies exactly 8 enrollment stages."""
        with open(repo("libfprint-driver", "goodix5e0a.c"), "r") as f:
            content = f.read()
        self.assertIn("nr_enroll_stages = 8", content)

    def test_scan_type_is_press(self):
        """Verify driver scan type is FP_SCAN_TYPE_PRESS."""
        with open(repo("libfprint-driver", "goodix5e0a.c"), "r") as f:
            content = f.read()
        self.assertIn("scan_type = FP_SCAN_TYPE_PRESS", content)

    def test_bz3_threshold_value(self):
        """Verify minutiae matching bz3_threshold is calibrated to 12."""
        with open(repo("libfprint-driver", "goodix5e0a.c"), "r") as f:
            content = f.read()
        self.assertIn("bz3_threshold = 12", content)

    def test_multi_stage_enroll_state_progression(self):
        """Simulate complete 8-stage enrollment workflow with touch and release cycle per stage."""
        for stage in range(1, 9):
            # 1. Touch down
            down_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
            down_reply = self.mcu.handle_out_packet(down_pkt)
            ok, _, body, _ = decode_pack(down_reply)
            _, cmd, payload, _, _ = decode_protocol(body)
            self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_DOWN)
            self.assertEqual(payload[0], 0x01)

            # 2. Capture frame
            img_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"))
            img_reply = self.mcu.handle_out_packet(img_pkt)
            self.assertGreater(len(img_reply), 0)

            # 3. Touch release
            up_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
            up_reply = self.mcu.handle_out_packet(up_pkt)
            ok, _, body, _ = decode_pack(up_reply)
            _, cmd, payload, _, _ = decode_protocol(body)
            self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_UP)
            self.assertEqual(payload[0], 0x00)

    def test_consecutive_verify_session_reinit(self):
        """Simulate 5 back-to-back PAM verify sessions with NOP flush reset between invocations."""
        for session in range(5):
            # NOP flush
            nop_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
            nop_reply = self.mcu.handle_out_packet(nop_pkt)
            self.assertEqual(nop_reply, b"")

            # Touch detection
            down_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
            down_reply = self.mcu.handle_out_packet(down_pkt)
            self.assertGreater(len(down_reply), 0)

            # Release
            up_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
            up_reply = self.mcu.handle_out_packet(up_pkt)
            self.assertGreater(len(up_reply), 0)

if __name__ == "__main__":
    unittest.main()
