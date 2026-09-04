"""
Tier 1 - Feature 15: 12-bit Pixel Unpacking & Normalization
Requirements: strip ChicagoH block padding, unpack 6-byte groups to 4 pixels (64x80 = 5120), and normalize.
"""

import unittest
from tests.test_utils import (
    decode_12bit_frame, decode_chicagoh_frame, pack_12bit_frame, squash_frame_linear,
    FRAME_PIXELS, RAW_FRAME_BYTES, FRAME_BLOCKS, FRAME_BLOCK_BYTES,
    FRAME_BLOCK_ACTIVE_BYTES, WIRE_FRAME_BYTES
)

class TestF15UnpackNormalize(unittest.TestCase):

    def test_12bit_nibble_unpacking_formula(self):
        """Verify mathematical equivalence of 6-byte unpacking:
        p0 = ((chunk[0] & 0xf) << 8) + chunk[1]
        p1 = (chunk[3] << 4) + (chunk[0] >> 4)
        p2 = ((chunk[5] & 0xf) << 8) + chunk[2]
        p3 = (chunk[4] << 4) + (chunk[5] >> 4)
        """
        # Test vector: chunk with specific known values
        # Let p0 = 0x123 (291), p1 = 0x456 (1110), p2 = 0x789 (1929), p3 = 0xABC (2748)
        # b0 = (p0>>8 & 0xF) | ((p1 & 0xF) << 4) = 0x1 | 0x60 = 0x61
        # b1 = p0 & 0xFF = 0x23
        # b2 = p2 & 0xFF = 0x89
        # b3 = (p1 >> 4) & 0xFF = 0x45
        # b4 = (p3 >> 4) & 0xFF = 0xAB
        # b5 = (p2>>8 & 0xF) | ((p3 & 0xF) << 4) = 0x7 | 0xC0 = 0xC7
        chunk = bytes([0x61, 0x23, 0x89, 0x45, 0xAB, 0xC7])
        pixels = decode_12bit_frame(chunk)
        self.assertEqual(pixels, [0x123, 0x456, 0x789, 0xABC])

    def test_full_frame_unpack_pixel_count(self):
        """Verify 7,680 raw bytes unpacks to exactly 5,120 pixels."""
        raw_data = bytes([0xAA] * RAW_FRAME_BYTES)
        pixels = decode_12bit_frame(raw_data)
        self.assertEqual(len(pixels), FRAME_PIXELS)

    def test_canonical_frame_strips_each_block_padding(self):
        pixels = [(index * 37) % 4096 for index in range(FRAME_PIXELS)]
        packed = pack_12bit_frame(pixels)
        wire = bytearray()
        for block in range(FRAME_BLOCKS):
            start = block * FRAME_BLOCK_ACTIVE_BYTES
            wire.extend(packed[start : start + FRAME_BLOCK_ACTIVE_BYTES])
            wire.extend(b"\x00" * (FRAME_BLOCK_BYTES - FRAME_BLOCK_ACTIVE_BYTES))
        wire.extend(b"\x12\x34\x56\x78")

        self.assertEqual(len(wire), WIRE_FRAME_BYTES)
        self.assertEqual(decode_chicagoh_frame(bytes(wire)), pixels)

    def test_pixel_values_within_12bit_range(self):
        """Verify all decoded pixel values are strictly in range 0..4095."""
        raw_data = bytes(range(256)) * 30  # 7680 bytes
        pixels = decode_12bit_frame(raw_data)
        for p in pixels:
            self.assertGreaterEqual(p, 0)
            self.assertLessEqual(p, 4095)

    def test_linear_squash_normalization_range(self):
        """Verify linear squashing maps arbitrary 12-bit range to 0..255."""
        test_pixels = [1000 + (i * 2000 // FRAME_PIXELS) for i in range(FRAME_PIXELS)]
        squashed = squash_frame_linear(test_pixels)
        self.assertEqual(len(squashed), FRAME_PIXELS)
        self.assertEqual(min(squashed), 0)
        self.assertEqual(max(squashed), 255)

    def test_uniform_frame_normalization_zero_safe(self):
        """Verify squashing a uniform frame (all identical pixels, max-min=0) avoids division by zero."""
        uniform_pixels = [2048] * FRAME_PIXELS
        squashed = squash_frame_linear(uniform_pixels)
        self.assertEqual(squashed, [0] * FRAME_PIXELS)

if __name__ == "__main__":
    unittest.main()
