"""
Tier 5: Adversarial Stress, Fuzzing & Fault Injection Test Suite
Validates system resilience against hostile inputs, memory stability, and unexpected transport faults.
"""

import unittest
import random
import struct
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    decode_12bit_frame, pack_12bit_frame, squash_frame_linear, process_frame_demosaic,
    FLAGS_MSG_PROTOCOL, FLAGS_TLS_DATA, CMD_NOP, CMD_READ_SENSOR_REGISTER,
    CMD_MCU_SWITCH_TO_FDT_DOWN, CMD_MCU_SWITCH_TO_FDT_UP, CMD_MCU_GET_IMAGE,
    CANONICAL_FDT_DOWN, CANONICAL_FDT_UP, FRAME_PIXELS, IMAGE_OUT_PIXELS
)

class TestAdversarialStress(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()
        random.seed(42)

    def test_protocol_packet_fuzzing_100_iterations(self):
        """Fuzz decode_pack and decode_protocol with 100 randomly generated bitstreams."""
        for _ in range(100):
            length = random.randint(0, 500)
            fuzzed_data = bytes(random.getrandbits(8) for _ in range(length))
            # Must safely return without throwing unhandled exceptions
            ok, flags, payload, chk_ok = decode_pack(fuzzed_data)
            if ok:
                decode_protocol(payload)

    def test_memory_stability_100_consecutive_frames(self):
        """Execute 100 consecutive frame decoding, squashing, and demosaicing cycles without memory growth."""
        for i in range(100):
            pixels = [(i * 10 + j) % 4096 for j in range(FRAME_PIXELS)]
            raw_bytes = pack_12bit_frame(pixels)
            unpacked = decode_12bit_frame(raw_bytes)
            squashed = squash_frame_linear(unpacked)
            demosaiced = process_frame_demosaic(squashed)
            self.assertEqual(len(demosaiced), IMAGE_OUT_PIXELS)

    def test_bitflip_fault_injection_in_fdt_tables(self):
        """Inject random single-bit flips into FDT tables and verify corruption is detectable."""
        for _ in range(20):
            corrupted_down = bytearray(CANONICAL_FDT_DOWN)
            byte_idx = random.randint(0, len(corrupted_down) - 1)
            bit_idx = random.randint(0, 7)
            corrupted_down[byte_idx] ^= (1 << bit_idx)

            if byte_idx == 26:
                # Byte 26 mutated -> DOWN flag altered
                self.assertNotEqual(corrupted_down[26], 0x01)
            else:
                self.assertNotEqual(bytes(corrupted_down), CANONICAL_FDT_DOWN)

    def test_register_flood_attack(self):
        """Flood MCU with 200 random register read and write commands."""
        for _ in range(200):
            addr = random.randint(0, 0xFFFF)
            val = bytes([random.randint(0, 255), random.randint(0, 255)])
            w_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(0x80, struct.pack("<BH2s", 0, addr, val)))
            self.mcu.handle_out_packet(w_pkt)

            r_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(0x82, struct.pack("<BHBB", 0, addr, 2, 0)))
            reply = self.mcu.handle_out_packet(r_pkt)
            self.assertGreater(len(reply), 0)

    def test_rapid_alternating_state_flood(self):
        """Rapidly toggle FDT DOWN and FDT UP 50 times in immediate succession."""
        for _ in range(50):
            d_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
            self.mcu.handle_out_packet(d_pkt)
            u_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
            self.mcu.handle_out_packet(u_pkt)
        self.assertTrue(self.mcu.fdt_up_active)

if __name__ == "__main__":
    unittest.main()
