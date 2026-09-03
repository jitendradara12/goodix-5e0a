"""
Tier 1 - Feature 1: USB Interface & Endpoint Configuration
Requirements: Claim interface 0, EP 0x01 OUT (64B chunked), EP 0x83 IN (64KB buffer)
"""

import unittest
from tests.test_utils import (
    VENDOR_ID, PRODUCT_ID, INTERFACE_NUM, EP_OUT, EP_IN,
    EP_OUT_CHUNK_SIZE, EP_IN_MAX_BUF_SIZE,
    encode_pack, encode_protocol, FLAGS_MSG_PROTOCOL, CMD_NOP
)

class TestF01USBEndpoints(unittest.TestCase):

    def test_usb_vendor_and_product_id_match(self):
        """Verify driver targets exact Goodix 27c6:5e0a hardware IDs."""
        self.assertEqual(VENDOR_ID, 0x27c6)
        self.assertEqual(PRODUCT_ID, 0x5e0a)

    def test_usb_endpoint_in_address_and_size(self):
        """Verify EP IN address is 0x83 with 64KB max buffer allocation."""
        self.assertEqual(EP_IN, 0x83)
        self.assertEqual(EP_IN_MAX_BUF_SIZE, 65536)

    def test_usb_endpoint_out_address_and_chunking(self):
        """Verify EP OUT address is 0x01 with 64-byte chunk limit."""
        self.assertEqual(EP_OUT, 0x01)
        self.assertEqual(EP_OUT_CHUNK_SIZE, 64)

    def test_usb_interface_zero_claimed(self):
        """Verify interface 0 is the primary USB interface."""
        self.assertEqual(INTERFACE_NUM, 0)

    def test_usb_packet_chunk_padding_alignment(self):
        """Verify USB out framing properly pads all payload lengths to 64-byte blocks."""
        for payload_len in [1, 10, 63, 64, 65, 127, 128]:
            payload = b"\xaa" * payload_len
            encoded = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, payload, pad_data=True), pad_data=True)
            self.assertEqual(len(encoded) % EP_OUT_CHUNK_SIZE, 0,
                             f"Encoded length {len(encoded)} not aligned to 64 bytes for payload len {payload_len}")

if __name__ == "__main__":
    unittest.main()
