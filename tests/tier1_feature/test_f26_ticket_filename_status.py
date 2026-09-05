"""
Tier 1 - Feature 26: Ticket filename carries the one-word status.
Requirements: .scratch/goodix-5e0a/issues/NN-<status>-slug.md must mirror
the **Status:** header's first word, so one ls separates permanent history
(closed/superseded) from the live workfront. AGENTS.md owns the rule.
"""

import os
import re
import unittest
from tests.repo_paths import repo

ISSUES_DIR = repo(".scratch", "goodix-5e0a", "issues")

ALLOWED = (
    "ready-for-agent",
    "ready-for-hardware-verify",
    "in-progress",
    "superseded",
    "closed",
    "verified",
)

_NAME_RE = re.compile(r"^(\d+)-(.+)-.+\.md$")
_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(\S+)")


def _tickets():
    return sorted(
        f for f in os.listdir(ISSUES_DIR)
        if re.match(r"^\d+-.+\.md$", f)
    )


def _status_of(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = _STATUS_RE.match(line)
            if m:
                return m.group(1).rstrip(",:;")
    return None


class TicketFilenameStatusTest(unittest.TestCase):
    def test_filenames_wellformed_with_allowed_status(self):
        files = _tickets()
        self.assertTrue(files, "no ticket files found")
        for name in files:
            m = _NAME_RE.match(name)
            self.assertIsNotNone(m, f"bad ticket filename: {name}")
            token = next(
                (s for s in ALLOWED if m.group(2).startswith(s)), None,
            )
            self.assertIsNotNone(
                token, f"unknown status token in filename: {name}")

    def test_filename_status_matches_header(self):
        for name in _tickets():
            token = next(
                s for s in ALLOWED
                if _NAME_RE.match(name).group(2).startswith(s))
            header = _status_of(os.path.join(ISSUES_DIR, name))
            self.assertIsNotNone(header, f"no Status header: {name}")
            self.assertEqual(
                header, token,
                f"{name}: filename says {token}, header says {header}")

    def test_live_workfront_visible_via_glob(self):
        import glob
        live = set(glob.glob(os.path.join(ISSUES_DIR, "*ready-for-agent*")))
        live |= set(glob.glob(
            os.path.join(ISSUES_DIR, "*ready-for-hardware-verify*")))
        live |= set(glob.glob(os.path.join(ISSUES_DIR, "*in-progress*")))
        self.assertTrue(live, "live workfront glob finds nothing")


if __name__ == "__main__":
    unittest.main()
