"""
Tier 2 - Boundary 21: Corrupted Headers
Tests handling of corrupted header flags, inverted checksums, and garbage bytes.
"""

import unittest
from tests.test_utils import (
    decode_pack, decode_protocol, encode_pack, encode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_NOP
)

class TestB21CorruptedHeaders(unittest.TestCase):

    def test_unknown_pack_flag(self):
        """Verify decoder flags valid_checksum=False when header checksum byte does not match."""
        # Flag=0x00, len=0, but chk=0xFF
        bad_pack = b"\x00\x00\x00\xff"
        ok, flags, payload, valid_chk = decode_pack(bad_pack)
        self.assertTrue(ok)
        self.assertFalse(valid_chk)

    def test_corrupted_protocol_cmd(self):
        """Verify protocol checksum detects bitflip in cmd byte."""
        pkt = bytearray(encode_protocol(CMD_NOP, b"\x01\x02\x03", calc_checksum=True, pad_data=False))
        pkt[0] = 0xFE  # Bitflip command byte
        ok, cmd, payload, valid_chk, is_null = decode_protocol(bytes(pkt))
        self.assertTrue(ok)
        self.assertFalse(valid_chk)

    def test_corrupted_protocol_length(self):
        """Verify protocol checksum detects corrupted length byte."""
        pkt = bytearray(encode_protocol(CMD_NOP, b"\x01\x02\x03", calc_checksum=True, pad_data=False))
        pkt[1] = 0x50  # Corrupt length
        ok, _, _, _, _ = decode_protocol(bytes(pkt))
        # Will fail length check or checksum check
        self.assertFalse(ok)

    def test_garbage_stream_decoding(self):
        """Verify completely random garbage bytes are rejected without crashing."""
        garbage = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0xBA, 0xBE])
        ok, _, _, valid_chk = decode_pack(garbage)
        # Checksum check will fail
        self.assertFalse(valid_chk)

    def test_all_zeros_header_checksum_mismatch(self):
        """Verify header 0x00, 0x00, 0x00 with chk=0x01 fails."""
        bad_hdr = b"\x00\x00\x00\x01"
        ok, _, _, valid_chk = decode_pack(bad_hdr)
        self.assertFalse(valid_chk)

if __name__ == "__main__":
    unittest.main()
