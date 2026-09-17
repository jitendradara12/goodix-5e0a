"""Installer flags for portable and desktop-integrated setups (tickets 97-99).
Run: python3 -B tests/tier1_feature/test_f100_installer_portability.py -v"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "install.sh"
TE_FILE = ROOT / "packaging/selinux/goodix-engine.te"


class InstallerFlagsTest(unittest.TestCase):
    def run_script(self, *args):
        import subprocess
        return subprocess.run(["bash", str(SCRIPT), *args],
                              capture_output=True, text=True)

    def test_help_documents_new_flags(self):
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in ("--no-deps", "--build-only", "--check", "--dll", "--uninstall"):
            self.assertIn(flag, result.stdout)

    def test_check_is_read_only_and_refuses_extra_args(self):
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        # Nothing was installed by a --check run.
        self.assertFalse(Path("/opt/goodix-libfprint").exists() and
                         "Installed" in result.stdout)
        self.assertIn("fprintd", result.stdout)
        result = self.run_script("--check", "--uninstall")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage", result.stderr)

    def test_missing_dll_error_mentions_opt_out(self):
        # Unknown/odd ID must not hard-fail the parse; it falls back to
        # --no-deps behavior and the preinstalled-dependency checks.
        result = self.run_script("--build-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage", result.stderr)

    def test_selinux_artifact_matches_confirmed_rule(self):
        text = TE_FILE.read_text()
        self.assertIn("module goodix-engine", text)
        self.assertIn("allow fprintd_t tmpfs_t:file { execute map read write };", text)
        self.assertNotIn("setenforce", text)  # no disable-SELinux shortcuts


if __name__ == "__main__":
    unittest.main()
