"""
Tier 1 - Feature 25: Unified Patch / Driver Source Synchronization
Requirements: the committed 0001-*.patch must embed the exact current
libfprint-driver/ sources, so a driver edit without patch regeneration
fails loudly instead of shipping stale code to NixOS.
"""

import os
import re
import unittest
from tests.repo_paths import repo

PATCH_PATH = repo("0001-Add-driver-support-for-Goodix-27c6-5e0a.patch")

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _split_sections(patch_lines):
    sections, cur = [], []
    for line in patch_lines:
        if line.startswith("diff --git"):
            if cur:
                sections.append(cur)
            cur = [line]
        else:
            cur.append(line)
    if cur:
        sections.append(cur)
    return sections


def _local_counterpart(patch_path):
    base = os.path.basename(patch_path)
    local = repo("libfprint-driver", base)
    return local if os.path.isfile(local) else None


class TestF25PatchSourceSync(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(PATCH_PATH, "r", encoding="utf-8") as f:
            cls.sections = _split_sections(f.read().splitlines())

    # Byte-identical to upstream goodix-fp-linux-dev/libfprint@c343b69
    # (verified 2026-09-05); pristine files are correctly absent from the patch.
    PRISTINE_UPSTREAM = {"goodixtls.h", "goodix511.h", "goodix_proto.c"}

    def test_patch_covers_all_driver_files(self):
        """Every repo driver file must be patched or known-pristine upstream."""
        patched = set()
        for sec in self.sections:
            m = re.match(r"diff --git a/(.*) b/(.*)", sec[0])
            patched.add(os.path.basename(m.group(1)))
        for base in os.listdir(repo("libfprint-driver")):
            if base.endswith((".c", ".h")):
                self.assertTrue(
                    base in patched or base in self.PRISTINE_UPSTREAM,
                    f"{base} is neither in the unified patch nor known-pristine",
                )

    def test_new_files_match_working_tree_byte_for_byte(self):
        """New-file sections must reconstruct the repo sources exactly."""
        checked = 0
        for sec in self.sections:
            if not any(l.startswith("--- /dev/null") for l in sec):
                continue
            m = re.match(r"diff --git a/(.*) b/(.*)", sec[0])
            local = _local_counterpart(m.group(1))
            self.assertIsNotNone(local, f"new file {m.group(1)} has no repo counterpart")
            added = [l[1:] for l in sec if l.startswith("+") and not l.startswith("+++")]
            with open(local, "r", encoding="utf-8") as f:
                disk = f.read().splitlines()
            self.assertEqual(added, disk, f"patch copy of {m.group(1)} drifted from {local}")
            checked += 1
        self.assertGreater(checked, 0, "no new-file sections found in patch")

    def test_hunk_headers_are_self_consistent(self):
        """Every @@ -a,b +c,d @@ header must match its hunk's line counts."""
        hunks = 0
        for sec in self.sections:
            i = 0
            while i < len(sec):
                m = _HUNK_RE.match(sec[i])
                if not m:
                    i += 1
                    continue
                old_n = int(m.group(2)) if m.group(2) is not None else 1
                new_n = int(m.group(4)) if m.group(4) is not None else 1
                i += 1
                old_count = new_count = 0
                while i < len(sec) and not sec[i].startswith("@@") and not sec[i].startswith("diff --git"):
                    line = sec[i]
                    if line.startswith(" ") or line.startswith("-"):
                        old_count += 1
                    if line.startswith(" ") or line.startswith("+"):
                        new_count += 1
                    i += 1  # '\ No newline' marker lines match neither branch
                self.assertEqual(old_count, old_n, f"old count mismatch in hunk: {m.group(0)}")
                self.assertEqual(new_count, new_n, f"new count mismatch in hunk: {m.group(0)}")
                hunks += 1
        self.assertGreater(hunks, 0, "no hunks found in patch")


if __name__ == "__main__":
    unittest.main()
