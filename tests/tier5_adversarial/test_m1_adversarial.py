"""
Tier 5 Adversarial Tests: Milestone 1 Payload Stress & Mutation Harness
Adversarially tests:
- Exhaustive single-bit flips across all 39 bytes of FDT DOWN and UP
- Exhaustive single-bit flips across FDT MODE (27B), CONFIG_52XD (256B), and PSK (32B)
- Strict byte 26 distinction invariant (FDT DOWN=0x01 vs FDT UP=0x00)
- Checksum integrity, collision resistance, and tamper detection
- Integer promotion and sign extension edge cases in checksum verification
"""

import struct
import unittest
from pathlib import Path
from tests.test_utils import (
    CANONICAL_PSK,
    CANONICAL_CONFIG_52XD,
    CANONICAL_FDT_MODE,
    CANONICAL_FDT_DOWN,
    CANONICAL_FDT_UP,
    CANONICAL_REG_022C_GAIN,
    CMD_MCU_SWITCH_TO_FDT_DOWN,
    CMD_MCU_SWITCH_TO_FDT_UP,
    CMD_MCU_SWITCH_TO_FDT_MODE,
    CMD_WRITE_SENSOR_REGISTER,
    FLAGS_MSG_PROTOCOL,
    NULL_CHECKSUM,
    encode_protocol,
    decode_protocol,
    encode_pack,
    decode_pack,
    calc_protocol_checksum,
    calc_pack_checksum,
)
from tests.tier1_feature.test_m1_payloads import parse_c_array, parse_c_macro

HEADER_PATH = Path("/tmp/libfprint-goodix/libfprint/drivers/goodixtls/goodix5e0a.h")


