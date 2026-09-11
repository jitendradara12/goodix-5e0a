#!/usr/bin/env python3
"""Empirical Fuzzing and Negative Boundary Test Suite for sec_white_decrypt.

Author: Challenger 2 (teamwork_preview_challenger)
Target: experiments/goodix_whitebox.py -> sec_white_decrypt
"""

import hashlib
import os
import random
import struct
import subprocess
import sys
import unittest

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import experiments.goodix_whitebox as wb
from tests.test_utils import CANONICAL_PSK


class TestSecWhiteDecryptFuzzingAndBoundaries(unittest.TestCase):

    def setUp(self):
        self.kat_output = wb.KNOWN_OUTPUT
        self.kat_psk = wb.KNOWN_PSK
        self.canonical_psk = CANONICAL_PSK
        self.canonical_output = wb.sec_white_encrypt(CANONICAL_PSK)

    # ------------------------------------------------------------------------
    # 1. Ciphertext Block Alignment Stress-Testing
    # ------------------------------------------------------------------------
    def test_01_ciphertext_block_alignment(self):
        """Stress-test ciphertext lengths where len(ciphertext) % 16 != 0.

        Verifies:
        - For ct_len in 1..15 (wire 49..63): raises ValueError('Encrypted payload too short: ... < 64').
        - For ct_len >= 17 where ct_len % 16 != 0: raises ValueError('... is not a multiple of 16').
        - Tests ct_len from 1 to 128.
        """
        tested_lengths = 0
        min_length_rejected = 0
        alignment_rejected = 0

        for ct_len in range(1, 129):
            if ct_len % 16 == 0:
                continue
            tested_lengths += 1
            # Wire layout: 16B prefix + ct_len ciphertext + 32B HMAC
            dummy_wire = bytes(16) + bytes(ct_len) + bytes(32)

            with self.assertRaises(ValueError) as cm:
                wb.sec_white_decrypt(dummy_wire)

            err_msg = str(cm.exception)
            if ct_len < 16:
                # Wire is 49..63 bytes -> rejected by min length guard < 64
                self.assertIn("too short", err_msg)
                self.assertIn("< 64", err_msg)
                min_length_rejected += 1
            else:
                # Wire is >= 65 bytes -> rejected by multiple of 16 check
                self.assertIn("multiple of 16", err_msg)
                self.assertIn(f"Ciphertext length {ct_len} is not a multiple of 16", err_msg)
                alignment_rejected += 1

        print(f"[TEST 1 PASS] Ciphertext block alignment: {tested_lengths} non-multiple-of-16 lengths tested "
              f"({min_length_rejected} caught by min-length guard <64, {alignment_rejected} caught by multiple-of-16 guard).")

    # ------------------------------------------------------------------------
    # 2. Payload Length Truncation Stress-Testing
    # ------------------------------------------------------------------------
    def test_02_payload_length_truncation(self):
        """Stress-test payload lengths 0 to 63 and truncated KAT (95 bytes)."""
        # Test all wire lengths 0 to 63 bytes
        short_count = 0
        for wire_len in range(64):
            with self.assertRaises(ValueError) as cm:
                wb.sec_white_decrypt(bytes(wire_len))
            self.assertIn("too short", str(cm.exception))
            short_count += 1

        # Test truncated 32B KAT (95 bytes)
        trunc_kat = self.kat_output[:95]
        self.assertEqual(len(trunc_kat), 95)
        with self.assertRaises(ValueError) as cm:
            wb.sec_white_decrypt(trunc_kat)
        self.assertIn("multiple of 16", str(cm.exception))
        self.assertEqual(str(cm.exception), "Ciphertext length 47 is not a multiple of 16")

        # Test progressive truncation of 32B KAT from 95 down to 0 bytes
        kat_truncations = 0
        for trunc_len in range(95, -1, -1):
            sub_blob = self.kat_output[:trunc_len]
            with self.assertRaises(ValueError):
                wb.sec_white_decrypt(sub_blob)
            kat_truncations += 1

        # Test with explicit expected_len parameter
        for psk_len, exp_wire in [(16, 80), (32, 96), (48, 112), (64, 128)]:
            for trunc_len in [64, exp_wire - 1]:
                if trunc_len < exp_wire:
                    with self.assertRaises(ValueError) as cm:
                        wb.sec_white_decrypt(bytes(trunc_len), expected_len=psk_len)
                    self.assertIn("too short", str(cm.exception))

        print(f"[TEST 2 PASS] Payload truncation: {short_count} lengths (0..63) verified, "
              f"{kat_truncations} KAT progressive truncations (0..95) verified.")

    # ------------------------------------------------------------------------
    # 3. Prefix Mutation Stress-Testing (Single-bit and Multi-byte)
    # ------------------------------------------------------------------------
    def test_03_prefix_mutation(self):
        """Stress-test prefix mutation: flip each bit of 16B prefix across multiple payloads."""
        payloads = [
            ("32B KAT (96B wire)", self.kat_output, "ec35ae3abb45ed3f12c4751f1e5c2cc0"),
            ("Canonical PSK (96B wire)", self.canonical_output, self.canonical_output[:16].hex()),
        ]
        # Also add 16B, 48B, 64B payloads
        for size in [16, 48, 64]:
            raw = bytes([i % 256 for i in range(size)])
            enc = wb.sec_white_encrypt(raw)
            payloads.append((f"{size}B PSK ({len(enc)}B wire)", enc, enc[:16].hex()))

        total_prefix_bit_flips = 0
        for desc, wire, exp_prefix_hex in payloads:
            wire_flips = 0
            for byte_idx in range(16):
                for bit_idx in range(8):
                    tampered = bytearray(wire)
                    tampered[byte_idx] ^= (1 << bit_idx)
                    act_prefix_hex = bytes(tampered[:16]).hex()

                    with self.assertRaises(ValueError) as cm:
                        wb.sec_white_decrypt(bytes(tampered))

                    err_msg = str(cm.exception)
                    self.assertIn("Prefix mismatch:", err_msg)
                    self.assertIn(f"expected {exp_prefix_hex}", err_msg)
                    self.assertIn(f"got {act_prefix_hex}", err_msg)
                    wire_flips += 1
                    total_prefix_bit_flips += 1

            self.assertEqual(wire_flips, 128)

        # Multi-byte prefix mutations
        for pattern in [bytes(16), bytes([0xFF] * 16), bytes([0xAA] * 16), bytes([0x55] * 16)]:
            tampered = pattern + self.kat_output[16:]
            with self.assertRaises(ValueError) as cm:
                wb.sec_white_decrypt(tampered)
            self.assertIn("Prefix mismatch:", str(cm.exception))

        print(f"[TEST 3 PASS] Prefix mutation: {total_prefix_bit_flips} single-bit flips across "
              f"{len(payloads)} payloads verified with exact expected vs actual hex.")

    # ------------------------------------------------------------------------
    # 4. HMAC Tampering Stress-Testing
    # ------------------------------------------------------------------------
    def test_04_hmac_tampering(self):
        """Stress-test HMAC tampering: flip each bit of the 32B HMAC tag across payloads."""
        payloads = [
            ("32B KAT (96B wire)", self.kat_output),
            ("Canonical PSK (96B wire)", self.canonical_output),
        ]
        for size in [16, 48, 64]:
            raw = bytes([i % 256 for i in range(size)])
            payloads.append((f"{size}B PSK", wb.sec_white_encrypt(raw)))

        total_hmac_bit_flips = 0
        for desc, wire in payloads:
            wire_flips = 0
            hmac_start = len(wire) - 32
            for byte_idx in range(hmac_start, len(wire)):
                for bit_idx in range(8):
                    tampered = bytearray(wire)
                    tampered[byte_idx] ^= (1 << bit_idx)

                    with self.assertRaises(ValueError) as cm:
                        wb.sec_white_decrypt(bytes(tampered))

                    self.assertEqual(str(cm.exception), "HMAC verification failed")
                    wire_flips += 1
                    total_hmac_bit_flips += 1

            self.assertEqual(wire_flips, 256)

        # Gross HMAC corruptions
        for hmac_replacement in [bytes(32), bytes([0xFF] * 32), bytes([0x42] * 32)]:
            tampered = self.kat_output[:-32] + hmac_replacement
            with self.assertRaises(ValueError) as cm:
                wb.sec_white_decrypt(tampered)
            self.assertEqual(str(cm.exception), "HMAC verification failed")

        print(f"[TEST 4 PASS] HMAC tampering: {total_hmac_bit_flips} single-bit flips across "
              f"{len(payloads)} payloads verified with ValueError('HMAC verification failed').")

    # ------------------------------------------------------------------------
    # 5. Ciphertext Tampering Stress-Testing
    # ------------------------------------------------------------------------
    def test_05_ciphertext_tampering(self):
        """Stress-test ciphertext bit-flips: verify HMAC authentication catches every flip."""
        # 32B KAT has 48B ciphertext (indices 16..63)
        ct_bit_flips = 0
        for byte_idx in range(16, 64):
            for bit_idx in range(8):
                tampered = bytearray(self.kat_output)
                tampered[byte_idx] ^= (1 << bit_idx)

                with self.assertRaises(ValueError) as cm:
                    wb.sec_white_decrypt(bytes(tampered))

                # Since prefix is untouched, it reaches HMAC check and fails
                self.assertEqual(str(cm.exception), "HMAC verification failed")
                ct_bit_flips += 1

        self.assertEqual(ct_bit_flips, 48 * 8)
        print(f"[TEST 5 PASS] Ciphertext bit-flipping: {ct_bit_flips} bit flips in ciphertext caught by HMAC.")

    # ------------------------------------------------------------------------
    # 6. Exception Hygiene & Fuzzing Matrix
    # ------------------------------------------------------------------------
    def test_06_exception_hygiene_and_random_fuzzing(self):
        """Verify that NO unhandled exceptions escape across 2,000 randomized test vectors.

        Ensures:
        - No CalledProcessError (from openssl subprocess fallback)
        - No KeyError
        - No IndexError
        - No AttributeError
        - No unhandled cryptography exceptions (InvalidPadding, etc.)
        - Only ValueError is raised.
        """
        rng = random.Random(0x5E0A27C6)
        iterations = 2000
        unhandled_exceptions = []
        value_errors = 0

        for i in range(iterations):
            # Generate random length from 0 to 512
            length = rng.randint(0, 512)
            fuzz_data = rng.randbytes(length)

            try:
                wb.sec_white_decrypt(fuzz_data)
                # If random data ever successfully decrypted, that would be astonishing (1 in 2^384)
                self.fail(f"Random blob of length {length} unexpectedly decrypted successfully!")
            except ValueError:
                value_errors += 1
            except Exception as e:
                unhandled_exceptions.append((i, length, type(e).__name__, str(e)))

        self.assertEqual(len(unhandled_exceptions), 0, f"Unhandled exceptions detected: {unhandled_exceptions[:5]}")
        self.assertEqual(value_errors, iterations)

        print(f"[TEST 6 PASS] Exception hygiene fuzzing: {iterations} random vectors tested, "
              f"{value_errors} cleanly raised ValueError, 0 unhandled exceptions.")

    # ------------------------------------------------------------------------
    # 7. Forged Ciphertext with Valid HMAC (Padding Error Path)
    # ------------------------------------------------------------------------
    def test_07_forged_ciphertext_valid_hmac_padding_hygiene(self):
        """Construct payloads with valid prefix and valid HMAC over corrupt ciphertext.

        This forces execution past prefix & HMAC checks directly into _aes_128_cbc_decrypt
        to test CBC decrypt exception hygiene (e.g. OpenSSL subprocess error vs Cryptography InvalidPadding).
        """
        prefix = self.kat_output[:16]
        _, hmac_key = wb.derive_keys(prefix)

        # Generate 50 corrupt ciphertexts (each a multiple of 16 bytes)
        rng = random.Random(0x1337C0DE)
        padding_errors_caught = 0

        for size_blocks in [1, 2, 3, 4, 5]:
            ct_len = size_blocks * 16
            for trial in range(10):
                corrupt_ct = rng.randbytes(ct_len)
                valid_hmac = wb.compute_hmac(hmac_key, corrupt_ct)
                crafted_wire = prefix + corrupt_ct + valid_hmac

                try:
                    wb.sec_white_decrypt(crafted_wire, expected_len=32)
                except ValueError as e:
                    # Must be a ValueError (e.g. "OpenSSL decryption failed" or "Invalid padding bytes")
                    padding_errors_caught += 1
                except Exception as e:
                    self.fail(f"Unhandled non-ValueError escaped from _aes_128_cbc_decrypt: {type(e).__name__}: {e}")

        self.assertEqual(padding_errors_caught, 50)
        print(f"[TEST 7 PASS] Forged ciphertext padding hygiene: {padding_errors_caught} crafted payloads "
              f"with valid HMACs cleanly raised ValueError on decryption unpadding.")


if __name__ == "__main__":
    unittest.main()
