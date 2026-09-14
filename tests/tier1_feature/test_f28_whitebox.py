"""
Tier 1 - Feature 28: Goodix 5e0a WhiteBox PSK Encryption & Wire Framing Verification.

Hermetically tests the reverse-engineered Goodix WhiteBox encryption and wire-provisioning
structures from wbdi.dll without hardware dependencies:
  (a) SHA256(CANONICAL_PSK) matches the observed 0xbb020001 MCU hash byte-for-byte;
  (b) SecWhiteEncrypt produces a 96-byte payload (16B IV + 48B Ciphertext + 32B HMAC)
      and pins intermediate vectors (hash1, prefix, hash2, aes_key, iv);
  (c) SecWhiteDecrypt validates round-trip integrity, multi-size inputs (16/32/48/64B),
      and input guards (length % 16, short payload, bit-flip HMAC, tampered MAC, prefix mismatch);
  (d) build_psk_write_payload formats the 10B magic header, TLV1 (0xbb010002), and TLV2 (0xbb010003);
  (e) chunk_psk_write_payload structures 12B chunk headers (total_len, chunk_len, chunk_offset).
"""

import hashlib
import struct
import unittest

import tests.repo_paths
from tests.test_utils import CANONICAL_PSK
from goodix_whitebox import (
    sec_white_encrypt,
    sec_white_decrypt,
    build_psk_write_payload,
    chunk_psk_write_payload,
    derive_hash1,
    mutate_byte15,
    derive_hash2,
    derive_keys,
    compute_hmac,
    KNOWN_PSK,
    KNOWN_OUTPUT,
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
        """SecWhiteEncrypt output must be 96 bytes: 16B IV + 48B Ciphertext + 32B HMAC.

        Pins intermediate vectors (hash1, prefix, hash2, aes_key, iv) for 32B zero KAT (Ticket 63),
        verifies 96B KAT output, and ensures single-hash derivation does not match aes_key.
        """
        enc = sec_white_encrypt(CANONICAL_PSK)
        self.assertEqual(len(enc), 96)
        iv = enc[:16]
        ct = enc[16:64]
        mac = enc[64:]
        self.assertEqual(len(iv), 16)
        self.assertEqual(len(ct), 48)
        self.assertEqual(len(mac), 32)

        # Ticket 63: Pin intermediate vectors for 32B zero KAT
        kat_len = 32
        hash1 = derive_hash1(kat_len)
        self.assertEqual(
            hash1.hex(),
            "ec35ae3abb45ed3f12c4751f1e5c2ccc412608157f318e4d4693589753d088f0",
            "hash1 intermediate vector mismatch",
        )

        prefix = mutate_byte15(hash1, kat_len)
        self.assertEqual(
            prefix.hex(),
            "ec35ae3abb45ed3f12c4751f1e5c2cc0",
            "prefix intermediate vector mismatch",
        )

        hash2 = derive_hash2(prefix)
        self.assertEqual(
            hash2.hex(),
            "b7e7f234c4e98b9eef95bfe665bacad2b80a0a33ed2dde8a98be21f02942ad7f",
            "hash2 intermediate vector mismatch",
        )

        aes_key, hmac_key = derive_keys(prefix)
        self.assertEqual(
            aes_key.hex(),
            "b7e7f234c4e98b9eef95bfe665bacad2",
            "aes_key intermediate vector mismatch",
        )
        self.assertEqual(
            hmac_key.hex(),
            "b7e7f234c4e98b9eef95bfe665bacad2b80a0a33ed2dde8a98be21f02942ad7f",
            "hmac_key intermediate vector mismatch",
        )

        derived_iv = prefix
        self.assertEqual(
            derived_iv.hex(),
            "ec35ae3abb45ed3f12c4751f1e5c2cc0",
            "IV intermediate vector mismatch",
        )

        # Anti-regression assert: single-hash derivation must not match aes_key
        single_hash_key = hash1[:16]
        self.assertNotEqual(
            aes_key,
            single_hash_key,
            "Anti-regression check failed: aes_key must not equal single-hash hash1[:16]",
        )

        # Verify 96B KAT output
        kat_enc = sec_white_encrypt(KNOWN_PSK)
        self.assertEqual(len(kat_enc), 96)
        self.assertEqual(kat_enc, KNOWN_OUTPUT, "96B KAT output mismatch")

    def test_c_roundtrip_decryption(self):
        """SecWhiteDecrypt must invert SecWhiteEncrypt and authenticate HMAC.

        Covers multi-size roundtrips (16B, 32B, 48B, 64B) with wire lengths (80B, 96B, 112B, 128B) (Ticket 64).
        Tests decrypt input guards: non-multiple-of-16 ct, short payloads (<64B), bit-flipped ciphertext,
        tampered HMAC, and corrupted prefix with expected/actual hex strings (Ticket 62).
        """
        # Canonical PSK roundtrip
        enc = sec_white_encrypt(CANONICAL_PSK)
        dec = sec_white_decrypt(enc)
        self.assertEqual(dec, CANONICAL_PSK)

        # Ticket 64: Multi-size round-trip coverage
        sizes_and_wires = [(16, 80), (32, 96), (48, 112), (64, 128)]
        for size, expected_wire_len in sizes_and_wires:
            with self.subTest(size=size, expected_wire_len=expected_wire_len):
                test_data = bytes([i % 256 for i in range(size)])
                enc_data = sec_white_encrypt(test_data)
                self.assertEqual(
                    len(enc_data),
                    expected_wire_len,
                    f"Wire length mismatch for {size}B input: got {len(enc_data)}, expected {expected_wire_len}",
                )
                dec_data = sec_white_decrypt(enc_data)
                self.assertEqual(dec_data, test_data, f"Round-trip decryption failed for {size}B input")

                # Also verify explicit expected_len parameter
                dec_explicit = sec_white_decrypt(enc_data, expected_len=size)
                self.assertEqual(dec_explicit, test_data)

        # Ticket 62: Decrypt input guards

        # Guard 1: Truncated / non-multiple-of-16 ciphertext length -> ValueError
        with self.assertRaises(ValueError) as cm:
            sec_white_decrypt(KNOWN_OUTPUT[:-1])  # 95 bytes: 16B prefix + 47B ct + 32B mac
        self.assertIn("multiple of 16", str(cm.exception))

        # Guard 2: Short payload (<64B) -> ValueError
        for short_len in [0, 16, 48, 63]:
            with self.subTest(short_len=short_len):
                with self.assertRaises(ValueError) as cm:
                    sec_white_decrypt(bytes(short_len))
                self.assertIn("too short", str(cm.exception))

        # Guard 3: Bit-flipped ciphertext -> HMAC failure
        tampered_ct = bytearray(KNOWN_OUTPUT)
        tampered_ct[20] ^= 0x01  # Offset 20 is inside ciphertext (16..63)
        with self.assertRaises(ValueError) as cm:
            sec_white_decrypt(bytes(tampered_ct))
        self.assertIn("HMAC verification failed", str(cm.exception))

        # Guard 4: Tampered HMAC -> HMAC failure
        tampered_mac = bytearray(KNOWN_OUTPUT)
        tampered_mac[-1] ^= 0x01  # Offset 95 is inside HMAC tag (64..95)
        with self.assertRaises(ValueError) as cm:
            sec_white_decrypt(bytes(tampered_mac))
        self.assertIn("HMAC verification failed", str(cm.exception))

        # Guard 5: Corrupted prefix -> ValueError with expected and actual hex strings
        corrupted_prefix = bytearray(KNOWN_OUTPUT)
        corrupted_prefix[0] ^= 0x01  # Flip first byte of prefix
        with self.assertRaises(ValueError) as cm:
            sec_white_decrypt(bytes(corrupted_prefix))
        err_msg = str(cm.exception)
        self.assertIn("Prefix mismatch", err_msg)
        self.assertIn("expected", err_msg)
        self.assertIn("got", err_msg)
        expected_hex = "ec35ae3abb45ed3f12c4751f1e5c2cc0"
        actual_hex = bytes(corrupted_prefix[:16]).hex()
        self.assertIn(expected_hex, err_msg)
        self.assertIn(actual_hex, err_msg)

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
