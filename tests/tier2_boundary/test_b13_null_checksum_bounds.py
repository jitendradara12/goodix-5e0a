"""
Tier 2 - Boundary 13: Null Checksum Boundaries
Tests decoding of packets with 0x88 null checksum vs normal calculated checksums.
"""

import unittest
from tests.test_utils import (
    encode_protocol, decode_protocol, CMD_NOP, NULL_CHECKSUM
)

class TestB13NullChecksumBounds(unittest.TestCase):

    def test_null_checksum_byte_presence(self):
        """Verify calc_checksum=False sets trailer byte to 0x88."""
        pkt = encode_protocol(CMD_NOP, b"\x01\x02\x03", calc_checksum=False, pad_data=False)
        self.assertEqual(pkt[-1], NULL_CHECKSUM)

    def test_null_checksum_decoder_flag(self):
        """Verify decoder flags valid_null_checksum as True."""
        pkt = encode_protocol(CMD_NOP, b"\x01\x02\x03", calc_checksum=False, pad_data=False)
        ok, cmd, payload, valid_chk, is_null = decode_protocol(pkt)
        self.assertTrue(ok)
        self.assertTrue(is_null)

    def test_calculated_checksum_not_null(self):
        """Verify standard packets do not report is_null unless coincidentally 0x88."""
        pkt = encode_protocol(CMD_NOP, b"", calc_checksum=True, pad_data=False)
        ok, cmd, payload, valid_chk, is_null = decode_protocol(pkt)
        self.assertTrue(ok)
        self.assertTrue(valid_chk)
        self.assertFalse(is_null)

    def test_corrupted_checksum_byte(self):
        """Verify corrupted checksum byte is flagged as invalid."""
        pkt = bytearray(encode_protocol(CMD_NOP, b"\x01\x02\x03", calc_checksum=True, pad_data=False))
        pkt[-1] = (pkt[-1] + 1) & 0xFF  # Corrupt
        ok, cmd, payload, valid_chk, is_null = decode_protocol(bytes(pkt))
        self.assertFalse(valid_chk)
        self.assertFalse(is_null)

    def test_null_checksum_with_empty_payload(self):
        """Verify 0-byte payload with null checksum."""
        pkt = encode_protocol(CMD_NOP, b"", calc_checksum=False, pad_data=False)
        ok, cmd, payload, valid_chk, is_null = decode_protocol(pkt)
        self.assertTrue(ok)
        self.assertTrue(is_null)

if __name__ == "__main__":
    unittest.main()
