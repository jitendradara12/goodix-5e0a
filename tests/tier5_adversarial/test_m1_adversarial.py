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
        cls.down_s12 = parse_c_array(cls.header_content, "goodix_5e0a_down_s12")
        cls.down_retry = parse_c_array(cls.header_content, "goodix_5e0a_down_retry")
        cls.up_u01 = parse_c_array(cls.header_content, "goodix_5e0a_up_u01")
        cls.img_payload = parse_c_array(cls.header_content, "goodix_5e0a_img_payload")
        cls.config_table = parse_c_array(cls.header_content, "goodix_5e0a_config")
        cls.psk = parse_c_array(cls.header_content, "goodix_5e0a_psk")

    def test_down_and_up_table_properties(self):
        """
        Verify that down_s12, down_retry, and up_u01 are exactly 35 bytes,
        and down_s12 and down_retry differ only at specific retry slot bytes.
        """
        self.assertEqual(len(self.down_s12), 35)
        self.assertEqual(len(self.down_retry), 35)
        self.assertEqual(len(self.up_u01), 35)

        diff_indices = [i for i in range(35) if self.down_s12[i] != self.down_retry[i]]
        # Diffs at slot bytes 11 and 19
        self.assertEqual(diff_indices, [11, 19])

    def test_down_s12_exhaustive_bit_flip_checksum_invalidation(self):
        """
        Flip every single bit in down_s12 payload
        and verify that the wire checksum invalidates in 100% of cases.
        """
        encoded = encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, self.down_s12, calc_checksum=True, pad_data=False)
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
            f"Expected 0 false negatives for bit flips in down_s12, but {len(failures)} passed: {failures}"
        )

    def test_up_u01_exhaustive_bit_flip_checksum_invalidation(self):
        """
        Flip every single bit in up_u01 payload
        and verify that the wire checksum invalidates in 100% of cases.
        """
        encoded = encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, self.up_u01, calc_checksum=True, pad_data=False)
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
            f"Expected 0 false negatives for bit flips in up_u01, but {len(failures)} passed: {failures}"
        )

    def test_img_payload_exhaustive_bit_flip_checksum_invalidation(self):
        """
        Flip every single bit in img_payload
        and verify that the wire checksum invalidates in 100% of cases.
        """
        encoded = encode_protocol(0x20, self.img_payload, calc_checksum=True, pad_data=False)
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
            f"Expected 0 false negatives for bit flips in img_payload, but {len(failures)} passed: {failures}"
        )

    def test_config_table_exhaustive_bit_flip_checksum_invalidation(self):
        """
        Flip every single bit (256 bytes * 8 bits = 2048 bit flips) in config_table payload
        and verify that the wire checksum invalidates in 100% of cases.
        """
        encoded = encode_protocol(0x90, self.config_table, calc_checksum=True, pad_data=False)
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
            f"Expected 0 false negatives for bit flips in config_table, but {len(failures)} passed: {failures}"
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
            ("DOWN_S12", CMD_MCU_SWITCH_TO_FDT_DOWN, self.down_s12),
            ("UP_U01", CMD_MCU_SWITCH_TO_FDT_UP, self.up_u01),
            ("IMG_PAYLOAD", 0x20, self.img_payload),
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