class TestM1AdversarialHarness(unittest.TestCase):
    """Adversarial challenge test suite for Milestone 1 payloads and protocols."""

    @classmethod
    def setUpClass(cls):
        cls.header_content = HEADER_PATH.read_text(encoding="utf-8")
        cls.fdt_down = parse_c_array(cls.header_content, "goodix_5e0a_fdt_down")
        cls.fdt_up = parse_c_array(cls.header_content, "goodix_5e0a_fdt_up")
        cls.fdt_mode = parse_c_array(cls.header_content, "goodix_5e0a_fdt_mode")
        cls.config_52xd = parse_c_array(cls.header_content, "goodix_5e0a_config")
        cls.psk = parse_c_array(cls.header_content, "goodix_5e0a_psk")

    def test_byte_26_strict_distinction_invariant(self):
        """
        Adversarially verify that FDT DOWN (0x32) and FDT UP (0x34) differ ONLY at byte 26,
        and that byte 26 is strictly 0x01 for DOWN and 0x00 for UP.
        """
        self.assertEqual(len(self.fdt_down), 39)
        self.assertEqual(len(self.fdt_up), 39)
        self.assertEqual(self.fdt_down[26], 0x01, "FDT DOWN byte 26 must be 0x01 (Touch)")
        self.assertEqual(self.fdt_up[26], 0x00, "FDT UP byte 26 must be 0x00 (Release)")

        diff_indices = [i for i in range(39) if self.fdt_down[i] != self.fdt_up[i]]
        self.assertEqual(
            diff_indices, [26],
            f"FDT DOWN and FDT UP must differ exclusively at byte 26, found differences at {diff_indices}"
        )

        # Verify Hamming distance is exactly 1 bit
        bit_diff = bin(self.fdt_down[26] ^ self.fdt_up[26]).count("1")
        self.assertEqual(bit_diff, 1, "Byte 26 hamming distance between DOWN (0x01) and UP (0x00) must be 1")

    def test_fdt_down_exhaustive_bit_flip_checksum_invalidation(self):
        """
        Flip every single bit (39 bytes * 8 bits = 312 bit flips) in FDT DOWN payload
        and verify that the wire checksum invalidates in 100% of cases.
        """
        encoded = encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, self.fdt_down, calc_checksum=True, pad_data=False)
        total_len = len(encoded)

        failures = []
        for byte_idx in range(total_len):
            for bit in range(8):
                corrupt = bytearray(encoded)
                corrupt[byte_idx] ^= (1 << bit)
                corrupt_bytes = bytes(corrupt)

                ok, cmd, payload, valid_chk, valid_null = decode_protocol(corrupt_bytes)
                if ok and valid_chk:
                    failures.append((byte_idx, bit))

        self.assertEqual(
            len(failures), 0,
            f"Expected 0 false negatives for bit flips in FDT DOWN, but {len(failures)} passed: {failures}"
        )

    def test_fdt_up_exhaustive_bit_flip_checksum_invalidation(self):
        """
        Flip every single bit (39 bytes * 8 bits = 312 bit flips) in FDT UP payload
        and verify that the wire checksum invalidates in 100% of cases.
        """
        encoded = encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, self.fdt_up, calc_checksum=True, pad_data=False)
        total_len = len(encoded)

        failures = []
        for byte_idx in range(total_len):
            for bit in range(8):
                corrupt = bytearray(encoded)
                corrupt[byte_idx] ^= (1 << bit)
                corrupt_bytes = bytes(corrupt)

                ok, cmd, payload, valid_chk, valid_null = decode_protocol(corrupt_bytes)
                if ok and valid_chk:
                    failures.append((byte_idx, bit))

        self.assertEqual(
            len(failures), 0,
            f"Expected 0 false negatives for bit flips in FDT UP, but {len(failures)} passed: {failures}"
        )

    def test_fdt_mode_exhaustive_bit_flip_checksum_invalidation(self):
        """
        Flip every single bit (27 bytes * 8 bits = 216 bit flips) in FDT MODE payload
        and verify that the wire checksum invalidates in 100% of cases.
        """
        encoded = encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, self.fdt_mode, calc_checksum=True, pad_data=False)
        total_len = len(encoded)

        failures = []
        for byte_idx in range(total_len):
            for bit in range(8):
                corrupt = bytearray(encoded)
                corrupt[byte_idx] ^= (1 << bit)
                corrupt_bytes = bytes(corrupt)

                ok, cmd, payload, valid_chk, valid_null = decode_protocol(corrupt_bytes)
                if ok and valid_chk:
                    failures.append((byte_idx, bit))

        self.assertEqual(
            len(failures), 0,
            f"Expected 0 false negatives for bit flips in FDT MODE, but {len(failures)} passed: {failures}"
        )

    def test_config_52xd_exhaustive_bit_flip_checksum_invalidation(self):
        """
        Flip every single bit (256 bytes * 8 bits = 2048 bit flips) in CONFIG_52XD payload
        and verify that the wire checksum invalidates in 100% of cases.
        """
        encoded = encode_protocol(0x90, self.config_52xd, calc_checksum=True, pad_data=False)
        total_len = len(encoded)

        failures = []
        for byte_idx in range(total_len):
            for bit in range(8):
                corrupt = bytearray(encoded)
                corrupt[byte_idx] ^= (1 << bit)
                corrupt_bytes = bytes(corrupt)

                ok, cmd, payload, valid_chk, valid_null = decode_protocol(corrupt_bytes)
                if ok and valid_chk:
                    failures.append((byte_idx, bit))

        self.assertEqual(
            len(failures), 0,
            f"Expected 0 false negatives for bit flips in CONFIG_52XD, but {len(failures)} passed: {failures}"
        )

    def test_psk_key_tamper_detection(self):
        """
        Flip every single bit (32 bytes * 8 bits = 256 bit flips) in PSK key
        and verify that tampering is detected when used in preset PSK packet.
        """
        encoded = encode_protocol(0xE4, self.psk, calc_checksum=True, pad_data=False)
        total_len = len(encoded)

        failures = []
        for byte_idx in range(total_len):
            for bit in range(8):
                corrupt = bytearray(encoded)
                corrupt[byte_idx] ^= (1 << bit)
                corrupt_bytes = bytes(corrupt)

                ok, cmd, payload, valid_chk, valid_null = decode_protocol(corrupt_bytes)
                if ok and valid_chk:
                    failures.append((byte_idx, bit))

        self.assertEqual(
            len(failures), 0,
            f"Expected 0 false negatives for bit flips in PSK, but {len(failures)} passed: {failures}"
        )

    def test_exhaustive_checksum_sweep(self):
        """
        For a given valid packet, substitute all 256 possible values into the checksum position.
        Exactly 1 value must be accepted, and 255 values must be rejected.
        """
        for name, cmd, payload in [
            ("FDT_DOWN", CMD_MCU_SWITCH_TO_FDT_DOWN, self.fdt_down),
            ("FDT_UP", CMD_MCU_SWITCH_TO_FDT_UP, self.fdt_up),
            ("FDT_MODE", CMD_MCU_SWITCH_TO_FDT_MODE, self.fdt_mode),
        ]:
            encoded = bytearray(encode_protocol(cmd, payload, calc_checksum=True, pad_data=False))
            chk_idx = len(encoded) - 1
            valid_chk_byte = encoded[chk_idx]

            accepted_values = []
            for test_val in range(256):
                encoded[chk_idx] = test_val
                ok, _, _, valid_chk, _ = decode_protocol(bytes(encoded))
                if ok and valid_chk:
                    accepted_values.append(test_val)

            self.assertEqual(
                accepted_values, [valid_chk_byte],
                f"{name} checksum sweep failed: accepted {accepted_values}, expected only [{valid_chk_byte}]"
            )

    def test_checksum_integer_promotion_boundary_analysis(self):
        """
        Verify that protocol checksum formula (0xAA - sum) works consistently across
        the entire range where sum <= 0xAA and sum > 0xAA (which would be negative in signed 32-bit int).
        """
        for sum_val in range(256):
            expected_chk = (0xAA - sum_val) & 0xFF
            # Construct a 1-byte payload whose header+payload sum equals sum_val
            # hdr: cmd=0x00, wire_len=2 (sum = 2)
            # if sum_val >= 2, payload = sum_val - 2
            if sum_val >= 2:
                payload_byte = sum_val - 2
                raw = bytes([0x00, 0x02, 0x00, payload_byte, expected_chk])
                ok, cmd, payload, valid_chk, valid_null = decode_protocol(raw)
                self.assertTrue(ok)
                self.assertTrue(valid_chk, f"Checksum verification failed for sum_val={sum_val}")


if __name__ == "__main__":
    unittest.main()
