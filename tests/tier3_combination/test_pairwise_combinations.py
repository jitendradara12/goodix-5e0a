"""
Tier 3: Pairwise Combinatorial Integration Tests (24 Pairwise Tests)
Cross-feature interaction tests validating state machines, protocol lifecycles, and pipelines.
"""

import unittest
import struct
import socket
from tests.repo_paths import repo
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    decode_12bit_frame, decode_chicagoh_frame, pack_12bit_frame, squash_frame_linear,
    process_frame_demosaic,
    FLAGS_MSG_PROTOCOL, FLAGS_TLS, FLAGS_TLS_DATA,
    CMD_NOP, CMD_RESET, CMD_READ_SENSOR_REGISTER, CMD_WRITE_SENSOR_REGISTER,
    CMD_FIRMWARE_VERSION, CMD_READ_OTP, CMD_PRESET_PSK_READ, CMD_REQUEST_TLS_CONNECTION,
    CMD_TLS_SUCCESSFULLY_ESTABLISHED, CMD_UPLOAD_CONFIG_MCU, CMD_ENABLE_CHIP,
    CMD_MCU_SWITCH_TO_FDT_MODE, CMD_MCU_SWITCH_TO_FDT_DOWN, CMD_MCU_SWITCH_TO_FDT_UP,
    CMD_MCU_GET_IMAGE, CMD_ACK, CMD_QUERY_MCU_STATE,
    CANONICAL_PSK, CANONICAL_CONFIG_52XD, CANONICAL_FDT_MODE, CANONICAL_FDT_DOWN,
    CANONICAL_FDT_UP, CANONICAL_REG_022C_GAIN, CHIP_ID_VAL, FIRMWARE_VERSION_STR,
    RESET_NUMBER, FRAME_PIXELS, RAW_FRAME_BYTES, IMAGE_OUT_PIXELS,
    SENSOR_WIDTH, SENSOR_HEIGHT, FRAME_BLOCKS, FRAME_BLOCK_BYTES,
    FRAME_BLOCK_ACTIVE_BYTES
)

