"""Offline fixtures for the ticket-89 report; no hardware or raw biometrics."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[2] / "scripts" / "matching_reliability.py"
SPEC = importlib.util.spec_from_file_location("matching_reliability", TOOL)
reliability = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reliability)

MATCH = """Sep 17 10:00:00 host fprintd[123]: 5e0a Milan verify: match=1 pts=75 (threshold=50)
Sep 17 10:00:00 host fprintd[123]: report_verify_status: result verify-match
Sep 17 10:00:00 host fprintd[123]: report_verify_status: result verify-match
"""
NO_MATCH = MATCH.replace("match=1", "match=0").replace("verify-match", "verify-no-match")
RETRY = "report_verify_status: result verify-retry-scan\n"


def sample(identifier="a", label="genuine", text=MATCH, results=None, **changes):
    journal, milan = reliability.parse_evidence(text)
    return reliability.validate({
        "id": identifier, "label": label, "finger": "finger-a", "contact": "steady",
        "cancelled": False, "results": results or [], "journal": journal, "milan": milan,
        **changes,
    })


class ReliabilityTests(unittest.TestCase):
    def test_labeled_results_and_duplicate_statuses(self):
        rows = [sample("a", results=["match", "match"]),
                sample("b", text=NO_MATCH), sample("c", "wrong", NO_MATCH),
                sample("d", "wrong"), sample("e", "unknown", NO_MATCH),
                sample("f", cancelled=True)]
        report = reliability.report(rows)
        summary = report["summary"]
        self.assertEqual(summary["attempts"], 6)
        self.assertEqual(summary["genuine_first_touch_success"],
                         {"numerator": 1, "denominator": 2, "rate": .5})
        self.assertEqual(summary["genuine_first_decision_miss"]["numerator"], 1)
        self.assertEqual(summary["wrong_finger_first_decision_rejection"]["rate"], .5)
        self.assertEqual(summary["excluded"], {"cancelled": 1, "unknown-label": 1})
        self.assertEqual(summary["outcomes"]["unknown-no-match"], 1)
        self.assertEqual(report["samples"][0]["evidence"], "journal-and-milan-consistent")

    def test_retry_then_match_is_not_first_touch_or_false_reject(self):
        row = sample(text=RETRY + RETRY + MATCH,
                     results=["retry", "match"])
        report = reliability.report([row])
        summary = report["summary"]
        self.assertEqual(report["samples"][0]["outcome"], "retry-first")
        self.assertEqual(report["samples"][0]["final"], "match")
        self.assertEqual(summary["genuine_first_touch_success"]["rate"], 0)
        self.assertIsNone(summary["genuine_first_decision_miss"]["rate"])
        self.assertEqual(summary["attempts"], 1)

    def test_mixed_terminal_claims_are_excluded(self):
        for text in (NO_MATCH + MATCH, MATCH + NO_MATCH,
                     MATCH + RETRY, MATCH + RETRY + MATCH,
                     "Verify result: verify-match (done)\n"
                     "Verify result: verify-no-match (done)\n"):
            with self.subTest(text=text):
                row = sample(text=text)
                self.assertEqual(reliability.assess(row)["excluded"], "mixed-claims")
                summary = reliability.report([row])["summary"]
                self.assertEqual(summary["attempts"], 1)
                self.assertEqual(summary["genuine_first_touch_success"]["denominator"], 0)

    def test_client_terminal_requires_done(self):
        for decision in ("match", "no-match"):
            for suffix in ("", " (not done)", " (done", " (retry)"):
                with self.subTest(decision=decision, suffix=suffix):
                    statuses, _ = reliability.parse_evidence(
                        f"Verify result: verify-{decision}{suffix}\n")
                    self.assertEqual(statuses, ["incomplete"])
                    for journal in ("", MATCH):
                        row = sample(text=journal, results=statuses)
                        self.assertEqual(reliability.assess(row)["excluded"], "incomplete")
                        self.assertIsNone(reliability.report([row])["summary"]
                                          ["genuine_first_touch_success"]["rate"])

    def test_identical_terminal_duplicates_remain_one_attempt(self):
        row = sample(results=["match"])
        # Public report/assess also tolerate uncollapsed duplicate statuses.
        row["results"] = ["match", "match"]
        row["journal"] = ["match", "match"]
        self.assertIsNone(reliability.assess(row)["excluded"])
        summary = reliability.report([row])["summary"]
        self.assertEqual(summary["attempts"], 1)
        self.assertEqual(summary["genuine_first_touch_success"]["rate"], 1)

    def test_missing_retry_only_and_errors_are_inconclusive(self):
        for text, reason in [ ("", "incomplete"), (RETRY, "incomplete"),
                             ("5e0a Milan verify: match=0 pts=0", "missing-status"),
                             ("Verify result: verify-unknown-error (done)", "error"),
                             ("Verify result: verify-new-status (done)", "error"),
                             ("Verify result: verify-cancelled (done)", "cancelled")]:
            with self.subTest(text=text):
                row = sample(text=text)
                self.assertEqual(reliability.assess(row)["excluded"], reason)
                self.assertIsNone(reliability.summarize([row])["genuine_first_touch_success"]["rate"])

    def test_unknown_finger_or_contact_never_implies_genuine_miss(self):
        for changes in ({"finger": "unknown"}, {"contact": "unknown"}, {"label": "unknown"}):
            with self.subTest(changes=changes):
                row = sample(text=NO_MATCH, **changes)
                self.assertEqual(reliability.assess(row)["outcome"], "unknown-no-match")
                self.assertEqual(reliability.summarize([row])["genuine_first_decision_miss"]["denominator"], 0)

    def test_conflicting_sources_excluded(self):
        for row, reason in [
            (sample(results=["no-match"]), "conflicting-statuses"),
            (sample(text=MATCH.replace("match=1", "match=0")), "conflicting-milan"),
            (sample(text=RETRY + MATCH, results=["match"]), "conflicting-statuses"),
        ]:
            with self.subTest(reason=reason):
                self.assertEqual(reliability.assess(row)["excluded"], reason)

    def test_client_only_and_quality_gate_journal_without_milan(self):
        for text in ("Verify result: verify-no-match (done)",
                     "5e0a no usable frame, reporting no-match\n"
                     "report_verify_status: result verify-no-match"):
            row = sample(text=text)
            self.assertEqual(reliability.assess(row)["outcome"], "genuine-miss")
            self.assertNotEqual(reliability.assess(row)["evidence"], "journal-and-milan-consistent")

    def test_group_counts(self):
        report = reliability.report([sample(), sample("b", contact="light"),
                                     sample("c", finger="finger-b")])
        self.assertEqual(len(report["groups"]), 3)
        self.assertTrue(all(g["attempts"] == 1 for g in report["groups"]))

    def test_empty_report_does_not_claim_accuracy(self):
        summary = reliability.report([])["summary"]
        self.assertEqual(summary["attempts"], 0)
        self.assertIsNone(summary["genuine_first_touch_success"]["rate"])

    def test_schema_rejects_extra_data_and_bad_labels(self):
        for changes in ({"image": "not-allowed"}, {"label": "probably-genuine"},
                        {"id": ""}, {"finger": "\nraw log"}, {"cancelled": 1},
                        {"results": ["unexpected"]}, {"milan": ["retry"]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                sample(**changes)

    def test_duplicate_ids_and_malformed_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "samples.jsonl"
            data = json.dumps(sample())
            path.write_text(data + "\n" + data + "\n")
            samples, duplicates = reliability.load_samples(path)
            self.assertEqual(duplicates, 1)
            self.assertEqual(reliability.report(samples)["summary"]["attempts"], 1)
            path.write_text(data + "\n" + json.dumps(sample(text=NO_MATCH)) + "\n")
            with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
                reliability.load_samples(path)
            for data in ("{", "[]", "null"):
                path.write_text(data)
                with self.assertRaisesRegex(ValueError, "sample line 1"):
                    reliability.load_samples(path)

    def test_cli_collect_report_and_no_raw_log_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            journal = directory / "journal.txt"
            journal.write_text(MATCH + "SECRET-UNRELATED-LOG\n")
            client = directory / "client.txt"
            client.write_text("Verify result: verify-match (done)\n")
            path = directory / "samples.jsonl"
            command = [sys.executable, str(TOOL), "collect", "--samples", str(path),
                       "--id", "trial-01", "--label", "genuine", "--finger", "finger-a",
                       "--contact", "steady", "--results", str(client), "--journal", str(journal)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["outcome"], "genuine-match")
            retained = path.read_text()
            for forbidden in ("SECRET", "pts", "threshold", "fprintd", "Sep 17"):
                self.assertNotIn(forbidden, retained)
            duplicate = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertEqual(path.read_text(), retained)
            result = subprocess.run([sys.executable, str(TOOL), "report", str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["summary"]["genuine_first_touch_success"]["rate"], 1)
            self.assertIn("SECRET", journal.read_text())
            # Hand-authored JSONL need not have a trailing newline.
            path.write_text(retained.rstrip("\n"))
            result = subprocess.run(
                [sys.executable, str(TOOL), "collect", "--samples", str(path),
                 "--id", "trial-02", "--cancelled"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["outcome"], "cancelled")
            rows, _ = reliability.load_samples(path)
            self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
