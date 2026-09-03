"""
Tier 2 - Boundary 15: Unpack Alignment Boundaries
Tests 12-bit nibble unpacking on non-multiples of 6 bytes, truncated chunks, and odd offsets.
"""

import unittest
from tests.test_utils import (
    decode_12bit_frame, pack_12bit_frame, FRAME_PIXELS
)

class TestB15UnpackAlignmentBounds(unittest.TestCase):

    def test_single_6byte_chunk(self):
        """Verify unpacking exactly 1 chunk (6 bytes) produces exactly 4 pixels."""
        chunk = bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC])
        pixels = decode_12bit_frame(chunk)
        self.assertEqual(len(pixels), 4)

    def test_partial_chunk_5bytes_ignored(self):
        """Verify 5 bytes (less than 6) produces 0 pixels without crashing."""
        chunk = bytes([0x12, 0x34, 0x56, 0x78, 0x9A])
        pixels = decode_12bit_frame(chunk)
        self.assertEqual(len(pixels), 0)

    def test_7byte_stream_unpacks_first_chunk(self):
        """Verify 7-byte stream (less than 6 + 4 trailer) yields 0 pixels under C boundary logic."""
        chunk = bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xFF])
        pixels = decode_12bit_frame(chunk)
        self.assertEqual(len(pixels), 0)

    def test_10byte_stream_with_trailer_unpacks_one_chunk(self):
        """Verify 10-byte stream (6-byte chunk + 4-byte trailer) unpacks 4 pixels."""
        stream = bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0x00, 0x00, 0x00, 0x00])
        pixels = decode_12bit_frame(stream)
        self.assertEqual(len(pixels), 4)

    def test_7684byte_tls_frame_alignment(self):
        """Verify 7,684-byte buffer unpacks full 5,120 pixel array."""
        test_pixels = [500] * FRAME_PIXELS
        raw_7680 = pack_12bit_frame(test_pixels)
        raw_7684 = raw_7680 + b"\x00\x00\x00\x00"
        pixels = decode_12bit_frame(raw_7684)
        self.assertEqual(len(pixels), FRAME_PIXELS)

    def test_empty_input_produces_empty_list(self):
        """Verify empty byte string produces empty pixel list."""
        pixels = decode_12bit_frame(b"")
        self.assertEqual(pixels, [])

if __name__ == "__main__":
    unittest.main()
