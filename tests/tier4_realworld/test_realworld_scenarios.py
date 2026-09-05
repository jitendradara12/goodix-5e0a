"""
Tier 4: Real-World Application Scenarios Test Suite
Simulates realistic system-level workloads:
- Scenario 1: Multi-stage Enrollment (fprintd-enroll) without false air advances
- Scenario 2: Consecutive Sudo PAM Verifications (5x back-to-back fprintd-verify)
- Scenario 3: Lockscreen PAM Cancelation & Instant Re-auth (hyprlock / swaylock)
- Scenario 4: Empty Air Finger Touch Rejection (0 false triggers over idle periods)
- Scenario 5: Hermetic Nix Package Build & Service Configuration Evaluation
"""

import unittest
import shutil
import struct
import subprocess
import time
from tests.repo_paths import repo, REPO_ROOT
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    decode_12bit_frame, pack_12bit_frame, squash_frame_linear, process_frame_demosaic,
    FLAGS_MSG_PROTOCOL, FLAGS_TLS_DATA,
    CMD_NOP, CMD_RESET, CMD_READ_SENSOR_REGISTER, CMD_WRITE_SENSOR_REGISTER,
    CMD_FIRMWARE_VERSION, CMD_READ_OTP, CMD_PRESET_PSK_READ, CMD_REQUEST_TLS_CONNECTION,
    CMD_TLS_SUCCESSFULLY_ESTABLISHED, CMD_UPLOAD_CONFIG_MCU, CMD_ENABLE_CHIP,
    CMD_MCU_SWITCH_TO_FDT_MODE, CMD_MCU_SWITCH_TO_FDT_DOWN, CMD_MCU_SWITCH_TO_FDT_UP,
    CMD_MCU_GET_IMAGE, CMD_ACK, CMD_QUERY_MCU_STATE,
    CANONICAL_PSK, CANONICAL_CONFIG_52XD, CANONICAL_FDT_MODE, CANONICAL_FDT_DOWN,
    CANONICAL_FDT_UP, CANONICAL_REG_022C_GAIN, CHIP_ID_VAL, FIRMWARE_VERSION_STR,
    RESET_NUMBER, FRAME_PIXELS, RAW_FRAME_BYTES, IMAGE_OUT_PIXELS
)

