"""
Tier 1 - Feature 96: Public installation portability.
Requirements: no personal driver paths, parseable installers, synchronized DLL paths.
"""

import os
from pathlib import Path
import shutil
import subprocess
import unittest

from tests.repo_paths import repo


class TestF96PublicPortability(unittest.TestCase):

    def test_no_personal_paths_in_driver(self):
        files = [p for p in Path(repo("libfprint-driver")).rglob("*")
                 if p.suffix in (".c", ".h")]
        files += list(Path(repo()).glob("0001-*.patch"))
        files += [Path(repo("install.sh")), Path(repo("flake.nix"))]
        for path in files:
            with self.subTest(path=path.name):
                content = path.read_text()
                self.assertNotIn("/home/sastauser", content)
                self.assertNotIn("sastauser", content)

    def test_install_sh_parses(self):
        result = subprocess.run(["bash", "-n", repo("install.sh")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.access(repo("install.sh"), os.X_OK))

    def test_flake_exists_and_parses(self):
        self.assertTrue(Path(repo("flake.nix")).is_file())
        if shutil.which("nix") is None:
            self.skipTest("nix is not installed")
        # path:. includes new files in an uncommitted checkout; do not create a lock.
        result = subprocess.run(
            ["nix", "flake", "show", "--allow-dirty", "--no-write-lock-file", "path:."],
            cwd=repo(), capture_output=True, text=True, timeout=180)
        unsupported = ("experimental Nix feature 'flakes' is disabled",
                       "experimental Nix feature 'nix-command' is disabled",
                       "unrecognised command 'flake'", "unrecognized command 'flake'")
        if result.returncode and any(message in result.stderr for message in unsupported):
            self.skipTest("nix flakes are unsupported or disabled")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_patch_and_driver_agree_on_dll_search_paths(self):
        files = [Path(repo("libfprint-driver", "goodix_milan.c"))]
        files += list(Path(repo()).glob("0001-*.patch"))
        for path in files:
            with self.subTest(path=path.name):
                content = path.read_text()
                self.assertIn("/var/lib/fprint/GoodixEngineAdapter.dll", content)
                self.assertNotIn("goodix-27c6-5e0a-re", content)


if __name__ == "__main__":
    unittest.main()
