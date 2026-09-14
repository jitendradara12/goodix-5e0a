"""
Tier 5 Adversarial Stress Test: Wire-to-Pixel Decoding Equivalence
Direct block unpack (new) vs. 2-step memcpy unpack (old).
Verifies 100% bitwise equivalence on synthetic wire streams, edge cases,
and real hardware captures.
"""

import unittest
import random
import struct
from tests.repo_paths import REPO_ROOT
from tests.test_utils import (
    FRAME_PIXELS,
    FRAME_BLOCKS,
    FRAME_BLOCK_BYTES,
    FRAME_BLOCK_ACTIVE_BYTES,
    WIRE_FRAME_BYTES,
    pack_12bit_frame,
    decode_12bit_frame,
    decode_chicagoh_frame,
)

FINGERPRINT_PGM = (REPO_ROOT / "legacy-experiments" / "fingerprint.pgm"
                   if (REPO_ROOT / "legacy-experiments" / "fingerprint.pgm").exists()
                   else REPO_ROOT / "experiments" / "fingerprint.pgm")
CLEAR0_PGM = (REPO_ROOT / "legacy-experiments" / "clear-0.pgm"
              if (REPO_ROOT / "legacy-experiments" / "clear-0.pgm").exists()
              else REPO_ROOT / "experiments" / "clear-0.pgm")

def decode_frame_old(data: bytes, length: int) -> list:
    """Old 2-step decoding: memcpy active bytes into packed buffer, then unpack 6-byte chunks."""
    if not data:
        return []
    packed = bytearray()
    for block in range(FRAME_BLOCKS):
        src = block * FRAME_BLOCK_BYTES
        if src + FRAME_BLOCK_ACTIVE_BYTES > length:
            break
        packed.extend(data[src : src + FRAME_BLOCK_ACTIVE_BYTES])

    pixel_idx = 0
    out = []
    i = 0
    packed_len = len(packed)
    while i + 6 <= packed_len and pixel_idx + 4 <= FRAME_PIXELS:
        c = packed[i : i + 6]
        out.append(((c[0] & 0x0F) << 8) | c[1])
        out.append((c[3] << 4) | (c[0] >> 4))
        out.append(((c[5] & 0x0F) << 8) | c[2])
        out.append((c[4] << 4) | (c[5] >> 4))
        pixel_idx += 4
        i += 6
    return out

def decode_frame_new(data: bytes, length: int) -> list:
    """New direct block decoding: decode 12-bit nibbles directly from wire blocks."""
    if not data:
        return []
    out = []
    pixel_idx = 0
    for block in range(FRAME_BLOCKS):
        src = block * FRAME_BLOCK_BYTES
        if src + FRAME_BLOCK_ACTIVE_BYTES > length:
            break
        blk = data[src : src + FRAME_BLOCK_ACTIVE_BYTES]
        i = 0
        while i < FRAME_BLOCK_ACTIVE_BYTES and pixel_idx + 4 <= FRAME_PIXELS:
            c = blk[i : i + 6]
            out.append(((c[0] & 0x0F) << 8) | c[1])
            out.append((c[3] << 4) | (c[0] >> 4))
            out.append(((c[5] & 0x0F) << 8) | c[2])
            out.append((c[4] << 4) | (c[5] >> 4))
            pixel_idx += 4
            i += 6
    return out

def build_wire_frame(pixels: list, padding_byte: int = 0x00, footer: bytes = b"\x12\x34\x56\x78") -> bytes:
    """Packs 5,120 pixels into a 10,564-byte wire frame with specified padding."""
    assert len(pixels) == FRAME_PIXELS
    packed = pack_12bit_frame(pixels)
    wire = bytearray()
    for b in range(FRAME_BLOCKS):
        start = b * FRAME_BLOCK_ACTIVE_BYTES
        wire.extend(packed[start : start + FRAME_BLOCK_ACTIVE_BYTES])
        wire.extend(bytes([padding_byte] * (FRAME_BLOCK_BYTES - FRAME_BLOCK_ACTIVE_BYTES)))
    wire.extend(footer)
    return bytes(wire)

