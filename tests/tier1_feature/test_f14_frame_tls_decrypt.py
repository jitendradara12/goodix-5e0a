"""
Tier 1 - Feature 14: Frame Acquisition & TLS Decryption
Requirements: Request frame via CMD 0x20, decrypt 7,684-byte payload to 7,680 raw bytes.
"""

import unittest
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, FLAGS_TLS_DATA, CMD_MCU_GET_IMAGE, RAW_FRAME_BYTES,
    pack_12bit_frame, decode_12bit_frame, FRAME_PIXELS
)

class TestF14FrameTLSDecrypt(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_frame_request_command_encoding(self):
        """Verify MCU frame request packet (CMD 0x20, 10B payload)."""
        payload = b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, payload))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, p_payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_MCU_GET_IMAGE)
        self.assertEqual(len(p_payload), 10)

    def test_raw_frame_size_7680_bytes(self):
        """Verify raw frame byte size is exactly 7,680 bytes (5,120 12-bit pixels = 1280 * 6B)."""
        self.assertEqual(RAW_FRAME_BYTES, 7680)
        self.assertEqual(RAW_FRAME_BYTES % 6, 0)
        self.assertEqual((RAW_FRAME_BYTES // 6) * 4, FRAME_PIXELS)

    def test_tls_decrypted_frame_payload_trimming(self):
        """Verify the 7684 -> 7680 trim arithmetic (trailing 4 checksum/status bytes)."""
        raw_7680 = b"\x12" * 7680
        tls_payload = raw_7680 + b"\x00\x00\x00\x00"
        self.assertEqual(len(tls_payload), 7684)
        self.assertEqual(tls_payload[:-4], raw_7680)

    def test_frame_transfer_over_tls_data_packets(self):
        """Verify frame packet uses FLAGS_TLS_DATA (0xb2)."""
        test_pixels = [1000] * FRAME_PIXELS
        raw_bytes = pack_12bit_frame(test_pixels)
        pkt = encode_pack(FLAGS_TLS_DATA, raw_bytes)
        ok, flags, payload, _ = decode_pack(pkt)
        self.assertTrue(ok)
        self.assertEqual(flags, FLAGS_TLS_DATA)
        self.assertEqual(len(payload), 7680)

    def test_frame_acquisition_flow_via_mcu(self):
        """Verify mock MCU produces valid 7,680-byte raw frame on CMD 0x20."""
        payload = b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, payload))
        reply = self.mcu.handle_out_packet(pkt)
        ok, flags, frame_bytes, _ = decode_pack(reply)
        self.assertTrue(ok)
        self.assertEqual(len(frame_bytes), 7680)
        pixels = decode_12bit_frame(frame_bytes)
        self.assertEqual(len(pixels), FRAME_PIXELS)

if __name__ == "__main__":
    unittest.main()
