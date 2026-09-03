"""
Tier 1 - Milestone 2: Modular Base-Class Driver Refactoring (Ponytail Standard)
Validates that goodix5e0a.c and goodix5e0a.h adhere strictly to FpiDeviceGoodixTls5xx
base-class derivations, minimal code footprints, and Ponytail invariants.
"""

import unittest
import os
import re

class TestM2DriverRefactoring(unittest.TestCase):

    def setUp(self):
        self.driver_c_path = "/tmp/libfprint-goodix/libfprint/drivers/goodixtls/goodix5e0a.c"
        self.driver_h_path = "/tmp/libfprint-goodix/libfprint/drivers/goodixtls/goodix5e0a.h"
        self.local_c_path = "/home/sastauser/code/temp/goodix/libfprint-driver/goodix5e0a.c"
        self.local_h_path = "/home/sastauser/code/temp/goodix/libfprint-driver/goodix5e0a.h"

        with open(self.driver_c_path, "r") as f:
            self.c_content = f.read()
        with open(self.driver_h_path, "r") as f:
            self.h_content = f.read()

    def test_gtype_derives_from_goodixtls5xx(self):
        """Verify driver derives directly from FpiDeviceGoodixTls5xx base class."""
        self.assertIn("G_DECLARE_FINAL_TYPE (FpiDeviceGoodixTls5e0a, fpi_device_goodixtls5e0a, FPI,\n                      DEVICE_GOODIXTLS5E0A, FpiDeviceGoodixTls5xx);", self.c_content)
        self.assertIn("G_DEFINE_TYPE (FpiDeviceGoodixTls5e0a, fpi_device_goodixtls5e0a,\n               FPI_TYPE_DEVICE_GOODIXTLS5XX);", self.c_content)

    def test_vtable_assignments_exactness(self):
        """Verify all vtable members are correctly wired in fpi_device_goodixtls5e0a_class_init."""
        expected_vtable_entries = [
            "xx_cls->get_mcu_cfg = get_mcu_config;",
            "xx_cls->get_fdt_down_cfg = get_fdt_down_config;",
            "xx_cls->get_fdt_up_cfg = get_fdt_up_config;",
            "xx_cls->process_raw_frame = process_raw_frame;",
            "xx_cls->scan_height = GOODIX_5E0A_HEIGHT;",
            "xx_cls->scan_width = GOODIX_5E0A_WIDTH;",
            "xx_cls->psk = goodix_5e0a_psk;",
            "xx_cls->psk_flags = GOODIX_5E0A_PSK_FLAGS;",
            "xx_cls->psk_len = sizeof (goodix_5e0a_psk);",
            "xx_cls->firmware_version = GOODIX_5E0A_FIRMWARE_VERSION;",
            "xx_cls->reset_number = GOODIX_5E0A_RESET_NUMBER;",
            "gx_class->interface = GOODIX_5E0A_INTERFACE;",
            "gx_class->ep_in = GOODIX_5E0A_EP_IN;",
            "gx_class->ep_out = GOODIX_5E0A_EP_OUT;",
            'dev_class->id = "goodixtls5e0a";',
            'dev_class->full_name = "Goodix TLS Fingerprint Sensor 5e0a";',
            "dev_class->type = FP_DEVICE_TYPE_USB;",
            "dev_class->id_table = goodix_5e0a_id_table;",
            "dev_class->nr_enroll_stages = 8;",
            "dev_class->scan_type = FP_SCAN_TYPE_PRESS;",
            "dev_class->temp_hot_seconds = -1;",
            "img_dev_class->activate = dev_activate;",
            "img_dev_class->bz3_threshold = 12;",
            "img_dev_class->img_width = GOODIX_5E0A_WIDTH * 2;",
            "img_dev_class->img_height = GOODIX_5E0A_HEIGHT * 2;",
        ]
        for entry in expected_vtable_entries:
            self.assertIn(entry, self.c_content, f"Missing vtable entry: {entry}")

    def test_no_change_state_override(self):
        """Verify goodix5e0a.c does NOT override change_state (delegating to base class scan SSM)."""
        self.assertNotIn("img_dev_class->change_state", self.c_content)
        self.assertNotIn("dev_change_state", self.c_content)

    def test_no_polling_or_custom_scan_ssm(self):
        """Verify no ad-hoc polling loops (g_timeout_add) or redundant scan state machines exist."""
        self.assertNotIn("g_timeout_add", self.c_content)
        self.assertNotIn("g_timeout_source_new", self.c_content)
        self.assertNotIn("scan_run_state", self.c_content)
        self.assertNotIn("usleep", self.c_content)

    def test_activation_ssm_structure(self):
        """Verify dev_activate implements 4-state SSM followed by TLS init and MCU config upload."""
        self.assertIn("enum activate_states {", self.c_content)
        self.assertIn("ACTIVATE_READ_AND_NOP,", self.c_content)
        self.assertIn("ACTIVATE_RESET,", self.c_content)
        self.assertIn("ACTIVATE_READ_CHIP_ID,", self.c_content)
        self.assertIn("ACTIVATE_CHECK_FW_VER,", self.c_content)
        self.assertIn("ACTIVATE_NUM_STATES,", self.c_content)

    def test_demosaicing_flags_and_dimensions(self):
        """Verify process_frame generates 160x128 image with FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED."""
        self.assertIn("fp_image_new (W, H)", self.c_content)
        self.assertIn("img->flags |= FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED;", self.c_content)

    def test_local_tree_synchronization(self):
        """Verify local driver tree in workspace matches active build tree exactly."""
        with open(self.local_c_path, "r") as f:
            local_c = f.read()
        with open(self.local_h_path, "r") as f:
            local_h = f.read()
        self.assertEqual(self.c_content, local_c, "goodix5e0a.c out of sync between build and repo")
        self.assertEqual(self.h_content, local_h, "goodix5e0a.h out of sync between build and repo")

if __name__ == "__main__":
    unittest.main()
