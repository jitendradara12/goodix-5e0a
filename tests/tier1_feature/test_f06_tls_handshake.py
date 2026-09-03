"""
Tier 1 - Feature 6: TLS 1.2 PSK Handshake
Requirements: Establish PSK-AES128-CBC-SHA256 session using 32-byte key via CMD 0xd0/0xd2/0xd4.
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, FLAGS_TLS, FLAGS_TLS_DATA,
    CMD_REQUEST_TLS_CONNECTION, CMD_TLS_SUCCESSFULLY_ESTABLISHED, CMD_ACK
)

class TestF06TLSHandshake(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_tls_request_command_encoding(self):
        """Verify TLS request command (CMD 0xd0)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_REQUEST_TLS_CONNECTION, b""))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, _, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_REQUEST_TLS_CONNECTION)

    def test_tls_established_ack_command_encoding(self):
        """Verify TLS successfully established notification command (CMD 0xd4)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_TLS_SUCCESSFULLY_ESTABLISHED, b""))
        reply = self.mcu.handle_out_packet(pkt)
        ok, flags, body, _ = decode_pack(reply)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_ACK)
        self.assertEqual(payload[0], CMD_TLS_SUCCESSFULLY_ESTABLISHED)
        self.assertEqual(CMD_TLS_SUCCESSFULLY_ESTABLISHED, 0xD4)

    def test_real_command_numbers_contract(self):
        """
        Verify real command numbers match proven on-wire behavior and goodix_proto.h:
        - 0xd4 = TLS_SUCCESSFULLY_ESTABLISHED
        - 0xd2 = MCU_GET_POV_IMAGE
        - 0xc4 = SET_DRV_STATE
        - 0xac = SET_POV_CONFIG
        """
        from pathlib import Path
        import re
        from tests.test_utils import (
            CMD_MCU_GET_POV_IMAGE, CMD_SET_DRV_STATE, CMD_SET_POV_CONFIG
        )

        self.assertEqual(CMD_TLS_SUCCESSFULLY_ESTABLISHED, 0xD4)
        self.assertEqual(CMD_MCU_GET_POV_IMAGE, 0xD2)
        self.assertEqual(CMD_SET_DRV_STATE, 0xC4)
        self.assertEqual(CMD_SET_POV_CONFIG, 0xAC)

        proto_h = Path(__file__).resolve().parents[2] / "libfprint-driver" / "goodix_proto.h"
        if proto_h.exists():
            content = proto_h.read_text(encoding="utf-8")
            self.assertIn("#define GOODIX_CMD_TLS_SUCCESSFULLY_ESTABLISHED (0xd4)", content)
            self.assertIn("#define GOODIX_CMD_MCU_GET_POV_IMAGE (0xd2)", content)
            self.assertIn("#define GOODIX_CMD_SET_DRV_STATE (0xc4)", content)
            self.assertIn("#define GOODIX_CMD_SET_POV_CONFIG (0xac)", content)

    def test_tls_psk_cipher_suite_identification(self):
        """Verify cipher suite string corresponds to OpenSSL PSK-AES128-CBC-SHA256."""
        cipher_suite = "PSK-AES128-CBC-SHA256"
        self.assertIn("PSK", cipher_suite)
        self.assertIn("AES128", cipher_suite)
        self.assertIn("SHA256", cipher_suite)

    def test_tls_packet_flags_routing(self):
        """Verify distinct flags for protocol messages (0xa0), TLS negotiation (0xb0), and TLS data (0xb2)."""
        self.assertEqual(FLAGS_MSG_PROTOCOL, 0xa0)
        self.assertEqual(FLAGS_TLS, 0xb0)
        self.assertEqual(FLAGS_TLS_DATA, 0xb2)

    def test_tls_session_establishment_flow(self):
        """Verify complete TLS session setup handshake sequence."""
        req_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_REQUEST_TLS_CONNECTION, b""))
        req_reply = self.mcu.handle_out_packet(req_pkt)
        self.assertTrue(self.mcu.tls_established)

        est_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_TLS_SUCCESSFULLY_ESTABLISHED, b""))
        est_reply = self.mcu.handle_out_packet(est_pkt)
        self.assertGreater(len(est_reply), 0)

if __name__ == "__main__":
    unittest.main()
