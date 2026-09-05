"""
Tier 1 - Milestone 2: Modular Base-Class Driver Refactoring (Ponytail Standard)
Validates that goodix5e0a.c and goodix5e0a.h adhere strictly to FpiDeviceGoodixTls5xx
base-class derivations, minimal code footprints, and Ponytail invariants.
"""

import unittest
import os
import re
from tests.repo_paths import repo, BUILD_TREE

class TestM2DriverRefactoring(unittest.TestCase):

    def setUp(self):
        self.driver_c_path = repo("libfprint-driver", "goodix5e0a.c")
        self.driver_h_path = repo("libfprint-driver", "goodix5e0a.h")

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
            "xx_cls->process_raw_frame = process_raw_frame;",
            "xx_cls->scan_height = GOODIX_5E0A_HEIGHT;",
            "xx_cls->scan_width = GOODIX_5E0A_WIDTH;",
            "xx_cls->psk = goodix_5e0a_psk;",
            "xx_cls->psk_flags = GOODIX_5E0A_PSK_FLAGS;",
            "xx_cls->psk_len = sizeof (goodix_5e0a_psk);",
            "xx_cls->firmware_version = GOODIX_5E0A_FIRMWARE_VERSION;",
            "xx_cls->reset_number = GOODIX_5E0A_RESET_NUMBER;",
            "xx_cls->has_calibration = FALSE;",
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
            "img_dev_class->change_state = goodix5e0a_change_state;",
            "img_dev_class->deactivate = goodix5e0a_deactivate;",
            "img_dev_class->bz3_threshold = 12;",
            "img_dev_class->img_width = GOODIX_5E0A_SCALED_WIDTH;",
            "img_dev_class->img_height = GOODIX_5E0A_SCALED_HEIGHT;",
        ]
        for entry in expected_vtable_entries:
            self.assertIn(entry, self.c_content, f"Missing vtable entry: {entry}")

    def test_state_and_lifecycle_handlers(self):
        """Verify goodix5e0a.c implements state change and deactivation handlers."""
        self.assertIn("img_dev_class->change_state = goodix5e0a_change_state;", self.c_content)
        self.assertIn("img_dev_class->deactivate = goodix5e0a_deactivate;", self.c_content)

    def test_no_polling_loops(self):
        """Verify no ad-hoc polling loops (g_timeout_add) or usleep exist."""
        self.assertNotIn("g_timeout_add", self.c_content)
        self.assertNotIn("usleep", self.c_content)

    def test_activation_ssm_structure(self):
        """Verify dev_activate implements 5-state SSM followed by TLS init and MCU config upload."""
        self.assertIn("enum activate_states {", self.c_content)
        self.assertIn("ACTIVATE_READ_AND_NOP,", self.c_content)
        self.assertIn("ACTIVATE_RESET,", self.c_content)
        self.assertIn("ACTIVATE_READ_CHIP_ID,", self.c_content)
        self.assertIn("ACTIVATE_READ_OTP,", self.c_content)
        self.assertIn("ACTIVATE_CHECK_FW_VER,", self.c_content)
        self.assertIn("ACTIVATE_NUM_STATES,", self.c_content)

    def test_demosaicing_flags_and_dimensions(self):
        """Verify process_raw_frame generates scaled image with FPI_IMAGE_COLORS_INVERTED."""
        self.assertIn("img->flags = FPI_IMAGE_COLORS_INVERTED;", self.c_content)
        self.assertIn("img->ppmm = 500.0 / 25.4;", self.c_content)

    def test_production_driver_compactness(self):
        """Verify production driver size (~850 LOC) with clean base-class subclassing."""
        lines = [l for l in self.c_content.splitlines() if l.strip()]
        self.assertLess(len(lines), 950, f"Driver exceeds production compactness limit: {len(lines)} LOC")
        self.assertIn("FPI_TYPE_DEVICE_GOODIXTLS5XX", self.c_content)


    @unittest.skipUnless(BUILD_TREE.is_dir(), "deployed build tree /tmp/libfprint-goodix absent")
    def test_local_tree_synchronization(self):
        """Verify local driver tree in workspace matches active build tree exactly."""
        tree = BUILD_TREE / "libfprint" / "drivers" / "goodixtls"
        with open(tree / "goodix5e0a.c", "r") as f:
            tree_c = f.read()
        with open(tree / "goodix5e0a.h", "r") as f:
            tree_h = f.read()
        self.assertEqual(self.c_content, tree_c, "goodix5e0a.c out of sync between build and repo")
        self.assertEqual(self.h_content, tree_h, "goodix5e0a.h out of sync between build and repo")

if __name__ == "__main__":
    unittest.main()
