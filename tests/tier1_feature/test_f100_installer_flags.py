"""Installer CLI and SELinux policy checks; no installation or sensor claims."""

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "install.sh"
TE_FILE = ROOT / "packaging/selinux/goodix-engine.te"


class InstallerFlagsTest(unittest.TestCase):
    def run_script(self, *args, **env):
        return subprocess.run(["bash", str(SCRIPT), *args],
                              env={**os.environ, "GOODIX_ENGINE_DLL_PATH": "", **env},
                              capture_output=True, text=True, timeout=10)

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

    def test_check_ignores_engine_environment(self):
        result = self.run_script("--check", GOODIX_ENGINE_DLL_PATH="/missing/engine.dll")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("These checks do not establish a working driver", result.stdout)

    def test_standalone_modes_reject_build_options(self):
        for mode in ("--help", "--check", "--uninstall"):
            for options in (("--no-deps",), ("--dll", "engine.dll"),
                            ("--build-only", "stage")):
                for args in ((*options, mode), (mode, *options)):
                    with self.subTest(args=args):
                        result = self.run_script(*args)
                        self.assertEqual(result.returncode, 1)
                        self.assertIn("Usage", result.stderr)

    def test_build_only_requires_destination(self):
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
