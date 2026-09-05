"""
Tier 1 - Feature 24: Automated Biometric Bozorth Matching and NBIS Minutiae Verification.
Requirements:
- Verify NBIS mindtct minutiae extraction on real/fixture frames extracts >= 12 minutiae (no floor abort).
- Verify Bozorth3 matching against gallery prints yields a score clearing threshold (>= 12).
- Verify enrollment gate GOODIX_5E0A_ENROLL_MIN_MINUTIAE >= 12 guarantees gallery template quality.
"""

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.test_utils import (
    SENSOR_WIDTH,
    SENSOR_HEIGHT,
    FRAME_PIXELS,
    IMAGE_OUT_WIDTH,
    IMAGE_OUT_HEIGHT,
    process_raw_frame,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BOZORTH_BIN = REPO_ROOT / "experiments" / "test_bozorth_verify"
PGM_FIXTURE = REPO_ROOT / "experiments" / "fingerprint.pgm"
TMP_PGM = Path("/tmp/live_touch.pgm")
HEADER_PATH = REPO_ROOT / "libfprint-driver" / "goodix5e0a.h"
C_PATH = REPO_ROOT / "libfprint-driver" / "goodix5e0a.c"


class TestF24BiometricBozorth(unittest.TestCase):
    """Automated tests for biometric minutiae extraction and Bozorth3 matching."""

    @classmethod
    def setUpClass(cls):
        # Unconditionally refresh /tmp/live_touch.pgm from repo fixture
        if PGM_FIXTURE.exists():
            shutil.copyfile(PGM_FIXTURE, TMP_PGM)

    def setUp(self):
        # Guarantee fixture integrity before each test method
        if PGM_FIXTURE.exists():
            shutil.copyfile(PGM_FIXTURE, TMP_PGM)

    @classmethod
    def tearDownClass(cls):
        # Restore clean fixture after test suite completion
        if PGM_FIXTURE.exists():
            shutil.copyfile(PGM_FIXTURE, TMP_PGM)

    def test_automated_bozorth_verification_pipeline(self):
        """Execute test_bozorth_verify binary and assert mindtct minutiae >= 12 and Bozorth score >= 12."""
        self.assertTrue(BOZORTH_BIN.exists(), f"Missing Bozorth verification binary: {BOZORTH_BIN}")
        self.assertTrue(TMP_PGM.exists(), f"Missing PGM fixture: {TMP_PGM}")

        res = subprocess.run(
            [str(BOZORTH_BIN)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, f"Bozorth verification binary exited with {res.returncode}: {res.stderr}")
        stdout = res.stdout

        # Verify Gallery minutiae >= 12
        gallery_match = re.search(r"Gallery minutiae:\s*(\d+)", stdout)
        self.assertIsNotNone(gallery_match, "Missing Gallery minutiae in output")
        gallery_minutiae = int(gallery_match.group(1))
        self.assertGreaterEqual(
            gallery_minutiae, 12,
            f"Gallery minutiae count {gallery_minutiae} must be >= 12 to prevent floor abort"
        )

        # Verify Probe minutiae >= 12
        probe_match = re.search(r"Probe minutiae:\s*(\d+)", stdout)
        self.assertIsNotNone(probe_match, "Missing Probe minutiae in output")
        probe_minutiae = int(probe_match.group(1))
        self.assertGreaterEqual(
            probe_minutiae, 12,
            f"Probe minutiae count {probe_minutiae} must be >= 12 to prevent floor abort"
        )

        # Verify Self-Match Score >= 12
        self_match = re.search(r"Bozorth3 Self-Match Score:\s*(\d+)", stdout)
        self.assertIsNotNone(self_match, "Missing Bozorth3 Self-Match Score in output")
        self_score = int(self_match.group(1))
        self.assertGreaterEqual(
            self_score, 12,
            f"Self-match score {self_score} must clear match threshold >= 12"
        )

        # Verify Probe-Match Score >= 12
        probe_score_match = re.search(r"Bozorth3 Probe-Match Score:\s*(\d+)", stdout)
        self.assertIsNotNone(probe_score_match, "Missing Bozorth3 Probe-Match Score in output")
        probe_score = int(probe_score_match.group(1))
        self.assertGreaterEqual(
            probe_score, 12,
            f"Probe-match score {probe_score} must clear match threshold >= 12"
        )

        self.assertIn(">>> VERIFICATION SUCCESSFUL! <<<", stdout)

    def test_fixture_frame_quality_and_contrast_filtering(self):
        """Verify fixture sensor frame has valid dynamic range and produces normalized residual image."""
        self.assertTrue(PGM_FIXTURE.exists(), f"Fixture file not found: {PGM_FIXTURE}")
        content = PGM_FIXTURE.read_text(encoding="ascii")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]

        header_tokens = lines[0].split()
        if len(header_tokens) == 1:
            magic = header_tokens[0]
            dim_tokens = lines[1].split()
            w, h = int(dim_tokens[0]), int(dim_tokens[1])
            max_v = int(lines[2].split()[0])
            pixel_data_lines = lines[3:]
        else:
            magic = header_tokens[0]
            w, h = int(header_tokens[1]), int(header_tokens[2])
            max_v = int(header_tokens[3])
            pixel_data_lines = lines[1:]

        self.assertEqual(magic, "P2")
        self.assertEqual(w, 64)
        self.assertEqual(h, 80)


        raw_pixels = []
        for line in pixel_data_lines:
            raw_pixels.extend(int(tok) for tok in line.split())

        self.assertEqual(len(raw_pixels), FRAME_PIXELS)
        min_px = min(raw_pixels)
        max_px = max(raw_pixels)
        self.assertGreaterEqual(min_px, 0)
        self.assertGreater(max_px, min_px)
        self.assertGreaterEqual(max_px - min_px, 200, "Fixture dynamic range must exceed 200 ADC counts")



        # Run 3x3 local contrast filtering and demosaicing
        upscaled = process_raw_frame(raw_pixels, width=w, height=h)
        self.assertEqual(len(upscaled), IMAGE_OUT_WIDTH * IMAGE_OUT_HEIGHT)
        self.assertTrue(any(px > 0 for px in upscaled), "Filtered frame must have non-zero pixels")

    def test_enrollment_quality_gate_in_driver_code(self):
        """Verify GOODIX_5E0A_ENROLL_MIN_MINUTIAE is configured >= 12 in driver header and C file."""
        self.assertTrue(HEADER_PATH.exists(), f"Header not found: {HEADER_PATH}")
        header_text = HEADER_PATH.read_text(encoding="utf-8")

        enroll_match = re.search(r"#define\s+GOODIX_5E0A_ENROLL_MIN_MINUTIAE\s+\(?(\d+)\)?", header_text)
        self.assertIsNotNone(enroll_match, "GOODIX_5E0A_ENROLL_MIN_MINUTIAE not found in header")
        enroll_min = int(enroll_match.group(1))
        self.assertGreaterEqual(enroll_min, 12, "Enrollment minutiae floor must be >= 12")

        c_text = C_PATH.read_text(encoding="utf-8")
        self.assertIn("img_dev_class->bz3_threshold = 12;", c_text)
        self.assertIn("minutiae_count < GOODIX_5E0A_ENROLL_MIN_MINUTIAE", c_text)

    def test_bozorth_floor_guarantee(self):
        """Verify that minutiae floor >= 12 strictly prevents NBIS Bozorth floor abort (< 10 minutiae)."""
        bozorth_min_computable = 10
        header_text = HEADER_PATH.read_text(encoding="utf-8")
        enroll_min = int(re.search(r"#define\s+GOODIX_5E0A_ENROLL_MIN_MINUTIAE\s+\(?(\d+)\)?", header_text).group(1))
        self.assertGreater(
            enroll_min, bozorth_min_computable,
            f"Enrollment floor ({enroll_min}) must strictly exceed NBIS Bozorth floor ({bozorth_min_computable})"
        )

    def test_degraded_frame_fails_verification(self):
        """Verify that an invalid/blank degraded frame fails minutiae extraction (< 10) and Bozorth verification."""
        self.assertTrue(BOZORTH_BIN.exists(), f"Missing Bozorth verification binary: {BOZORTH_BIN}")
        try:
            # Overwrite /tmp/live_touch.pgm with a flat/blank frame (uniform ADC counts)
            with open(TMP_PGM, "w", encoding="ascii") as f:
                f.write("P2\n64 80\n4095\n" + " ".join(["2048"] * 5120) + "\n")

            res = subprocess.run(
                [str(BOZORTH_BIN)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0, f"Bozorth verification binary crashed: {res.stderr}")
            stdout = res.stdout

            # Verification output must indicate failure, never success
            self.assertIn(">>> VERIFICATION FAILED! <<<", stdout)
            self.assertNotIn(">>> VERIFICATION SUCCESSFUL! <<<", stdout)

            # Minutiae count must be strictly below 10 (floor threshold)
            gallery_match = re.search(r"Gallery minutiae:\s*(\d+)", stdout)
            self.assertIsNotNone(gallery_match, "Missing Gallery minutiae in output")
            gallery_minutiae = int(gallery_match.group(1))
            self.assertLess(gallery_minutiae, 10, f"Expected < 10 minutiae for flat frame, got {gallery_minutiae}")

            probe_match = re.search(r"Probe minutiae:\s*(\d+)", stdout)
            self.assertIsNotNone(probe_match, "Missing Probe minutiae in output")
            probe_minutiae = int(probe_match.group(1))
            self.assertLess(probe_minutiae, 10, f"Expected < 10 minutiae for flat frame, got {probe_minutiae}")

            # Match score must be strictly below 12
            probe_score_match = re.search(r"Bozorth3 Probe-Match Score:\s*(\d+)", stdout)
            self.assertIsNotNone(probe_score_match, "Missing Bozorth3 Probe-Match Score in output")
            probe_score = int(probe_score_match.group(1))
            self.assertLess(probe_score, 12, f"Match score {probe_score} should be < 12 for degraded frame")
        finally:
            if PGM_FIXTURE.exists():
                shutil.copyfile(PGM_FIXTURE, TMP_PGM)


if __name__ == "__main__":
    unittest.main()
