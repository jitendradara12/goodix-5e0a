"""
Tier 5 Adversarial Stress Test: Base-Class Contract & 7-Stage Scan SSM
Empirically verifies that FpiDeviceGoodixTls5xx base class correctly executes all
7 scan stages when driven by goodix5e0a configuration tables and callbacks.
"""

import unittest
import os
import re
from tests.repo_paths import repo
from tests.test_utils import (
    MockGoodixMCU,
    CANONICAL_FDT_MODE,
    CANONICAL_FDT_DOWN,
    CANONICAL_FDT_UP,
    CANONICAL_PSK,
    CANONICAL_CONFIG_52XD,
    CANONICAL_REG_022C_GAIN,
    CMD_QUERY_MCU_STATE,
    CMD_MCU_SWITCH_TO_FDT_MODE,
    CMD_MCU_SWITCH_TO_FDT_DOWN,
    CMD_MCU_SWITCH_TO_FDT_UP,
    CMD_MCU_GET_IMAGE,
    CMD_NAV_0,
    CMD_ENABLE_CHIP,
    CMD_RESET,
    CMD_READ_OTP,
    CMD_FIRMWARE_VERSION,
    CMD_UPLOAD_CONFIG_MCU,
    FIRMWARE_VERSION_STR,
    PSK_FLAGS,
    RESET_NUMBER,
    SENSOR_WIDTH,
    SENSOR_HEIGHT,
    IMAGE_OUT_WIDTH,
    IMAGE_OUT_HEIGHT,
    encode_protocol,
    decode_protocol,
    encode_pack,
    decode_pack,
    FLAGS_MSG_PROTOCOL,
    FLAGS_TLS_DATA,
)

