"""Failure-injection tests for the disposable hardware session, without USB/root."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("hardware_session", ROOT / "tools/native_raster_session.py")
SESSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SESSION)


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
        for name, value in (("RUNTIME", self.runtime), ("DROPIN", self.dropin), ("REPORTS", self.reports)):
            patch = mock.patch.object(SESSION, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        for name, value in (("preflight", lambda: None), ("daemon_path", lambda: "/usr/libexec/fprintd"),
                            ("isolation_probe", lambda p: None), ("verify_runtime", lambda pid: None),
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
        spec = importlib.util.spec_from_file_location("journal_session", ROOT / "tools/native_raster_session.py")
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


if __name__ == "__main__":
    unittest.main()
