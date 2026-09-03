"""
Tier 1 - Feature 20: Meson / Ninja Build System Wiring
Requirements: Wire goodixtls5e0a into meson.build and libfprint/meson.build.
"""

import unittest
import os

class TestF20MesonWiring(unittest.TestCase):

    def setUp(self):
        self.root_meson = "/tmp/libfprint-goodix/meson.build"
        self.libfprint_meson = "/tmp/libfprint-goodix/libfprint/meson.build"
        self.driver_dir = "/tmp/libfprint-goodix/libfprint/drivers/goodixtls"

    def test_meson_build_includes_goodixtls5e0a(self):
        """Verify root meson.build contains goodixtls5e0a in driver list."""
        with open(self.root_meson, "r") as f:
            content = f.read()
        self.assertIn("goodixtls5e0a", content)

    def test_libfprint_meson_build_sources(self):
        """Verify libfprint/meson.build includes goodix5e0a.c and related source files."""
        with open(self.libfprint_meson, "r") as f:
            content = f.read()
        self.assertIn("goodix5e0a.c", content)

    def test_driver_source_files_exist(self):
        """Verify goodix5e0a.c and goodix5e0a.h exist in the driver directory."""
        self.assertTrue(os.path.isfile(os.path.join(self.driver_dir, "goodix5e0a.c")))
        self.assertTrue(os.path.isfile(os.path.join(self.driver_dir, "goodix5e0a.h")))

    def test_libfprint_build_ninja_exists(self):
        """Verify Ninja build manifest was generated."""
        self.assertTrue(os.path.isfile("/tmp/libfprint-goodix/build/build.ninja"))

    def test_meson_options_validity(self):
        """Verify meson_options.txt contains driver definitions."""
        with open("/tmp/libfprint-goodix/meson_options.txt", "r") as f:
            content = f.read()
        self.assertIn("drivers", content)

if __name__ == "__main__":
    unittest.main()