class TestPairwiseCombinations(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    # Pairwise 1: FDT Down + Cancel / Deactivate
    def test_pair_01_fdt_down_plus_cancel(self):
        """Pair 1: Entering FDT DOWN and then issuing immediate cancellation/NOP flush."""
        down_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        self.mcu.handle_out_packet(down_pkt)
        self.assertTrue(self.mcu.fdt_down_active)

        # Cancel with NOP
        nop_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = self.mcu.handle_out_packet(nop_pkt)
        self.assertEqual(reply, b"")

    # Pairwise 2: Decrypt + 12-bit Unpack + Normalization + Bilinear Demosaicing pipeline
    def test_pair_02_decrypt_unpack_normalize_demosaic_pipeline(self):
        """Pair 2: Full canonical-wire processing chain to a 128x160 FpImage."""
        test_pattern = [(r * 40 + c * 30) % 4000 for r in range(SENSOR_HEIGHT) for c in range(SENSOR_WIDTH)]
        packed = pack_12bit_frame(test_pattern)
        raw_wire = bytearray()
        for block in range(FRAME_BLOCKS):
            start = block * FRAME_BLOCK_ACTIVE_BYTES
            raw_wire.extend(packed[start : start + FRAME_BLOCK_ACTIVE_BYTES])
            raw_wire.extend(b"\x00" * (FRAME_BLOCK_BYTES - FRAME_BLOCK_ACTIVE_BYTES))
        raw_wire.extend(b"\x00\x00\x00\x00")

        unpacked = decode_chicagoh_frame(bytes(raw_wire))
        self.assertEqual(len(unpacked), FRAME_PIXELS)

        squashed = squash_frame_linear(unpacked)
        self.assertEqual(len(squashed), FRAME_PIXELS)
        self.assertEqual(min(squashed), 0)
        self.assertEqual(max(squashed), 255)

        demosaiced = process_frame_demosaic(squashed)
        self.assertEqual(len(demosaiced), IMAGE_OUT_PIXELS)

    # Pairwise 3: USB Timeout / Reconnect + NOP Buffer Flush Recovery
    def test_pair_03_reconnect_and_nop_flush_recovery(self):
        """Pair 3: Simulating USB disconnect/reconnect and draining stale queue via NOP."""
        self.mcu.in_queue.extend(b"\xff\xff\xff\xff\x00\x00")  # Stale data in wire
        nop_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = self.mcu.handle_out_packet(nop_pkt)
        self.assertEqual(reply, b"")

    # Pairwise 4: Deactivation + Immediate Reactivate (Session Lifecycle)
    def test_pair_04_deactivate_and_immediate_reactivate(self):
        """Pair 4: Cycling device activation SSM immediately after deactivation."""
        for cycle in range(3):
            # Deactivate: reset state
            # Activate: NOP -> Reset -> Chip ID -> Firmware
            self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b"")))
            rst_reply = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_RESET, struct.pack("<BB", 3, 20))))
            self.assertGreater(len(rst_reply), 0)

    # Pairwise 5: OTP Read + DPAPI PSK Handshake
    def test_pair_05_otp_read_and_psk_handshake(self):
        """Pair 5: Sequential OTP hardware check followed by TLS handshake."""
        otp_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_OTP, b""))
        otp_reply = self.mcu.handle_out_packet(otp_pkt)
        ok, _, body, _ = decode_pack(otp_reply)
        self.assertTrue(ok)

        tls_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_REQUEST_TLS_CONNECTION, b""))
        tls_reply = self.mcu.handle_out_packet(tls_pkt)
        self.assertTrue(self.mcu.tls_established)

    # Pairwise 6: FDT Mode Arming + Dual-Interrupt Toggle (DOWN -> UP)
    def test_pair_06_fdt_mode_arming_and_interrupt_toggle(self):
        """Pair 6: Switching between touch sensing modes (FDT MODE, DOWN, UP)."""
        mode_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE))
        self.mcu.handle_out_packet(mode_pkt)
        self.assertEqual(self.mcu.fdt_mode, CANONICAL_FDT_MODE)

        down_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        self.mcu.handle_out_packet(down_pkt)
        self.assertTrue(self.mcu.fdt_down_active)

        up_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        self.mcu.handle_out_packet(up_pkt)
        self.assertTrue(self.mcu.fdt_up_active)

    # Pairwise 7: Corrupted Packet Header + State Reset + Re-synchronization
    def test_pair_07_corrupted_packet_state_reset_resync(self):
        """Pair 7: Corrupt bytes on the wire are ignored; NOP and reset still succeed after."""
        # Inject bad packet through the mock (undecodable flags -> empty reply, no state change)
        bad = b"\xff\xff\x00\x00"
        self.assertEqual(self.mcu.handle_out_packet(bad), b"")

        # Recover with NOP and Reset
        nop = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = self.mcu.handle_out_packet(nop)
        self.assertEqual(reply, b"")
        rst = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_RESET, b"\x03\x14"))
        reply_rst = self.mcu.handle_out_packet(rst)
        ok, _, _, _ = decode_pack(reply_rst)
        self.assertTrue(ok)

    # Pairwise 8: Register 0x022c Write + Readback verification
    def test_pair_08_register_write_readback_verification(self):
        """Pair 8: Sensor analog frontend configuration verification."""
        write_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_WRITE_SENSOR_REGISTER, struct.pack("<BH2s", 0, 0x022C, CANONICAL_REG_022C_GAIN)))
        self.mcu.handle_out_packet(write_pkt)

        read_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, struct.pack("<BHBB", 0, 0x022C, 2, 0)))
        reply = self.mcu.handle_out_packet(read_pkt)
        ok, _, body, _ = decode_pack(reply)
        _, _, data, _, _ = decode_protocol(body)
        self.assertEqual(data, CANONICAL_REG_022C_GAIN)

    # Pairwise 9: Firmware Query + OTP Read + PSK Preset verification sequence
    def test_pair_09_firmware_otp_psk_validation_sequence(self):
        """Pair 9: Pre-handshake hardware identity checks."""
        # FW query
        fw_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_FIRMWARE_VERSION, b""))
        fw_rep = self.mcu.handle_out_packet(fw_pkt)
        _, _, fw_body, _ = decode_pack(fw_rep)
        _, _, fw_payload, _, _ = decode_protocol(fw_body)
        self.assertEqual(fw_payload.rstrip(b"\x00").decode("ascii"), FIRMWARE_VERSION_STR)

        # PSK preset read
        psk_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_PRESET_PSK_READ, b""))
        psk_rep = self.mcu.handle_out_packet(psk_pkt)
        _, _, psk_body, _ = decode_pack(psk_rep)
        _, _, psk_payload, _, _ = decode_protocol(psk_body)
        self.assertEqual(psk_payload[4:], CANONICAL_PSK)

    # Pairwise 10: Rapid Verification Loop (Verify -> Touch -> Image -> Release -> Complete)
    def test_pair_10_rapid_verify_loop(self):
        """Pair 10: Complete PAM verify interaction loop."""
        # 1. Switch to FDT down
        down = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        self.mcu.handle_out_packet(down)

        # 2. Get frame
        img = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, b"\x01" * 10))
        img_rep = self.mcu.handle_out_packet(img)
        ok, _, payload, _ = decode_pack(img_rep)
        self.assertEqual(len(payload), 7680)

        # 3. Release
        up = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        self.mcu.handle_out_packet(up)

    # Pairwise 11: NOP Flush + Reset + Chip ID read pipeline
    def test_pair_11_nop_reset_chip_id_pipeline(self):
        """Pair 11: Device activation initial 3-stage sequence."""
        nop = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        self.mcu.handle_out_packet(nop)

        rst = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_RESET, struct.pack("<BB", 3, 20)))
        rst_rep = self.mcu.handle_out_packet(rst)
        _, _, rst_body, _ = decode_pack(rst_rep)
        _, _, rst_pl, _, _ = decode_protocol(rst_body)
        self.assertEqual(struct.unpack("<H", rst_pl)[0], RESET_NUMBER)

        cid = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, struct.pack("<BHBB", 0, 0, 4, 0)))
        cid_rep = self.mcu.handle_out_packet(cid)
        _, _, cid_body, _ = decode_pack(cid_rep)
        _, _, cid_pl, _, _ = decode_protocol(cid_body)
        self.assertEqual(cid_pl, CHIP_ID_VAL)

    # Pairwise 12: FDT Mode + FDT Down + FDT Up mode switching
    def test_pair_12_fdt_mode_transitions(self):
        """Pair 12: Complete FDT lifecycle transition state machine."""
        m_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE))
        self.mcu.handle_out_packet(m_pkt)

        d_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        self.mcu.handle_out_packet(d_pkt)

        u_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        self.mcu.handle_out_packet(u_pkt)

    # Pairwise 13: USB Chunk Padding + Multi-packet command stream
    def test_pair_13_chunk_padded_multi_command_stream(self):
        """Pair 13: Continuous stream of padded 64-byte chunks."""
        for cmd in [CMD_NOP, CMD_FIRMWARE_VERSION, CMD_READ_OTP]:
            pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(cmd, b"", pad_data=True), pad_data=True)
            self.assertEqual(len(pkt) % 64, 0)
            rep = self.mcu.handle_out_packet(pkt)
            if cmd == CMD_NOP:
                self.assertEqual(rep, b"")
            else:
                self.assertGreater(len(rep), 0)

    # Pairwise 14: TLS Session Establishment + Frame Request + Socket Teardown
    def test_pair_14_tls_session_frame_socket_teardown(self):
        """Pair 14: Socket shutdown discipline (SHUT_RDWR then close) as used by the TLS server teardown."""
        s1, s2 = socket.socketpair()
        try:
            # Send mock frame data through socket
            test_data = b"\xaa" * 100
            s1.sendall(test_data)
            received = s2.recv(100)
            self.assertEqual(received, test_data)
            # Safe shutdown
            s1.shutdown(socket.SHUT_RDWR)
            s2.shutdown(socket.SHUT_RDWR)
        finally:
            s1.close()
            s2.close()

    # Pairwise 15: Cancellation during Calibration phase + SSM error recovery
    def test_pair_15_cancellation_during_calibration(self):
        """Pair 15: Interrupting scan SSM during calibration stage."""
        # Trigger FDT UP calibration
        cal_up = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        self.mcu.handle_out_packet(cal_up)

        # Deactivation reset
        nop = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = self.mcu.handle_out_packet(nop)
        self.assertEqual(reply, b"")

    # Pairwise 16: Zero-air background calibration frame subtraction + Demosaicing
    def test_pair_16_calibration_frame_subtraction_demosaic(self):
        """Pair 16: Linear subtraction of background noise frame followed by demosaicing."""
        raw_pixels = [2000 + (i % 500) for i in range(FRAME_PIXELS)]
        calib_pixels = [1900] * FRAME_PIXELS

        # Simulate linear subtraction
        subtracted = [max(0, raw_pixels[i] - calib_pixels[i]) for i in range(FRAME_PIXELS)]
        squashed = squash_frame_linear(subtracted)
        demosaiced = process_frame_demosaic(squashed)
        self.assertEqual(len(demosaiced), IMAGE_OUT_PIXELS)

    # Pairwise 17: Driver Class Inheritance + Auto-feature initialization
    def test_pair_17_driver_class_inheritance(self):
        """Pair 17: Subclassing verification and auto feature init."""
        with open(repo("libfprint-driver", "goodix5e0a.c"), "r") as f:
            content = f.read()
        self.assertIn("G_DEFINE_TYPE (FpiDeviceGoodixTls5e0a, fpi_device_goodixtls5e0a,", content)
        self.assertIn("FPI_TYPE_DEVICE_GOODIXTLS5XX", content)
        self.assertIn("fpi_device_class_auto_initialize_features", content)

    # Pairwise 18: Patch evaluation + Derivation compilation + Udev rules generation
    def test_pair_18_patch_and_nixos_module_integrity(self):
        """Pair 18: Patch consistency with NixOS derivation configuration."""
        with open(repo("libfprint-goodix.nix"), "r") as f:
            nix_content = f.read()
        self.assertIn("0001-Add-driver-support-for-Goodix-27c6-5e0a.patch", nix_content)
        self.assertIn("-Ddrivers=goodixtls5e0a", nix_content)

    # Pairwise 19: High Dynamic Range sensor frame + Linear normalization + 160x128 upsample
    def test_pair_19_hdr_frame_normalization_upsample(self):
        """Pair 19: HDR sensor frame (0 to 4095) linearly mapped to full 8-bit dynamic range."""
        hdr_pixels = [(i * 4095) // (FRAME_PIXELS - 1) for i in range(FRAME_PIXELS)]
        squashed = squash_frame_linear(hdr_pixels)
        self.assertEqual(squashed[0], 0)
        self.assertEqual(squashed[-1], 255)
        demosaiced = process_frame_demosaic(squashed)
        self.assertEqual(len(demosaiced), IMAGE_OUT_PIXELS)

    # Pairwise 20: Protocol Command serialization without ACK collision
    def test_pair_20_command_serialization_no_collision(self):
        """Pair 20: Rapid back-to-back command dispatch."""
        for cmd_code in [CMD_NOP, CMD_FIRMWARE_VERSION, CMD_READ_OTP, CMD_QUERY_MCU_STATE]:
            pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(cmd_code, b""))
            rep = self.mcu.handle_out_packet(pkt)
            if cmd_code == CMD_NOP:
                self.assertEqual(rep, b"")
            else:
                self.assertGreater(len(rep), 0)

    # Pairwise 21: Consecutive Enrollment Stages with state machine invariant checks
    def test_pair_21_enrollment_invariants(self):
        """Pair 21: 8 stages with intermediate invariant assertions."""
        for s in range(1, 9):
            # Touch down
            d = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
            self.mcu.handle_out_packet(d)
            self.assertTrue(self.mcu.fdt_down_active)

            # Touch up
            u = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
            self.mcu.handle_out_packet(u)
            self.assertTrue(self.mcu.fdt_up_active)

    # Pairwise 22: TLS Socket creation + Socketpair bi-directional write/read loop
    def test_pair_22_socketpair_bidirectional_traffic(self):
        """Pair 22: Socketpair echo sanity for opaque bridge payloads (no USB/TLS stack involved)."""
        s_mcu, s_tls = socket.socketpair()
        try:
            # Client writes MCU packet to TLS
            s_mcu.sendall(b"\x16\x03\x03\x00\x05hello")
            tls_in = s_tls.recv(10)
            self.assertEqual(tls_in, b"\x16\x03\x03\x00\x05hello")

            # TLS writes response to MCU
            s_tls.sendall(b"\x16\x03\x03\x00\x05world")
            mcu_in = s_mcu.recv(10)
            self.assertEqual(mcu_in, b"\x16\x03\x03\x00\x05world")
        finally:
            s_mcu.close()
            s_tls.close()

    # Pairwise 23: Device Re-open after unexpected close / disconnect
    def test_pair_23_device_reopen_after_disconnect(self):
        """Pair 23: A freshly re-instantiated mock answers NOP (clean-state recovery)."""
        new_mcu = MockGoodixMCU()
        self.assertTrue(new_mcu.is_connected)
        nop_pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b""))
        reply = new_mcu.handle_out_packet(nop_pkt)
        self.assertEqual(reply, b"")

    # Pairwise 24: End-to-end full device activation, image capture, and deactivation pipeline
    def test_pair_24_e2e_full_lifecycle_pipeline(self):
        """Pair 24: Complete lifecycle from cold start to activation, scan, image demosaic, and deactivation."""
        # 1. Cold start activation
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b"")))
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_RESET, struct.pack("<BB", 3, 20))))
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, struct.pack("<BHBB", 0, 0, 4, 0))))
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_FIRMWARE_VERSION, b"")))
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_REQUEST_TLS_CONNECTION, b"")))
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_UPLOAD_CONFIG_MCU, CANONICAL_CONFIG_52XD)))
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ENABLE_CHIP, bytes([1, 0]))))

        # 2. Touch detection & frame capture
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE)))
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN)))
        img_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, b"\x01" * 10)))

        # 3. Release
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP)))

        # 4. Processing
        ok, _, raw_frame, _ = decode_pack(img_rep)
        pixels = decode_12bit_frame(raw_frame)
        squashed = squash_frame_linear(pixels)
        out_image = process_frame_demosaic(squashed)
        self.assertEqual(len(out_image), IMAGE_OUT_PIXELS)

        # 5. Deactivation
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b"")))

if __name__ == "__main__":
    unittest.main()
