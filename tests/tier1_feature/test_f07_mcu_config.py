"""
Tier 1 - Feature 7: MCU Config Upload (256B)
Requirements: Upload 256-byte CONFIG_52XD payload via CMD 0x90.
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_UPLOAD_CONFIG_MCU, CMD_ACK, CANONICAL_CONFIG_52XD
)

class TestF07MCUConfig(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_mcu_config_payload_length(self):
        """Verify CONFIG_52XD payload length is exactly 256 bytes."""
        self.assertEqual(len(CANONICAL_CONFIG_52XD), 256)

    def test_mcu_config_upload_command_encoding(self):
        """Verify MCU config upload packet structure (CMD 0x90, 256B payload)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_UPLOAD_CONFIG_MCU, CANONICAL_CONFIG_52XD))
        ok, flags, body, chk_ok = decode_pack(pkt)
        self.assertTrue(ok)
        self.assertTrue(chk_ok)
        p_ok, cmd, payload, p_chk_ok, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_UPLOAD_CONFIG_MCU)
        self.assertEqual(len(payload), 256)

    def test_mcu_config_payload_integrity(self):
        """Verify uploaded config payload matches byte-for-byte with ChicagoH 52xD configuration table."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_UPLOAD_CONFIG_MCU, CANONICAL_CONFIG_52XD))
        reply = self.mcu.handle_out_packet(pkt)
        self.assertEqual(self.mcu.mcu_config, CANONICAL_CONFIG_52XD)

    def test_mcu_config_upload_ack_response(self):
        """Verify MCU returns ACK for CMD 0x90 upload."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_UPLOAD_CONFIG_MCU, CANONICAL_CONFIG_52XD))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, cmd, payload, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_ACK)
        self.assertEqual(payload[0], CMD_UPLOAD_CONFIG_MCU)

    def test_mcu_config_header_and_tail_markers(self):
        """Verify specific header (0x70, 0x11, 0x60, 0x71) and tail bytes (0x58, 0x20, 0xc5, 0x0e)."""
        self.assertEqual(CANONICAL_CONFIG_52XD[:4], bytes([0x70, 0x11, 0x60, 0x71]))
        self.assertEqual(CANONICAL_CONFIG_52XD[-4:], bytes([0x58, 0x20, 0xc5, 0x0e]))

if __name__ == "__main__":
    unittest.main()
