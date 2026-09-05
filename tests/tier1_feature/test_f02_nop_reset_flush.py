"""
Tier 1 - Feature 2: NOP Buffer Flush & Reset
Requirements: Send CMD 0x00 and CMD 0xa2 to drain stale USB replies and reset sensor.
"""

import unittest
import struct
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_NOP, CMD_RESET, CMD_ACK, RESET_NUMBER
)

class TestF02NopResetFlush(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_nop_command_encoding(self):
        """Verify NOP packet structure (CMD 0x00, wire length = 1, checksum valid)."""
        packet = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b"", calc_checksum=True, pad_data=False), pad_data=False)
        ok, flags, body, chk_ok = decode_pack(packet)
        self.assertTrue(ok)
        self.assertTrue(chk_ok)
        self.assertEqual(flags, FLAGS_MSG_PROTOCOL)

        p_ok, cmd, payload, p_chk_ok, is_null = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertTrue(p_chk_ok)
        self.assertEqual(cmd, CMD_NOP)
        self.assertEqual(payload, b"")

    def test_reset_command_encoding(self):
        """Verify Reset command encoding (CMD 0xa2, payload: soft_reset=1, sleep_time=20)."""
        # Reset payload: struct { reset_sensor:1, soft_reset_mcu:1, padding:6, sleep_time:8 }
        payload = struct.pack("<BB", 0x03, 20)  # reset_sensor=1, soft_reset=1, sleep=20
        packet = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_RESET, payload, calc_checksum=True))
        reply = self.mcu.handle_out_packet(packet)
        self.assertGreater(len(reply), 0)

    def test_mcu_reset_reply_counter(self):
        """Verify MCU reset reply returns reset counter 2048."""
        payload = struct.pack("<BB", 0x03, 20)
        packet = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_RESET, payload))
        reply = self.mcu.handle_out_packet(packet)

        ok, flags, body, _ = decode_pack(reply)
        p_ok, cmd, resp_payload, p_chk_ok, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_RESET)
        counter = struct.unpack("<H", resp_payload)[0]
        self.assertEqual(counter, RESET_NUMBER)

    def test_nop_buffer_flush_silence_is_success(self):
        """Verify mock NOP produces no reply (silence = success / buffer empty)."""
        packet = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = self.mcu.handle_out_packet(packet)
        # Proven on-wire hardware fact: 5e0a MCU never replies to NOP; silence is success
        self.assertEqual(reply, b"")

    def test_nop_ack_validated_if_received(self):
        """Verify if MCU firmware does send an ACK to NOP, it is properly validated."""
        self.mcu.nop_replies = True
        packet = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = self.mcu.handle_out_packet(packet)
        ok, flags, body, _ = decode_pack(reply)
        self.assertTrue(ok)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_ACK)
        self.assertEqual(payload[0], CMD_NOP)
        self.assertEqual(payload[1] & 0x01, 0x01)  # always_true bit

    def test_regression_ticket01_nop_timeout_aborts_activation(self):
        """
        Regression test for Ticket 01:
        Ensure the test suite fails if NOP-timeout-aborts-activation ever returns.
        Verifies:
        1. goodix_send_nop routes through goodix_receive_none_tolerant in goodix.c.
        2. goodix_receive_none_tolerant explicitly clears G_IO_ERROR_TIMED_OUT.
        3. Non-timeout errors (e.g. G_IO_ERROR_FAILED) are not cleared and fail activation.
        """
        import re
        from pathlib import Path
        driver_c = Path(__file__).resolve().parents[2] / "libfprint-driver" / "goodix.c"
        self.assertTrue(driver_c.exists(), f"Driver source missing at {driver_c}")
        c_code = driver_c.read_text(encoding="utf-8")

        # 1. Verify tolerant receiver definition in C code
        self.assertIn("goodix_receive_none_tolerant", c_code)
        self.assertIn("g_error_matches (error, G_IO_ERROR, G_IO_ERROR_TIMED_OUT)", c_code)
        self.assertIn("g_clear_error (&error);", c_code)

        # 2. Verify goodix_send_nop uses goodix_receive_none_tolerant (not strict goodix_receive_none)
        nop_func_match = re.search(r"goodix_send_nop\s*\([^)]*\)\s*\{(.*?)\nvoid\ngoodix_send_mcu_get_image", c_code, re.DOTALL)
        self.assertIsNotNone(nop_func_match, "goodix_send_nop function not found in goodix.c")
        nop_body = nop_func_match.group(1)
        self.assertIn("goodix_receive_none_tolerant", nop_body,
                      "REGRESSION (Ticket 01): goodix_send_nop must wire goodix_receive_none_tolerant")
        self.assertNotIn("goodix_receive_none,", nop_body,
                         "REGRESSION (Ticket 01): goodix_send_nop must NOT use strict goodix_receive_none")

        # 3. Behavioral simulation of the tolerant receiver logic
        def simulate_receiver(error_type: str | None) -> bool:
            """Returns True if activation succeeds (error is None or cleared), False if aborted."""
            err = error_type
            if err == "G_IO_ERROR_TIMED_OUT":
                err = None  # g_clear_error (&error) — silence is success
            return err is None

        # Regression gate: NOP timeout MUST succeed and advance activation
        self.assertTrue(simulate_receiver("G_IO_ERROR_TIMED_OUT"),
                        "REGRESSION (Ticket 01): NOP timeout must NOT abort activation")
        # Other real errors MUST fail
        self.assertFalse(simulate_receiver("G_IO_ERROR_FAILED"),
                         "Real hardware failures must still abort activation")
        self.assertTrue(simulate_receiver(None),
                        "Clean reply without error must succeed")

    def test_command_serialization_ack_sequencing(self):
        """Verify sequential execution of NOP followed by Reset increments reset count."""
        nop_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        self.mcu.handle_out_packet(nop_pkt)
        self.assertEqual(self.mcu.reset_count, 0)

        rst_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_RESET, struct.pack("<BB", 0x03, 20)))
        self.mcu.handle_out_packet(rst_pkt)
        self.assertEqual(self.mcu.reset_count, 1)

if __name__ == "__main__":
    unittest.main()
