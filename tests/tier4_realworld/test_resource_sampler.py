"""Offline fixtures validate the sampler, not fprintd's live resource cost."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/sample_fprintd_resources.py"
spec = importlib.util.spec_from_file_location("resource_sampler", SCRIPT)
sampler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sampler)


def stat(pid=123, start=900, user=20, system=10, comm="fprintd ) worker", state="S"):
    fields = ["0"] * 50
    fields[0] = state
    fields[11], fields[12], fields[19] = map(str, (user, system, start))
    return f"{pid} ({comm}) " + " ".join(fields) + "\n"


class ResourceSamplerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        process = self.root / "123"
        process.mkdir()
        (process / "stat").write_text(stat())
        (process / "status").write_text("Name:\tfprintd\nVmRSS:\t4096 kB\n")
        (process / "smaps_rollup").write_text("001-002 ---p\nRss: 4096 kB\nPss: 2048 kB\n")
        (process / "cmdline").write_bytes(b"/usr/libexec/fprintd\0--no-timeout\0")

    def snapshot(self):
        return sampler.snapshot(lambda: 123, self.root)

    def pair(self):
        before = self.snapshot()
        after = copy.deepcopy(before)
        before["monotonic_seconds"] = 50
        after["monotonic_seconds"] = 70
        after["stat"]["user_ticks"] += 150
        after["stat"]["system_ticks"] += 50
        return before, after

    def test_stat_comm_with_spaces_and_parentheses(self):
        result = sampler.parse_stat(stat())
        self.assertEqual(result, dict(pid=123, comm="fprintd ) worker", state="S",
                                      user_ticks=20, system_ticks=10, starttime_ticks=900))

    def test_bad_stat(self):
        for text in ("", "123 (fprintd) S 0", stat(user=-1)):
            with self.subTest(text=text), self.assertRaises((ValueError, IndexError)):
                sampler.parse_stat(text)

    def test_memory_exact_key_and_units(self):
        self.assertEqual(sampler.parse_kib("Pss_Dirty: 12 kB\nPss: 45 kB", "Pss"), 45)
        for text in ("Pss_Dirty: 12 kB", "Pss: 45 MB", "Pss: -1 kB", "Pss: nope kB"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                sampler.parse_kib(text, "Pss")

    def test_snapshot_end_to_end_fixture(self):
        sample = self.snapshot()
        self.assertTrue(sample["identity_valid"])
        self.assertEqual(sample["errors"], [])
        self.assertEqual(sample["rss_kib"], 4096)
        self.assertEqual(sample["pss_kib"], 2048)
        self.assertTrue(sample["no_timeout_argument"])

    def test_cpu_deltas_actual_elapsed_and_idle_unproven(self):
        report = sampler.summarize(*self.pair(), 100)
        self.assertEqual(report["resource_sample"], "complete")
        self.assertEqual(report["cpu_user_seconds"], 1.5)
        self.assertEqual(report["cpu_system_seconds"], 0.5)
        self.assertEqual(report["cpu_total_seconds"], 2)
        self.assertEqual(report["cpu_percent_one_core"], 10)
        self.assertEqual(report["elapsed_seconds"], 20)
        self.assertEqual(report["identity"], "unchanged")
        self.assertEqual(report["idle_baseline"], "inconclusive-because-no-claims-not-established")
        self.assertIsNone(report["wakeups"]["value"])
        self.assertIsNone(report["power"]["value"])

    def test_pid_change_and_reuse_suppress_deltas(self):
        for field, value, expected in (("pid", 456, "pid-changed"),
                                       ("starttime_ticks", 901, "starttime-changed-pid-reused")):
            before, after = self.pair()
            (after if field == "pid" else after["stat"])[field] = value
            report = sampler.summarize(before, after, 100)
            self.assertEqual(report["identity"], expected)
            self.assertIsNone(report["cpu_total_seconds"])
            self.assertEqual(report["resource_sample"], "incomplete")

    def test_denied_metrics_explicit_cpu_still_available(self):
        original = Path.read_text

        def read(path, *args, **kwargs):
            if path.name in ("status", "smaps_rollup"):
                raise PermissionError("fixture denial")
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", read):
            sample = self.snapshot()
        self.assertTrue(sample["identity_valid"])
        self.assertIsNone(sample["rss_kib"])
        self.assertIsNone(sample["pss_kib"])
        self.assertEqual(sample["errors"], ["rss_kib: permission-denied", "pss_kib: permission-denied"])
        after = copy.deepcopy(sample)
        after["monotonic_seconds"] += 1
        report = sampler.summarize(sample, after, 100)
        self.assertEqual(report["cpu_total_seconds"], 0)
        self.assertEqual(report["resource_sample"], "incomplete")

    def test_denied_stat_cannot_establish_identity(self):
        with patch.object(Path, "read_text", side_effect=PermissionError()):
            sample = self.snapshot()
        self.assertFalse(sample["identity_valid"])
        self.assertIsNone(sample["stat"])
        self.assertEqual(sample["errors"], ["stat: permission-denied"])

    def test_malformed_pss_is_reported(self):
        (self.root / "123/smaps_rollup").write_text("Pss: nope kB\n")
        sample = self.snapshot()
        self.assertIsNone(sample["pss_kib"])
        self.assertIn("pss_kib: malformed-or-missing-counter", sample["errors"])

    def test_missing_pss_has_no_invented_fallback(self):
        (self.root / "123/smaps_rollup").unlink()
        sample = self.snapshot()
        self.assertIsNone(sample["pss_kib"])
        self.assertIn("pss_kib: missing-or-process-exited", sample["errors"])

    def test_process_exit_between_endpoints(self):
        before = self.snapshot()
        (self.root / "123/stat").unlink()
        after = self.snapshot()
        report = sampler.summarize(before, after, 100)
        self.assertEqual(report["identity"], "unavailable")
        self.assertIsNone(report["cpu_total_seconds"])
        self.assertIn("stat: missing-or-process-exited", after["errors"])

    def test_exit_or_reuse_during_snapshot(self):
        for second in (FileNotFoundError(), sampler.parse_stat(stat(start=901))):
            with patch.object(sampler, "parse_stat", side_effect=[sampler.parse_stat(stat()), second]):
                sample = self.snapshot()
            self.assertFalse(sample["identity_valid"])
            self.assertTrue(sample["errors"])

    def test_zombie_not_live_identity(self):
        (self.root / "123/stat").write_text(stat(state="Z"))
        self.assertFalse(self.snapshot()["identity_valid"])

    def test_pid_resolution_failure(self):
        def denied():
            raise PermissionError()
        sample = sampler.snapshot(denied, self.root)
        self.assertIsNone(sample["pid"])
        self.assertEqual(sample["errors"], ["pid: permission-denied"])

    def test_service_query_is_read_only_and_bounded(self):
        with patch.object(sampler.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "123\n")) as run:
            self.assertEqual(sampler.service_pid(), 123)
        self.assertEqual(run.call_args.args[0],
                         ["systemctl", "show", "fprintd.service", "--property=MainPID", "--value"])
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        for output in ("0\n", "not a pid"):
            with patch.object(sampler.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output)):
                with self.assertRaises((ProcessLookupError, ValueError)):
                    sampler.service_pid()

    def test_denied_cmdline_and_absent_flag(self):
        with patch.object(Path, "read_bytes", side_effect=PermissionError()):
            sample = self.snapshot()
        self.assertIsNone(sample["no_timeout_argument"])
        self.assertIn("cmdline: permission-denied", sample["errors"])
        (self.root / "123/cmdline").write_bytes(b"fprintd\0--no-timeout-other\0")
        self.assertFalse(self.snapshot()["no_timeout_argument"])
        before, after = self.pair()
        after["no_timeout_argument"] = False
        self.assertEqual(sampler.summarize(before, after, 100)["idle_baseline"],
                         "inconclusive-because-no-timeout-argument-not-established")

    def test_counter_regression_and_invalid_clock(self):
        for field in ("user_ticks", "system_ticks", "clock"):
            before, after = self.pair()
            if field == "clock":
                after["monotonic_seconds"] = before["monotonic_seconds"]
            else:
                after["stat"][field] = 0
            report = sampler.summarize(before, after, 100)
            self.assertIsNone(report["cpu_total_seconds"])
            self.assertIn("invalid-counter-delta-or-clock", report["errors"])

    def test_cli_json_and_configurable_interval_without_live_io(self):
        output = io.StringIO()
        with patch.object(sampler, "snapshot", side_effect=self.pair()), \
             patch.object(sampler.time, "sleep") as sleep, \
             patch.object(sampler.os, "sysconf", return_value=100), \
             contextlib.redirect_stdout(output):
            rc = sampler.main(["--interval", "0.25", "--pid", "123"])
        report = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(report["requested_interval_seconds"], 0.25)
        self.assertEqual(report["selection"], "fixed-pid")
        self.assertEqual(report["cpu_total_seconds"], 2)
        sleep.assert_called_once_with(0.25)

    def test_cli_interrupt_preserves_initial_sample(self):
        output = io.StringIO()
        with patch.object(sampler, "snapshot", return_value=self.snapshot()), \
             patch.object(sampler.time, "sleep", side_effect=KeyboardInterrupt), \
             contextlib.redirect_stdout(output):
            self.assertEqual(sampler.main(["--pid", "123"]), 130)
        report = json.loads(output.getvalue())
        self.assertIsNotNone(report["before"]["stat"])
        self.assertIsNone(report["after"])
        self.assertEqual(report["idle_baseline"], "inconclusive-because-interrupted")

    def test_cli_missing_process_does_not_wait(self):
        (self.root / "123/stat").unlink()
        with patch.object(sampler, "snapshot", return_value=self.snapshot()), \
             patch.object(sampler.time, "sleep") as sleep, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sampler.main(["--pid", "123"]), 1)
        sleep.assert_not_called()

    def test_cli_rejects_invalid_inputs_without_reading(self):
        for args in (["--interval", "nan"], ["--interval", "inf"], ["--interval", "0"],
                     ["--interval", "-1"], ["--pid", "0"], ["--pid", "-1"]):
            with self.subTest(args=args), patch.object(sampler, "snapshot") as read, \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                sampler.main(args)
            self.assertEqual(raised.exception.code, 2)
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
