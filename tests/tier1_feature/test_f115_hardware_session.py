"""Failure-injection tests for the disposable hardware session, without USB/root."""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("hardware_session", ROOT / "tools/hardware_session.py")
SESSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SESSION)
EXECUTABLE_MAPPING_PROBE = SESSION.executable_mapping_probe


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.runtime = self.base / "runtime"
        self.dropin = self.base / "units/test.conf"
        self.reports = self.base / "reports"
        self.old_prints = self.base / "real-prints"
        self.old_prints.mkdir()
        (self.old_prints / "existing-template").write_bytes(b"existing template unchanged")
        self.stage = self.base / "stage"
        (self.stage / "lib").mkdir(parents=True)
        (self.stage / "lib/libfprint-2.so.2").write_bytes(b"fixture library")
        (self.stage / "GoodixEngineAdapter.dll").write_bytes(b"fixture engine")
        self.active = "active"
        self.calls = []
        self.failure = None
        self.stack = []
        for name, value in (("RUNTIME", self.runtime), ("DROPIN", self.dropin), ("REPORTS", self.reports),
                            ("DRIVER_BASE", self.base)):
            patch = mock.patch.object(SESSION, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        for name, value in (("preflight", lambda: None), ("daemon_path", lambda: "/usr/libexec/fprintd"),
                            ("isolation_probe", lambda p: None), ("verify_runtime", lambda pid, driver: None),
                            ("executable_mapping_probe", lambda p: None),
                            ("property_value", self.property), ("command", self.command),
                            ("filtered_journal", lambda start: "5e0a Milan verify: match=1 pts=40\n")):
            patch = mock.patch.object(SESSION, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        for name in ("signal",):
            patch = mock.patch.object(SESSION.signal, name)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(SESSION.subprocess, "run", return_value=subprocess.CompletedProcess([], 0))
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(SESSION.os, "fchown")
        patch.start()
        self.addCleanup(patch.stop)

    def property(self, name):
        return {"ActiveState": self.active, "MainPID": "123"}[name]

    def command(self, args, **kwargs):
        args = list(map(str, args))
        self.calls.append(args)
        if self.failure and self.failure(args):
            raise subprocess.CalledProcessError(1, args)
        if args[:2] == ["systemctl", "stop"]:
            self.active = "inactive"
        if args[:2] in (["systemctl", "start"], ["systemctl", "restart"]):
            self.active = "active"
        return subprocess.CompletedProcess(args, 0)

    def run_session(self, test):
        with mock.patch.object(SESSION, "guided_test", test):
            code = SESSION.root_session(self.stage, {"revision": "fixture"})
        path = next(self.reports.glob("*.zip"))
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(set(archive.namelist()), set(SESSION.REPORT_FILES))
            contents = {name: archive.read(name) for name in archive.namelist()}
        self.assertNotIn(b"existing template unchanged", b"".join(contents.values()))
        self.assertNotIn(b"private secret test template", b"".join(contents.values()))
        self.assertEqual((self.old_prints / "existing-template").read_bytes(), b"existing template unchanged")
        if json.loads(contents["session.json"])["restored"]:
            self.assertEqual(list(self.base.glob("goodix-5e0a-experiment-*")), [])
        return code, json.loads(contents["session.json"])

    def exercise(self, event, clients):
        (self.runtime / "prints/root").mkdir()
        (self.runtime / "prints/root/test-template").write_bytes(b"private secret test template")
        event("holding", duration_seconds=20)
        return {"verdict": "confirmed"}

    def test_success_restores_running_service_and_excludes_templates(self):
        code, result = self.run_session(self.exercise)
        self.assertEqual(code, 0)
        self.assertTrue(result["restored"])
        self.assertEqual(self.active, "active")
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.dropin.exists())
        self.assertIn(["systemctl", "stop", "fprintd.service"], self.calls)
        self.assertIn(["systemctl", "start", "fprintd.service"], self.calls)
        self.assertEqual(list(self.base.glob("goodix-5e0a-experiment-*")), [])

    def test_driver_is_staged_outside_run_and_removed_on_restore(self):
        def inspect_driver(event, clients):
            manifest = json.loads((self.runtime / "manifest.json").read_text())
            driver = Path(manifest["driver_directory"])
            self.assertNotIn(self.runtime, driver.parents)
            self.assertEqual((driver / "lib/libfprint-2.so.2").read_bytes(), b"fixture library")
            self.assertIn(f"Environment=LD_LIBRARY_PATH={driver}/lib", self.dropin.read_text())
            return self.exercise(event, clients)
        code, result = self.run_session(inspect_driver)
        self.assertEqual(code, 0)
        self.assertTrue(result["restored"])
        self.assertEqual(list(self.base.glob("goodix-5e0a-experiment-*")), [])

    def test_noexec_staging_aborts_before_service_change_and_cleans_up(self):
        with mock.patch.object(SESSION, "executable_mapping_probe", side_effect=RuntimeError("noexec")):
            code, result = self.run_session(self.exercise)
        self.assertEqual(code, 1)
        self.assertFalse(result["hardware_run"])
        self.assertTrue(result["restored"])
        self.assertFalse(any(c[:2] in (["systemctl", "start"], ["systemctl", "stop"], ["systemctl", "restart"])
                             for c in self.calls))
        self.assertEqual(list(self.base.glob("goodix-5e0a-experiment-*")), [])

    def test_executable_mapping_probe_rejects_noexec(self):
        with mock.patch.object(SESSION.mmap, "mmap", side_effect=PermissionError("noexec")):
            with self.assertRaisesRegex(RuntimeError, "cannot be mapped executable"):
                EXECUTABLE_MAPPING_PROBE(self.stage / "lib/libfprint-2.so.2")

    def test_inactive_service_is_left_inactive(self):
        self.active = "inactive"
        code, result = self.run_session(self.exercise)
        self.assertEqual(code, 0)
        self.assertEqual(self.active, "inactive")
        self.assertNotIn(["systemctl", "start", "fprintd.service"], self.calls)

    def test_interrupt_after_enrollment_restores_service(self):
        def interrupted(event, clients):
            self.exercise(event, clients)
            raise KeyboardInterrupt()
        code, result = self.run_session(interrupted)
        self.assertEqual(code, 1)
        self.assertTrue(result["restored"])
        self.assertEqual(self.active, "active")
        self.assertFalse(self.runtime.exists())

    def test_restart_failure_removes_override_and_restores(self):
        self.failure = lambda args: args[:2] == ["systemctl", "restart"]
        code, result = self.run_session(self.exercise)
        self.assertEqual(code, 1)
        self.assertTrue(result["restored"])
        self.assertFalse(self.dropin.exists())
        self.assertEqual(self.active, "active")

    def test_isolation_failure_does_not_start_or_stop_fprintd(self):
        with mock.patch.object(SESSION, "isolation_probe", side_effect=RuntimeError("no namespace")):
            code, result = self.run_session(self.exercise)
        self.assertEqual(code, 1)
        self.assertFalse(result["hardware_run"])
        self.assertFalse(any(c[:2] in (["systemctl", "start"], ["systemctl", "stop"], ["systemctl", "restart"])
                             for c in self.calls))

    def test_bad_live_storage_aborts_before_enrollment(self):
        with mock.patch.object(SESSION, "verify_runtime", side_effect=RuntimeError("wrong storage")):
            with mock.patch.object(SESSION, "guided_test") as guided:
                code, result = self.run_session(guided)
                guided.assert_not_called()
        self.assertEqual(code, 1)
        self.assertTrue(result["restored"])

    def test_recovery_refuses_changed_override(self):
        self.runtime.mkdir()
        self.dropin.parent.mkdir()
        self.dropin.write_text("foreign override")
        SESSION.write_json(self.runtime / "manifest.json", {"dropin": "our override", "service_changed": True})
        with self.assertRaisesRegex(RuntimeError, "changed"):
            SESSION.restore()
        self.assertEqual(self.dropin.read_text(), "foreign override")
        self.assertEqual(self.calls, [])

    def test_recovery_is_idempotent_and_handles_initial_write_interruption(self):
        self.runtime.mkdir()
        (self.runtime / "manifest.json.tmp").write_text("partial")
        SESSION.restore()
        SESSION.restore()
        self.assertFalse(self.runtime.exists())

    def test_client_cleanup_error_does_not_skip_restore(self):
        def cleanup_error(event, clients):
            client = mock.Mock()
            client.stop.side_effect = RuntimeError("client already gone")
            clients.append(client)
            return self.exercise(event, clients)
        code, result = self.run_session(cleanup_error)
        self.assertTrue(result["restored"])
        self.assertIn("client_cleanup_error", result)

    def test_journal_projection_excludes_payloads_and_unknown_suffixes(self):
        # Use the real filter, not the root-session fixture's stub.
        spec = importlib.util.spec_from_file_location("journal_session", ROOT / "tools/hardware_session.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text = ("2026-10-19T00:00:00Z host fprintd: 5e0a Milan verify: match=1 pts=40 template=SECRET\n"
                "5e0a raw first 16 bytes: SECRET\n"
                "PSK=SECRET\n"
                "5e0a frame 1/4: declen=10564 active=5120 range=2000 quality=12 overlap=98 score-proxy=3170\n")
        with mock.patch.object(module, "output", return_value=text):
            report = module.filtered_journal(0)
        self.assertNotIn("SECRET", report)
        self.assertNotIn("host", report)
        self.assertIn("match=1 pts=40", report)
        self.assertIn("quality=12 overlap=98", report)


class CaptureCandidateTests(unittest.TestCase):
    def test_wire_patch_preserves_default_sources_and_only_changes_capture_data(self):
        names = ("libfprint-driver/goodix.c", "libfprint-driver/goodix5e0a.h")
        originals = {name: (ROOT / name).read_text() for name in names}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            for name in names:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(originals[name])
            patch = ROOT / "experiments/jet-soup-capture.patch"
            subprocess.run(["git", "apply", "--no-index", "--check", str(patch)], cwd=source,
                           check=True, capture_output=True)
            subprocess.run(["git", "apply", "--no-index", str(patch)], cwd=source,
                           check=True, capture_output=True)
            before = originals[names[1]]
            after = (source / names[1]).read_text()

            def config(text):
                body = re.search(r"goodix_5e0a_config\[256\] = \{(.*?)\};", text, re.S)[1]
                return bytes(int(value, 16) for value in re.findall(r"0x([0-9a-f]{2})", body))

            changes = {index: (old, new) for index, (old, new) in enumerate(zip(config(before), config(after)))
                       if old != new}
            self.assertEqual(changes, {200: (0x15, 0x1f), 235: (0, 0xf0), 236: (1, 0),
                                       254: (0x53, 0x4a), 255: (0x0e, 0x1e)})
            payload = "0x01, 0x00, 0xad, 0x00, 0xae, 0x00, 0xac, 0x00, 0xad, 0x00"
            self.assertIn(payload, after)
            self.assertIn(payload, (source / names[0]).read_text())
            self.assertIn('#define GOODIX_5E0A_BANDPASS_TARGET_RMS (80.0f)', after)
            for name in names:
                self.assertEqual((ROOT / name).read_text(), originals[name])

    def test_runtime_uses_shared_current_pipeline_without_legacy_experiment_flag(self):
        text = SESSION.dropin_text("/usr/libexec/fprintd", "0123456789abcdef")
        self.assertNotIn("Environment=GOODIX_5E0A_NATIVE_RASTER=1", text)
        self.assertIn("UnsetEnvironment=GOODIX_5E0A_NATIVE_RASTER", text)


if __name__ == "__main__":
    unittest.main()
