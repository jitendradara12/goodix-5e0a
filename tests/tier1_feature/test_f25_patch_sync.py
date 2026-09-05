"""
Tier 1 - Feature 25: Unified Patch / Driver Source Synchronization
Requirements: the committed 0001-*.patch must embed the exact current
libfprint-driver/ sources, so a driver edit without patch regeneration
fails loudly instead of shipping stale code to NixOS.
"""

import hashlib
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
            if cur and cur[0].startswith("diff --git"):
                sections.append(cur)
            cur = [line]
        else:
            cur.append(line)
    if cur and cur[0].startswith("diff --git"):
        sections.append(cur)
    # Only diff sections survive: a git-format-patch mail preamble (or any
    # trailing junk) is dropped instead of crashing consumers with
    # AttributeError on a None regex match.
    return sections


def _local_counterpart(patch_path):
    base = os.path.basename(patch_path)
    local = repo("libfprint-driver", base)
    return local if os.path.isfile(local) else None


def _count_hunk_body(sec, i):
    """Count old/new lines from index i to the next header or end.

    Returns (old_count, new_count, next_i)."""
    old_count = new_count = 0
    while i < len(sec) and not sec[i].startswith("@@") and not sec[i].startswith("diff --git"):
        line = sec[i]
        if line.startswith(" ") or line.startswith("-"):
            old_count += 1
        if line.startswith(" ") or line.startswith("+"):
            new_count += 1
        i += 1  # '\ No newline' marker lines match neither branch
    return old_count, new_count, i


def _reconstruct_new_file(sec):
    """Rebuild exact new-file bytes from '+' lines, honoring '\ No newline'."""
    chunks = []
    for line in sec:
        if line.startswith("+++") or not line.startswith(("+", "\\")):
            continue
        if line.startswith("\\"):
            if chunks and chunks[-1].endswith("\n"):
                chunks[-1] = chunks[-1][:-1]
        else:
            chunks.append(line[1:] + "\n")
    return "".join(chunks)


class TestF25PatchSourceSync(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(PATCH_PATH, "r", encoding="utf-8") as f:
            cls.sections = _split_sections(f.read().splitlines())

    # Byte-identical to upstream goodix-fp-linux-dev/libfprint@c343b69
    # (verified 2026-09-05 via byte comparison against raw.githubusercontent);
    # pristine files are correctly absent from the patch. Hashes pin this so
    # an edit without patch regeneration fails instead of going unnoticed.
    PRISTINE_UPSTREAM = {
        "goodixtls.h": "ffb7ada4a4a320470495d2524841fe1ec8567befae62ebebd294954f9804fbaf",
        "goodix511.h": "d6039cf218ab7a299b38e3e87de1af952c671fd6519cc58c737d824c4bf0a9c0",
        "goodix_proto.c": "dd4aad34da3249899dcd595dc6702d1a907cd990f7f987d033b8bb5b031fe72a",
    }

    def test_patch_covers_all_driver_files(self):
        """Every repo driver file must be patched or known-pristine upstream."""
        patched = set()
        for sec in self.sections:
            for line in sec:
                self.assertFalse(
                    line.startswith("Binary files "),
                    f"binary patch section cannot be byte-verified: {sec[0]}",
                )
            m = re.match(r"diff --git a/(.*) b/(.*)", sec[0])
            patched.add(os.path.basename(m.group(1)))
        for base in os.listdir(repo("libfprint-driver")):
            if base.endswith((".c", ".h")):
                self.assertTrue(
                    base in patched or base in self.PRISTINE_UPSTREAM,
                    f"{base} is neither in the unified patch nor known-pristine",
                )

    def test_pristine_files_match_pinned_hashes(self):
        """Pristine files must still be byte-identical to upstream c343b69."""
        for base, expected in self.PRISTINE_UPSTREAM.items():
            with open(repo("libfprint-driver", base), "rb") as f:
                actual = hashlib.sha256(f.read()).hexdigest()
            self.assertEqual(
                actual, expected,
                f"{base} changed: regenerate the patch or update the pin",
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
            with open(local, "r", encoding="utf-8") as f:
                disk = f.read()
            self.assertEqual(
                _reconstruct_new_file(sec), disk,
                f"patch copy of {m.group(1)} drifted from {local}",
            )
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
                old_count, new_count, i = _count_hunk_body(sec, i + 1)
                self.assertEqual(old_count, old_n, f"old count mismatch in hunk: {m.group(0)}")
                self.assertEqual(new_count, new_n, f"new count mismatch in hunk: {m.group(0)}")
                hunks += 1
        self.assertGreater(hunks, 0, "no hunks found in patch")


class TestPatchParser(unittest.TestCase):
    """Unit tests for the section splitter and new-file reconstruction."""

    def test_drops_mail_preamble(self):
        """A git-format-patch mail header must not become a section."""
        lines = [
            "From abc123 Mon Sep 17 00:00:00 2001",
            "From: A U Thor",
            "Subject: [PATCH] x",
            "---",
            "diff --git a/f b/f",
            "new file mode 100644",
            "--- /dev/null",
            "+++ b/f",
            "@@ -0,0 +1 @@",
            "+hi",
        ]
        secs = _split_sections(lines)
        self.assertEqual(len(secs), 1)
        self.assertTrue(secs[0][0].startswith("diff --git"))

    def test_reconstruct_honors_no_trailing_newline(self):
        """'\\ No newline' marker must strip the reconstructed final newline."""
        sec = [
            "diff --git a/f b/f",
            "--- /dev/null",
            "+++ b/f",
            "@@ -0,0 +1,2 @@",
            "+hi",
            "+bye",
            "\\ No newline at end of file",
        ]
        self.assertEqual(_reconstruct_new_file(sec), "hi\nbye")

    def test_count_hunk_body(self):
        """Body counter must tally old/new lines and stop at the next header."""
        sec = [" context", "-old", "+new", " context", "@@ -1,1 +1,1 @@"]
        old, new, nxt = _count_hunk_body(sec, 0)
        self.assertEqual((old, new, nxt), (3, 3, 4))

    def test_count_hunk_body_ignores_no_newline_marker(self):
        """Marker lines must count toward neither side."""
        sec = ["+only", "\\ No newline at end of file"]
        old, new, nxt = _count_hunk_body(sec, 0)
        self.assertEqual((old, new, nxt), (0, 1, 2))

    def test_reconstruction_detects_single_byte_drift(self):
        """Flipping one byte in a real new-file section must change output.

        Proves the byte-exact test above is sensitive, not vacuous."""
        with open(PATCH_PATH, "r", encoding="utf-8") as f:
            secs = _split_sections(f.read().splitlines())
        sec = next(s for s in secs if any(l.startswith("--- /dev/null") for l in s))
        original = _reconstruct_new_file(sec)
        mutated, flipped = [], False
        for line in sec:
            if not flipped and line.startswith("+") and not line.startswith("+++") and len(line) > 1:
                mutated.append("+" + ("X" if line[1] != "X" else "Y") + line[2:])
                flipped = True
            else:
                mutated.append(line)
        self.assertTrue(flipped, "no mutable '+' line found")
        self.assertNotEqual(_reconstruct_new_file(mutated), original)


if __name__ == "__main__":
    unittest.main()
