"""
Tier 1 - Feature 21: NixOS Flake & Derivation Patch Integrity
Requirements: Create clean unified patch and integrate into /home/sastauser/NixOS-Hyprland/modules/goodix/.
"""

import unittest
import os
import subprocess
from tests.repo_paths import repo, NIXOS_MODULE_DIR

NIXOS_TREE_MISSING = "external NixOS flake tree absent"

class TestF21NixOSPatch(unittest.TestCase):

    def setUp(self):
        self.patch_path = repo("0001-Add-driver-support-for-Goodix-27c6-5e0a.patch")
        self.nix_module_dir = str(NIXOS_MODULE_DIR)

    def test_patch_file_exists(self):
        """Verify unified patch file exists and is non-empty."""
        self.assertTrue(os.path.isfile(self.patch_path))
        self.assertGreater(os.path.getsize(self.patch_path), 10000)

    def test_patch_contains_all_driver_files(self):
        """Verify patch modifies goodix.c, goodix5xx.c, goodixtls.c and creates goodix5e0a.c/h."""
        with open(self.patch_path, "r") as f:
            content = f.read()
        self.assertIn("libfprint/drivers/goodixtls/goodix5e0a.c", content)
        self.assertIn("libfprint/drivers/goodixtls/goodix5e0a.h", content)
        self.assertIn("libfprint/drivers/goodixtls/goodix.c", content)
        self.assertIn("libfprint/drivers/goodixtls/goodix5xx.c", content)
        self.assertIn("libfprint/drivers/goodixtls/goodixtls.c", content)

    @unittest.skipUnless(NIXOS_MODULE_DIR.is_dir(), NIXOS_TREE_MISSING)
    def test_nixos_module_files_present(self):
        """Verify NixOS module tree in /home/sastauser/NixOS-Hyprland/modules/goodix."""
        self.assertTrue(os.path.isfile(os.path.join(self.nix_module_dir, "default.nix")))
        self.assertTrue(os.path.isfile(os.path.join(self.nix_module_dir, "libfprint-goodix.nix")))
        self.assertTrue(os.path.isfile(os.path.join(self.nix_module_dir, "0001-Add-driver-support-for-Goodix-27c6-5e0a.patch")))

    @unittest.skipUnless(NIXOS_MODULE_DIR.is_dir(), NIXOS_TREE_MISSING)
    def test_udev_rules_in_nixos_module(self):
        """Verify udev rules grant MODE=0666 and TAG+=uaccess for 27c6:5e0a."""
        with open(os.path.join(self.nix_module_dir, "default.nix"), "r") as f:
            content = f.read()
        self.assertIn('ATTRS{idVendor}=="27c6"', content)
        self.assertIn('ATTRS{idProduct}=="5e0a"', content)
        self.assertIn('MODE="0666"', content)
        self.assertIn('TAG+="uaccess"', content)

    @unittest.skipUnless(NIXOS_MODULE_DIR.is_dir(), NIXOS_TREE_MISSING)
    def test_pam_services_enabled(self):
        """Verify PAM services (sudo, login, hyprlock, swaylock, sddm) have fprintAuth enabled."""
        with open(os.path.join(self.nix_module_dir, "default.nix"), "r") as f:
            content = f.read()
        for svc in ["sudo", "login", "hyprlock", "swaylock", "sddm"]:
            self.assertIn(f"{svc}.fprintAuth", content)

if __name__ == "__main__":
    unittest.main()
