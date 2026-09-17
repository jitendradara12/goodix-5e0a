"""Unprivileged transaction tests. Run: python3 -B tests/fixtures/install/test_install.py -v"""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[3] / "install.sh"


class InstallerTests(unittest.TestCase):
    def run_functions(self, body, *args):
        # Source the actual script, without invoking main or altering its source.
        # Only transaction/build functions receive temporary filesystem paths.
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; shift; systemctl() { :; }; ' + body,
             "bash", str(SCRIPT), *map(str, args)],
            capture_output=True, text=True,
        )
        return result

    def test_help_and_bad_flags(self):
        for args, expected in [(["--help"], 0), (["--dll"], 1),
                               (["--dll", "--help"], 1),
                               (["--unknown"], 1), (["--uninstall", "--dll", "x"], 1)]:
            with self.subTest(args=args):
                result = subprocess.run(["bash", str(SCRIPT), *args],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                if args == ["--dll", "--help"]:
                    self.assertIn("--dll requires a file", result.stderr)
                else:
                    self.assertIn("Usage:", result.stdout + result.stderr)

    def test_nixos_preflight(self):
        # Read the OS through Bash too, so quoted ID forms have the same meaning.
        os_id = subprocess.check_output(
            ["bash", "-c", '. /etc/os-release; printf "%s" "$ID"'], text=True)
        if os_id != "nixos":
            self.skipTest("NixOS-only preflight")
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["bash", str(SCRIPT), "--dll", "/nonexistent/engine.dll"],
                cwd=directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("NixOS detected", result.stderr)
        self.assertNotIn("not found", result.stderr)

    def test_install_and_uninstall_preserve_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / "stage"
            stage.mkdir()
            (stage / "GoodixEngineAdapter.dll").write_bytes(b"fixture")
            (root / "enrolled-print").write_text("keep")
            result = self.run_functions('install_files "$1" "$2" "$3"',
                                        stage, root / "prefix", root / "dropins")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "prefix/GoodixEngineAdapter.dll").read_bytes(), b"fixture")
            config = (root / "dropins/90-goodix.conf").read_text()
            self.assertIn(f"Environment=LD_LIBRARY_PATH={root}/prefix/lib", config)
            self.assertIn(f"Environment=GOODIX_ENGINE_DLL_PATH={root}/prefix/GoodixEngineAdapter.dll", config)
            self.assertNotIn("ExecStart", config)
            (root / "dropins/user.conf").write_text("keep")
            result = self.run_functions('uninstall_files "$1" "$2"',
                                        root / "prefix", root / "dropins")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / "prefix").exists())
            self.assertFalse((root / "dropins/90-goodix.conf").exists())
            self.assertEqual((root / "dropins/user.conf").read_text(), "keep")
            self.assertEqual((root / "enrolled-print").read_text(), "keep")

    def test_existing_destinations_and_symlinks_are_refused(self):
        for existing in ("prefix", "dropins", "symlink"):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "stage").mkdir()
                if existing == "symlink":
                    (root / "prefix").symlink_to(root / "absent")
                else:
                    (root / existing).mkdir()
                    (root / existing / "user-file").write_text("keep")
                result = self.run_functions('install_files "$1" "$2" "$3"',
                                            root / "stage", root / "prefix", root / "dropins")
                self.assertNotEqual(result.returncode, 0)
                if existing == "symlink":
                    self.assertTrue((root / "prefix").is_symlink())
                else:
                    self.assertEqual((root / existing / "user-file").read_text(), "keep")

    def test_failed_copy_or_reload_rolls_back_only_new_paths(self):
        for failure in ('cp() { touch "${@: -1}/partial-copy"; return 1; };',
                        'systemctl() { return 1; };'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "stage").mkdir()
                (root / "unrelated").write_text("keep")
                result = self.run_functions(failure + ' install_files "$1" "$2" "$3"',
                                            root / "stage", root / "prefix", root / "dropins")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "prefix").exists())
                self.assertFalse((root / "dropins").exists())
                self.assertEqual((root / "unrelated").read_text(), "keep")

    def test_uninstall_refuses_changed_ownership_records(self):
        for changed in ("prefix/.goodix-install", "dropins/90-goodix.conf"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "stage").mkdir()
                result = self.run_functions('install_files "$1" "$2" "$3"',
                                            root / "stage", root / "prefix", root / "dropins")
                self.assertEqual(result.returncode, 0, result.stderr)
                (root / changed).write_text("user change")
                result = self.run_functions('uninstall_files "$1" "$2"',
                                            root / "prefix", root / "dropins")
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue((root / "prefix").is_dir())
                self.assertTrue((root / "dropins/90-goodix.conf").is_file())

    def test_build_stages_without_privilege_and_fetch_falls_back(self):
        self.assertNotEqual(os.geteuid(), 0, "Run installer fixtures unprivileged")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.dll").write_bytes(b"fixture")
            # Stand-ins create only under $1, never under the requested prefix.
            result = self.run_functions(r'''
                git() {
                    if [[ $1 == -C && $3 == fetch ]]; then return 1; fi
                    if [[ $1 == apply ]]; then return 0; fi # core patch: guarded by tier5 content test
                    if [[ $1 == clone ]]; then
                        mkdir -p "$3/libfprint/drivers/goodixtls"
                        echo 1.94.5 > "$3/meson.build"
                        echo FP_DEVICE_RETRY_REMOVE_FINGER, > "$3/libfprint/fp-device.h"
                        touch "$3/fallback-used"
                    fi
                }
                meson() { printf '%s\n' "$@" > meson-args; }
                ninja() {
                    if [[ ${3:-} == install ]]; then
                        [[ -n ${DESTDIR:-} ]] || return 1
                        mkdir -p "$DESTDIR/opt/goodix-libfprint/lib"
                        echo fixture > "$DESTDIR/opt/goodix-libfprint/lib/libfprint-2.so.2"
                    fi
                }
                sudo() { echo 'Unexpected privilege escalation' >&2; return 1; }
                build_stage "$1" "$2" "$1/input.dll"
            ''', root, SCRIPT.parent)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "libfprint/fallback-used").exists())
            # build_stage owns the copy; the core patch's content is guarded
            # by the tier5 content test (mock git cannot represent it here).
            copied = root / "libfprint/libfprint/drivers/goodixtls/goodix5e0a.c"
            self.assertTrue(copied.exists(), "driver sources must be copied into the tree")
            self.assertEqual(copied.read_text(),
                             (SCRIPT.parent / "libfprint-driver/goodix5e0a.c").read_text())
            args = (root / "libfprint/meson-args").read_text()
            self.assertIn("--prefix=/opt/goodix-libfprint", args)
            self.assertIn("-Dudev_rules=disabled", args)
            self.assertEqual((root / "stage/opt/goodix-libfprint/GoodixEngineAdapter.dll").read_bytes(), b"fixture")


if __name__ == "__main__":
    unittest.main()
