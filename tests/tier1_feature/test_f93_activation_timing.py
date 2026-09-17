"""Ticket 93: offline journal timing, synthetic inputs only."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.analyze_activation_timing import analyze, summary


def line(ms, message, pid=12, day="Sep 17"):
    seconds, micros = divmod(round(ms * 1000), 1000000)
    return f"{day} 11:00:{seconds:02d}.{micros:06d} host fprintd[{pid}]: {message}\n"


def warm():
    return [
        line(0, "start verification device 0 finger test"),
        line(1, "5e0a parked TLS session candidate fresh, health-checking (gen=3)"),
        line(2, "Running command: 0xae"),
        line(3, "got ack"),
        line(3.1, "Completed command: 0x00"),
        line(4, "5e0a TLS session reused (parked 90.2s, gen=3)"),
        line(5, "Running command: 0x96"),
        line(18, "got ack"),
        line(18.1, "Completed command: 0x00"),
        line(19, "Running command: 0xae"),
        line(20, "Completed command: 0x00"),
        line(21, "Running command: 0xd6"),
        line(34, "got ack"),
        line(34.2, "Completed command: 0x00"),
        line(35, "Running command: 0x32"),
        line(40, "got ack"),
        line(50, "5e0a D32 touch confirmed: mask=0x3f"),
        line(51, "Running command: 0x32"),
    ]


class TestActivationTiming(unittest.TestCase):
    def test_warm_markers_and_first_send_only(self):
        rows = analyze(warm())
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["path"], "park-reused")
        self.assertEqual(row["to_finger_wait_sent_ms"], 35)
        self.assertEqual(row["candidate_to_reused_ms"], 3)
        self.assertEqual(row["reused_to_finger_wait_sent_ms"], 31)
        self.assertEqual(row["end_line"], 15)
        self.assertEqual([c["command"] for c in row["commands"]],
                         ["0xae", "0x96", "0xae", "0xd6"])
        self.assertEqual(row["commands"][1]["to_completion_ms"], 13.1)
        self.assertEqual(row["commands"][1]["completion_to_next_ms"], 0.9)

    def test_candidate_is_not_reuse(self):
        row = analyze(warm()[:5])[0]
        self.assertEqual(row["path"], "candidate-only")
        self.assertEqual(row["status"], "incomplete:end-of-file")
        self.assertIsNone(row["reused_to_finger_wait_sent_ms"])
        self.assertEqual(summary([row]), {})

    def test_failed_candidate_then_cold_fallback(self):
        row = analyze(warm()[:5] + [
            line(5, "5e0a warm expired: reason=transport-miss"),
            line(6, "Running command: 0x32"),
        ])[0]
        self.assertEqual(row["path"], "cold:transport-miss")
        self.assertIsNone(row["candidate_to_reused_ms"])

    def test_config_reuse_is_not_tls_reuse(self):
        row = analyze([warm()[0],
                       line(1, "5e0a warm activation: reusing MCU config (age=1s)"),
                       line(2, "Running command: 0x32")])[0]
        self.assertEqual(row["path"], "warm-reactivation")
        self.assertIsNone(row["reused_to_finger_wait_sent_ms"])

    def test_missing_completion_is_not_next_send(self):
        row = analyze([warm()[0], line(1, "Running command: 0x00"),
                       line(2, "Running command: 0x32")])[0]
        command = row["commands"][0]
        self.assertIsNone(command["to_ack_ms"])
        self.assertIsNone(command["to_completion_ms"])
        self.assertEqual(command["to_next_command_ms"], 1)

    def test_tls_read_completion_does_not_fill_missing_request_completion(self):
        row = analyze([warm()[0], line(1, "Running command: 0xd0"),
                       line(2, "goodix_read_tls()"),
                       line(3, "Completed command: 0x00"),
                       line(4, "Running command: 0xd4"),
                       line(5, "Running command: 0x32")])[0]
        self.assertIsNone(row["commands"][0]["to_completion_ms"])
        self.assertEqual(row["commands"][0]["to_next_command_ms"], 3)

    def test_pid_action_and_file_boundaries(self):
        rows = analyze(warm()[:5] + [line(4, "Completed command: 0x00", pid=99),
                                    line(5, "Running command: 0x32", pid=99),
                                    line(6, "start verification device 0 finger next"),
                                    line(7, "Device reported close completion"),
                                    line(8, "Running command: 0x32")])
        self.assertEqual([r["status"] for r in rows],
                         ["incomplete:new-action", "incomplete:action-ended"])
        self.assertEqual(analyze(warm()[1:]), [])
        self.assertEqual(analyze([]), [])

    def test_coarse_timestamps_rejected(self):
        with self.assertRaisesRegex(ValueError, "six decimals"):
            analyze(["Sep 17 11:00:00 host fprintd[12]: start verification device 0\n"])

    def test_backwards_clock_rejected(self):
        with self.assertRaisesRegex(ValueError, "backward timestamp"):
            analyze([line(2, "start verification device 0"), line(1, "Running command: 0x32")])

    def test_midnight_and_single_digit_day(self):
        rows = analyze([
            "Sep  9 23:59:59.999000 host fprintd[12]: start verification device 0\n",
            "Sep 10 00:00:00.001000 host fprintd[12]: Running command: 0x32\n",
        ])
        self.assertEqual(rows[0]["to_finger_wait_sent_ms"], 2)

    def test_cli_json_and_missing_file(self):
        script = Path(__file__).resolve().parents[2] / "scripts/analyze_activation_timing.py"
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "journal.txt"
            journal.write_text("".join(warm()), encoding="utf-8")
            result = subprocess.run([sys.executable, str(script), str(journal)],
                                    capture_output=True, text=True, check=True)
            output = json.loads(result.stdout)
            self.assertEqual(output["summary"]["park-reused"]["n"], 1)
            self.assertIn("not USB readiness", output["measurement"])
            result = subprocess.run([sys.executable, str(script), str(journal) + ".missing"],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