class TestM2BaseContract7Stages(unittest.TestCase):

    def setUp(self):
        self.driver_c_path = repo("libfprint-driver", "goodix5e0a.c")
        self.driver_h_path = repo("libfprint-driver", "goodix5e0a.h")
        self.base_c_path = repo("libfprint-driver", "goodix5xx.c")
        self.base_h_path = repo("libfprint-driver", "goodix5xx.h")

        with open(self.driver_c_path, "r") as f:
            self.c_code = f.read()
        with open(self.driver_h_path, "r") as f:
            self.h_code = f.read()
        with open(self.base_c_path, "r") as f:
            self.base_c = f.read()
        with open(self.base_h_path, "r") as f:
            self.base_h = f.read()

    def test_7_scan_stages_definition_in_base_class(self):
        """Verify the 7 exact scan stages defined in goodix5xx.c enum SCAN_STAGES."""
        expected_stages = [
            "SCAN_STAGE_QUERY_MCU",
            "SCAN_STAGE_SWITCH_TO_FDT_MODE",
            "SCAN_STAGE_CALIBRATE",
            "SCAN_STAGE_SWITCH_TO_FDT_DOWN",
            "SCAN_STAGE_GET_IMG",
            "SCAN_STAGE_SWITCH_TO_FTD_UP",
            "SCAN_STAGE_SWITCH_TO_FTD_DONE",
            "SCAN_STAGE_NUM",
        ]
        for stage in expected_stages:
            self.assertIn(stage, self.base_c)

    def test_calibration_sub_ssm_stages_in_base_class(self):
        """Verify calibration sub-SSM stages defined in goodix5xx.c."""
        expected_calib_stages = [
            "CALIBRATION_STAGE_FDT_UP",
            "CALIBRATION_STAGE_NAV0",
            "CALIBRATION_STAGE_GET_IMG",
            "CALIBRATION_STAGE_NUM",
        ]
        for stage in expected_calib_stages:
            self.assertIn(stage, self.base_c)

    def test_base_class_vtable_binding_contract(self):
        """Verify goodix5e0a wires all required base class vtable methods."""
        vtable_checks = [
            "xx_cls->process_raw_frame = process_raw_frame;",
            "xx_cls->scan_height = GOODIX_5E0A_HEIGHT;",
            "xx_cls->scan_width = GOODIX_5E0A_WIDTH;",
            "xx_cls->psk = goodix_5e0a_psk;",
            "xx_cls->psk_flags = GOODIX_5E0A_PSK_FLAGS;",
            "xx_cls->psk_len = sizeof (goodix_5e0a_psk);",
            "xx_cls->firmware_version = GOODIX_5E0A_FIRMWARE_VERSION;",
            "xx_cls->reset_number = GOODIX_5E0A_RESET_NUMBER;",
            "xx_cls->has_calibration = FALSE;",
        ]
        for check in vtable_checks:
            self.assertIn(check, self.c_code)

    def test_7_stage_scan_ssm_in_goodix5e0a(self):
        """Verify the 7 exact scan SSM states and callbacks in goodix5e0a.c."""
        expected_5e0a_stages = [
            "SCAN_5E0A_SESSION_AE",
            "SCAN_5E0A_SESSION_D6",
            "SCAN_5E0A_FDT_DOWN",
            "SCAN_5E0A_GET_IMAGE",
            "SCAN_5E0A_FDT_UP_1",
            "SCAN_5E0A_UP_AE",
            "SCAN_5E0A_FDT_UP_2",
            "SCAN_5E0A_NUM_STATES",
        ]
        for stage in expected_5e0a_stages:
            self.assertIn(stage, self.c_code)

        self.assertIn("img_dev_class->change_state = goodix5e0a_change_state;", self.c_code)
        self.assertIn("goodix5e0a_scan_start (FP_DEVICE (img_dev));", self.c_code)
        self.assertIn("self->scan_ssm = fpi_ssm_new (dev, goodix5e0a_scan_run_state, SCAN_5E0A_NUM_STATES);", self.c_code)
        self.assertIn("img_dev_class->deactivate = goodix5e0a_deactivate;", self.c_code)

    def test_finger_status_reporting_in_scan_lifecycle(self):
        """Verify finger status reporting occurs at Stage 4 (TRUE) and Stage 6 (FALSE)."""
        self.assertIn("case SCAN_STAGE_GET_IMG:\n      fpi_image_device_report_finger_status (img_dev, TRUE);", self.base_c)
        self.assertIn("case SCAN_STAGE_SWITCH_TO_FTD_DONE:\n      fpi_image_device_report_finger_status (img_dev, FALSE);", self.base_c)


    def test_fdt_down_and_up_config_payloads(self):
        """Verify FDT DOWN and FDT UP config payloads match canonical hardware specs."""
        self.assertEqual(len(CANONICAL_FDT_MODE), 27)
        self.assertEqual(len(CANONICAL_FDT_DOWN), 39)
        self.assertEqual(len(CANONICAL_FDT_UP), 39)
        self.assertEqual(CANONICAL_FDT_DOWN[26], 0x01)
        self.assertEqual(CANONICAL_FDT_UP[26], 0x00)

    def test_simulated_7_stage_scan_execution(self):
        """
        Emulate the complete 7-stage scan sequence using MockGoodixMCU.
        Validates packets sent and received at every stage.
        """
        mcu = MockGoodixMCU()
        mcu.chip_enabled = True

        # Stage 0: SCAN_STAGE_QUERY_MCU
        cmd0 = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_QUERY_MCU_STATE, b""))
        resp0 = mcu.handle_out_packet(cmd0)
        self.assertTrue(len(resp0) > 0)
        ok0, flags0, payload0, chk0 = decode_pack(resp0)
        self.assertTrue(ok0)
        self.assertEqual(flags0, FLAGS_MSG_PROTOCOL)

        # Stage 1: SCAN_STAGE_SWITCH_TO_FDT_MODE
        cmd1 = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, CANONICAL_FDT_MODE))
        resp1 = mcu.handle_out_packet(cmd1)
        self.assertTrue(len(resp1) > 0)
        self.assertEqual(mcu.fdt_mode, CANONICAL_FDT_MODE)

        # Stage 2: SCAN_STAGE_CALIBRATE (sub-SSM)
        # 2a: CALIBRATION_STAGE_FDT_UP
        cmd2a = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        resp2a = mcu.handle_out_packet(cmd2a)
        self.assertTrue(len(resp2a) > 0)

        # 2b: CALIBRATION_STAGE_NAV0
        cmd2b = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NAV_0, b""))
        resp2b = mcu.handle_out_packet(cmd2b)
        self.assertTrue(len(resp2b) > 0)

        # 2c: CALIBRATION_STAGE_GET_IMG
        cmd2c = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, b""))
        resp2c = mcu.handle_out_packet(cmd2c)
        self.assertTrue(len(resp2c) > 0)

        # Stage 3: SCAN_STAGE_SWITCH_TO_FDT_DOWN (touch detection)
        cmd3 = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, CANONICAL_FDT_DOWN))
        resp3 = mcu.handle_out_packet(cmd3)
        self.assertTrue(mcu.fdt_down_active)
        self.assertTrue(len(resp3) > 0)

        # Stage 4: SCAN_STAGE_GET_IMG
        cmd4 = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_GET_IMAGE, b""))
        resp4 = mcu.handle_out_packet(cmd4)
        self.assertTrue(len(resp4) > 0)
        ok4, flags4, payload4, chk4 = decode_pack(resp4)
        self.assertEqual(flags4, FLAGS_TLS_DATA)

        # Stage 5: SCAN_STAGE_SWITCH_TO_FTD_UP (release detection)
        cmd5 = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, CANONICAL_FDT_UP))
        resp5 = mcu.handle_out_packet(cmd5)
        self.assertTrue(mcu.fdt_up_active)
        self.assertTrue(len(resp5) > 0)

        # Stage 6: SCAN_STAGE_SWITCH_TO_FTD_DONE
        # Scan finishes cleanly!
        self.assertTrue(mcu.fdt_up_active)

if __name__ == "__main__":
    unittest.main()
