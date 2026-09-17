"""
Tier 1 - Feature 22: Hermetic nix-build & Flake Evaluation
Requirements: Verify clean compilation of libfprint-goodix and fprintd override under Nix.
"""

import unittest
import shutil
import subprocess
import os
from tests.repo_paths import repo, REPO_ROOT

class TestF22NixDerivation(unittest.TestCase):

    def setUp(self):
        self.derivation_file = repo("libfprint-goodix.nix")

    @unittest.skipUnless(shutil.which("nix-instantiate"), "nix-instantiate not installed")
    def test_nix_derivation_evaluates_cleanly(self):
        """Verify nix-instantiate --eval successfully evaluates libfprint-goodix derivation."""
        cmd = [
            "nix-instantiate", "--eval",
            "-E", "let pkgs = import <nixpkgs> {}; in pkgs.callPackage ./libfprint-goodix.nix {}"
        ]
        result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Nix evaluation failed: {result.stderr}")
        self.assertIn("libfprint-goodix", result.stdout)

    def test_nix_derivation_meson_flags(self):
        """Verify mesonFlags contains -Ddrivers=goodixtls5e0a and udev options."""
        with open(self.derivation_file, "r") as f:
            content = f.read()
        self.assertIn("-Ddrivers=goodixtls5e0a", content)
        self.assertIn("-Dudev_rules=enabled", content)

    def test_nix_derivation_build_inputs(self):
        """Verify required C libraries (glib, libusb1, gusb, pixman, openssl) in buildInputs."""
        with open(self.derivation_file, "r") as f:
            content = f.read()
        for dep in ["glib", "libusb1", "gusb", "pixman", "openssl", "nss", "nspr"]:
            self.assertIn(dep, content)

    def test_nix_derivation_patch_included(self):
        """Verify the integration patch is listed and driver sources are copied in."""
        with open(self.derivation_file, "r") as f:
            content = f.read()
        self.assertIn("./goodix-5e0a-integration.patch", content)
        self.assertIn("cp ${./libfprint-driver}", content)

    def test_fprintd_override_in_nixos_module(self):
        """Verify default.nix overrides fprintd with libfprint-goodix package."""
        with open(repo("nixos-module.nix"), "r") as f:
            content = f.read()
        self.assertIn("services.fprintd", content)

    def test_nixos_module_udev_rules_present(self):
        """Verify the module ships a restrictive USB rule for 27c6:5e0a.

        Ticket 96 review: MODE=0666 made the sensor world-writable; fprintd
        runs as root, so 0660 + uaccess is sufficient. The package's own
        rules file is empty for 5e0a (hwdb generation disabled), so the
        module must carry the rule itself.
        """
        with open(repo("nixos-module.nix"), "r") as f:
            content = f.read()
        self.assertIn('ATTRS{idVendor}=="27c6"', content)
        self.assertIn('ATTRS{idProduct}=="5e0a"', content)
        self.assertIn('MODE="0660"', content)
        self.assertIn('TAG+="uaccess"', content)
        self.assertNotIn('MODE="0666"', content)

    def test_single_base_fetch_parity(self):
        """Verify both derivations fetch the same base (one patch, one base).

        Regression guard for the 2026-09-09 nixos-rebuild breakage: the
        module pointed at a fork that already carried goodix5e0a.c while
        the unified patch creates it as a new file. Skipped when the
        external flake tree is absent.
        """
        from tests.repo_paths import NIXOS_MODULE_DIR
        module_nix = NIXOS_MODULE_DIR / "libfprint-goodix.nix"
        if not module_nix.is_file():
            self.skipTest("external NixOS flake tree absent")
        with open(repo("libfprint-goodix.nix"), "r") as f:
            repo_nix = f.read()
        with open(str(module_nix), "r") as f:
            module_content = f.read()
        for field in ('owner = "goodix-fp-linux-dev";',
                      'repo = "libfprint";',
                      'rev = "c343b6934e40dcd40a5f9e3095810d98f1175a4d";',
                      'hash = "sha256-6llzCeVOtv0HRaNdB8mMzZCA8RBZtGkSCErsXwKE/vk=";'):
            self.assertIn(field, repo_nix)
            self.assertIn(field, module_content)
        self.assertNotIn("libfprintSrc", module_content)

if __name__ == "__main__":
    unittest.main()
