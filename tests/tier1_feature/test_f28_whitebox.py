"""
Tier 1 - Feature 28: Goodix 5e0a WhiteBox PSK Encryption & Wire Framing Verification.

Hermetically tests the reverse-engineered Goodix WhiteBox encryption and wire-provisioning
structures from wbdi.dll without hardware dependencies:
  (a) SHA256(CANONICAL_PSK) matches the observed 0xbb020001 MCU hash byte-for-byte;
  (b) SecWhiteEncrypt produces a 96-byte payload (16B IV + 48B Ciphertext + 32B HMAC);
  (c) SecWhiteDecrypt validates round-trip integrity and HMAC authenticity;
  (d) build_psk_write_payload formats the 10B magic header, TLV1 (0xbb010002), and TLV2 (0xbb010003);
  (e) chunk_psk_write_payload structures 12B chunk headers (total_len, chunk_len, chunk_offset).
"""

import hashlib
import struct
import unittest

from tests.test_utils import CANONICAL_PSK
from experiments.goodix_whitebox import (
    sec_white_encrypt,
    sec_white_decrypt,
    build_psk_write_payload,
    chunk_psk_write_payload,
)


class TestF28WhiteboxAndPskFraming(unittest.TestCase):

    def test_a_sha256_matches_mcu_hash_slot(self):
        """SHA-256 of the provisioned host PSK must match the 0xbb020001 MCU hash slot."""
        expected_hash = bytes.fromhex(
            "68776fdcf6352a215cc11cd58db2b361eb95a506cb503da68fb01ac1506ff1c9"
        )
        calculated_hash = hashlib.sha256(CANONICAL_PSK).digest()
        self.assertEqual(
            calculated_hash,
            expected_hash,
            "SHA256(host_psk) MUST equal the 0xbb020001 MCU hash readback."
        )

    def test_b_sec_white_encrypt_structure(self):
        """SecWhiteEncrypt output must be 96 bytes: 16B IV + 48B Ciphertext + 32B HMAC."""
        enc = sec_white_encrypt(CANONICAL_PSK)
        self.assertEqual(len(enc), 96)
        iv = enc[:16]
        ct = enc[16:64]
        mac = enc[64:]
        self.assertEqual(len(iv), 16)
        self.assertEqual(len(ct), 48)
        self.assertEqual(len(mac), 32)

    def test_c_roundtrip_decryption(self):
        """SecWhiteDecrypt must invert SecWhiteEncrypt and authenticate HMAC."""
        enc = sec_white_encrypt(CANONICAL_PSK)
        dec = sec_white_decrypt(enc)
        self.assertEqual(dec, CANONICAL_PSK)

        # Verify tamper detection
        tampered = bytearray(enc)
        tampered[20] ^= 0x01
        with self.assertRaises(ValueError):
            sec_white_decrypt(bytes(tampered))

    def test_d_psk_write_payload_tlvs(self):
        """Payload must contain 10B magic header and TLV1 (0xbb010002) + TLV2 (0xbb010003)."""
        sealed_blob = b"DUMMY_DPAPI_SEALED_BLOB"
        payload = build_psk_write_payload(CANONICAL_PSK, sealed_blob=sealed_blob)

        # 10-byte magic header
        expected_magic = bytes([0x56, 0xA5, 0xBB, 0x95, 0x6B, 0x7C, 0x8D, 0x9E, 0x00, 0x00])
        self.assertEqual(payload[:10], expected_magic)

        # TLV1: tag 0xbb010002, len = len(sealed_blob)
        off = 10
        tag1, len1 = struct.unpack("<II", payload[off:off + 8])
        self.assertEqual(tag1, 0xBB010002)
        self.assertEqual(len1, len(sealed_blob))
        self.assertEqual(payload[off + 8:off + 8 + len1], sealed_blob)

        # TLV2: tag 0xbb010003, len = 96
        off += 8 + len1
        tag2, len2 = struct.unpack("<II", payload[off:off + 8])
        self.assertEqual(tag2, 0xBB010003)
        self.assertEqual(len2, 96)

        # Decrypt TLV2 content
        enc_psk = payload[off + 8:off + 8 + len2]
        self.assertEqual(sec_white_decrypt(enc_psk), CANONICAL_PSK)

    def test_e_chunking_framing(self):
        """Chunking must enforce max chunk size and 12-byte Goodix chunk header."""
        payload = build_psk_write_payload(CANONICAL_PSK)
        chunks = chunk_psk_write_payload(payload, chunk_size=64)

        reconstructed = bytearray()
        for idx, chunk in enumerate(chunks):
            self.assertGreaterEqual(len(chunk), 12)
            tot, clen, coff = struct.unpack("<III", chunk[:12])
            self.assertEqual(tot, len(payload))
            self.assertEqual(clen, len(chunk) - 12)
            self.assertEqual(coff, len(reconstructed))
            self.assertLessEqual(clen, 64)
            reconstructed.extend(chunk[12:])

        self.assertEqual(bytes(reconstructed), payload)


if __name__ == "__main__":
    unittest.main()