class TestWireDecodingEquivalence(unittest.TestCase):

    def test_null_and_empty_buffers(self):
        """Verify behavior on None, empty byte string, and sub-block buffers."""
        self.assertEqual(decode_frame_old(None, 0), [])
        self.assertEqual(decode_frame_new(None, 0), [])
        self.assertEqual(decode_frame_old(b"", 0), [])
        self.assertEqual(decode_frame_new(b"", 0), [])
        self.assertEqual(decode_frame_old(b"\x00" * 50, 50), [])
        self.assertEqual(decode_frame_new(b"\x00" * 50, 50), [])

    def test_synthetic_all_zeros(self):
        """10,564 bytes of 0x00: all 5,120 pixels must be 0 and bitwise identical."""
        wire = bytes([0x00] * WIRE_FRAME_BYTES)
        old_px = decode_frame_old(wire, len(wire))
        new_px = decode_frame_new(wire, len(wire))
        self.assertEqual(len(new_px), FRAME_PIXELS)
        self.assertEqual(old_px, new_px)
        self.assertEqual(new_px, [0] * FRAME_PIXELS)

    def test_synthetic_all_0xff(self):
        """10,564 bytes of 0xFF: all 5,120 pixels must be 4095 and bitwise identical."""
        wire = bytes([0xFF] * WIRE_FRAME_BYTES)
        old_px = decode_frame_old(wire, len(wire))
        new_px = decode_frame_new(wire, len(wire))
        self.assertEqual(len(new_px), FRAME_PIXELS)
        self.assertEqual(old_px, new_px)
        self.assertEqual(new_px, [4095] * FRAME_PIXELS)

    def test_alternating_bit_patterns(self):
        """Alternating patterns (0xAA, 0x55, 0x5A, 0xA5) match bitwise."""
        for pat in [0xAA, 0x55, 0x5A, 0xA5, 0x33, 0xCC]:
            wire = bytes([pat] * WIRE_FRAME_BYTES)
            old_px = decode_frame_old(wire, len(wire))
            new_px = decode_frame_new(wire, len(wire))
            self.assertEqual(len(new_px), FRAME_PIXELS)
            self.assertEqual(old_px, new_px)

    @unittest.skipUnless(FINGERPRINT_PGM.exists(), "fingerprint.pgm fixture missing")
    def test_real_capture_fingerprint_pgm(self):
        """Real sensor capture legacy-experiments/fingerprint.pgm round-trip bitwise equality."""
        with open(FINGERPRINT_PGM, "r") as f:
            tokens = f.read().split()
        magic, w, h, maxv = tokens[0], int(tokens[1]), int(tokens[2]), int(tokens[3])
        self.assertEqual(magic, "P2")
        self.assertEqual(w, 64)
        self.assertEqual(h, 80)
        self.assertEqual(maxv, 4095)
        ground_truth_pixels = [int(x) for x in tokens[4:]]
        self.assertEqual(len(ground_truth_pixels), FRAME_PIXELS)

        wire = build_wire_frame(ground_truth_pixels)
        self.assertEqual(len(wire), WIRE_FRAME_BYTES)

        old_px = decode_frame_old(wire, len(wire))
        new_px = decode_frame_new(wire, len(wire))

        self.assertEqual(old_px, new_px)
        self.assertEqual(new_px, ground_truth_pixels)

    @unittest.skipUnless(CLEAR0_PGM.exists(), "clear-0.pgm fixture missing")
    def test_real_capture_clear0_pgm(self):
        """Baseline clear-0.pgm round-trip bitwise equality."""
        with open(CLEAR0_PGM, "r") as f:
            tokens = f.read().split()
        ground_truth_pixels = [int(x) for x in tokens[4:]]
        self.assertEqual(len(ground_truth_pixels), FRAME_PIXELS)

        wire = build_wire_frame(ground_truth_pixels)
        old_px = decode_frame_old(wire, len(wire))
        new_px = decode_frame_new(wire, len(wire))

        self.assertEqual(old_px, new_px)
        self.assertEqual(new_px, ground_truth_pixels)

    def test_padding_isolation_with_adversarial_noise(self):
        """Non-zero garbage in the 36 padding bytes per block must not affect decoded pixels."""
        pixels = [(i * 37) % 4096 for i in range(FRAME_PIXELS)]
        wire_clean = build_wire_frame(pixels, padding_byte=0x00)
        wire_noisy = build_wire_frame(pixels, padding_byte=0x7F, footer=b"\xDE\xAD\xBE\xEF")

        new_clean = decode_frame_new(wire_clean, len(wire_clean))
        new_noisy = decode_frame_new(wire_noisy, len(wire_noisy))
        old_noisy = decode_frame_old(wire_noisy, len(wire_noisy))

        self.assertEqual(new_clean, pixels)
        self.assertEqual(new_noisy, pixels)
        self.assertEqual(old_noisy, pixels)

    def test_truncation_boundaries(self):
        """Test partial lengths: block boundaries and mid-block cutoffs."""
        pixels = [(i * 13) % 4096 for i in range(FRAME_PIXELS)]
        wire = build_wire_frame(pixels)

        test_lens = [
            0, 1, 95, 96, 97, 131, 132, 133,
            132 * 10, 132 * 10 + 95, 132 * 10 + 96,
            10560, 10563, 10564, 10565, 20000
        ]
        for l in test_lens:
            old_px = decode_frame_old(wire, l)
            new_px = decode_frame_new(wire, l)
            self.assertEqual(old_px, new_px, f"Failed at length {l}")

    def test_random_fuzzing_500_buffers(self):
        """Fuzz with 500 randomized wire streams of varying lengths."""
        random.seed(999)
        for _ in range(500):
            wire_len = random.randint(0, WIRE_FRAME_BYTES + 100)
            data = bytes(random.getrandbits(8) for _ in range(wire_len))
            old_px = decode_frame_old(data, wire_len)
            new_px = decode_frame_new(data, wire_len)
            self.assertEqual(old_px, new_px)

if __name__ == "__main__":
    unittest.main()