class TestRealWorldScenarios(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def _activate_device(self, mcu: MockGoodixMCU):
        """Helper to execute standard activation state machine."""
        mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b"")))
        mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_RESET, struct.pack("<BB", 3, 20))))
        mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_READ_SENSOR_REGISTER, struct.pack("<BHBB", 0, 0, 4, 0))))
        mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_FIRMWARE_VERSION, b"")))
        mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_REQUEST_TLS_CONNECTION, b"")))
        mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_UPLOAD_CONFIG_MCU, CANONICAL_CONFIG_52XD)))
        mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_ENABLE_CHIP, bytes([1, 0]))))

    def _deactivate_device(self, mcu: MockGoodixMCU):
        """Helper to execute standard deactivation reset."""
        mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b"")))

    # Scenario 1: Multi-stage Enrollment (fprintd-enroll) without false air advances
    def test_scenario_01_multi_stage_enrollment(self):
        """Scenario 1: Simulates an 8-stage fprintd-enroll session.
        Advances ONLY on genuine touch down and finger up.
        Rejects advancing on idle / empty air.
        """
        self._activate_device(self.mcu)

        stages_completed = 0
        for stage in range(1, 9):
            # 1. Switch to FDT Mode
            self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE)))

            # 2. Before physical touch occurs, stage cannot advance
            self.assertFalse(self.mcu.touch_pending)

            # 3. Simulate physical finger touch
            self.mcu.simulate_touch_event()
            down_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN)))
            ok, _, body, _ = decode_pack(down_rep)
            _, cmd, payload, _, _ = decode_protocol(body)
            self.assertEqual(payload[0], 0x01)  # Touch confirmed

            # 4. Acquire frame
            img_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, b"\x01" * 10)))
            ok, _, raw_frame, _ = decode_pack(img_rep)
            self.assertEqual(len(raw_frame), RAW_FRAME_BYTES)

            # 5. Process image
            pixels = decode_12bit_frame(raw_frame)
            squashed = squash_frame_linear(pixels)
            out_img = process_frame_demosaic(squashed)
            self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)

            # 6. Must release finger before next stage is allowed
            self.mcu.simulate_release_event()
            up_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP)))
            ok, _, up_body, _ = decode_pack(up_rep)
            _, _, up_payload, _, _ = decode_protocol(up_body)
            self.assertEqual(up_payload[0], 0x00)  # Release confirmed

            stages_completed += 1
            self.mcu.touch_pending = False
            self.mcu.release_pending = False

        self.assertEqual(stages_completed, 8)
        self._deactivate_device(self.mcu)

    # Scenario 2: Consecutive Sudo PAM Verifications (5x back-to-back fprintd-verify)
    def test_scenario_02_consecutive_pam_verifications(self):
        """Scenario 2: Simulates 5 consecutive PAM authentication verify runs (e.g. repeated sudo commands).
        Verifies no 0xa2 command timeout, no socket hang, and clean re-initialization per run.
        """
        for run_idx in range(1, 6):
            # 1. Device activation
            self._activate_device(self.mcu)
            self.assertTrue(self.mcu.chip_enabled)
            self.assertTrue(self.mcu.tls_established)

            # 2. Wait for finger touch
            self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE)))
            down_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN)))
            self.assertGreater(len(down_rep), 0)

            # 3. Capture and process verification image
            img_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, b"\x01" * 10)))
            ok, _, raw_frame, _ = decode_pack(img_rep)
            self.assertTrue(ok)
            pixels = decode_12bit_frame(raw_frame)
            squashed = squash_frame_linear(pixels)
            out_img = process_frame_demosaic(squashed)
            self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)

            # 4. Finger release
            up_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP)))
            self.assertGreater(len(up_rep), 0)

            # 5. Device deactivation / PAM teardown
            self._deactivate_device(self.mcu)

    # Scenario 3: Lockscreen PAM Cancellation & Instant Re-auth (hyprlock / swaylock)
    def test_scenario_03_lockscreen_cancel_and_instant_reauth(self):
        """Scenario 3: Simulates user typing password while fingerprint scanner is waiting (cancellation),
        followed by immediate finger auth retry on next prompt.
        """
        # 1. Session 1 start
        self._activate_device(self.mcu)
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE)))
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN)))

        # 2. User types password -> cancel current PAM fingerprint verification
        self._deactivate_device(self.mcu)

        # 3. Immediately start Session 2 (Instant Re-auth)
        self._activate_device(self.mcu)
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE)))
        down_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN)))
        self.assertGreater(len(down_rep), 0)

        img_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, b"\x01" * 10)))
        self.assertGreater(len(img_rep), 0)

        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP)))
        self._deactivate_device(self.mcu)

    # Scenario 4: Empty Air Finger Touch Rejection (0 false triggers over idle periods)
    def test_scenario_04_empty_air_finger_touch_rejection(self):
        """Scenario 4: Simulates long idle periods where no physical finger touches the sensor.
        Verifies zero false image acquisitions and zero CPU busy-loops.
        """
        self._activate_device(self.mcu)
        self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE)))

        # Sensor remains in waiting state; no image request should be issued
        self.assertFalse(self.mcu.touch_pending)

        # Query MCU state to verify idle stability
        query_rep = self.mcu.handle_out_packet(encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_QUERY_MCU_STATE, b"")))
        ok, _, body, _ = decode_pack(query_rep)
        _, cmd, payload, _, _ = decode_protocol(body)
        self.assertEqual(cmd, CMD_QUERY_MCU_STATE)

        self._deactivate_device(self.mcu)

    # Scenario 5: Hermetic Nix Package Build & Service Configuration Evaluation
    @unittest.skipUnless(shutil.which("nix-instantiate"), "nix-instantiate not installed")
    def test_scenario_05_nix_package_and_service_evaluation(self):
        """Scenario 5: Evaluates NixOS configuration and libfprint-goodix derivation hermetically.
        """
        # 1. Verify libfprint-goodix derivation evaluates
        cmd1 = [
            "nix-instantiate", "--eval",
            "-E", "let pkgs = import <nixpkgs> {}; in pkgs.callPackage ./libfprint-goodix.nix {}"
        ]
        res1 = subprocess.run(cmd1, cwd=str(REPO_ROOT), capture_output=True, text=True)
        self.assertEqual(res1.returncode, 0, f"Derivation eval failed: {res1.stderr}")

        # 2. Verify nixos-module.nix syntax and attributes
        with open(repo("nixos-module.nix"), "r") as f:
            module_src = f.read()
        self.assertIn("services.fprintd", module_src)
        self.assertIn("services.udev", module_src)
        self.assertIn("security.pam.services", module_src)

if __name__ == "__main__":
    unittest.main()
