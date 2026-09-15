"""
Tier 1 - Feature 84: Optimistic Verify Fast-Path (Ticket 84).

Verifies without hardware (hermetic static & structural validation):
(a) goodix5e0a.c implements optimistic verify fast-path in goodix5e0a_keep_best_frame:
    gated to non-enroll actions (verify or identify), frame_count == 1,
    active >= 1500, range >= 500;
(b) speculative verify tests frame 1 against self->tmpl_blob via goodix_milan_verify_image;
    if match_pts > 0, logs fast-path match and returns FALSE without re-issuing read_image;
(c) speculative identify tests frame 1 against gallery templates via goodix_milan_identify_image;
    if matched_idx >= 0 and match_pts > 0, logs fast-path identify match and returns FALSE;
(d) fallback to normal 4-frame burst loop intact when not matched or active < 1500 / range < 500;
(e) enrollment touch never enters fast-path (only non-enroll actions participate);
(f) score-proxy wording preserved; driver contains no bare score keyword;
(g) same-SSM burst invariants hold: no state transitions or completions inside keep_best_frame.
"""

import os
import unittest
from tests.repo_paths import repo

GOODIX5E0A_C = repo("libfprint-driver", "goodix5e0a.c")
GOODIX5E0A_H = repo("libfprint-driver", "goodix5e0a.h")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _slice(src, start_marker, end_marker):
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


class TestF84OptimisticVerifyFastPath(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.c_src = _read(GOODIX5E0A_C)
        cls.h_src = _read(GOODIX5E0A_H)
        keep_def = ("goodix5e0a_keep_best_frame (FpDevice *dev, gpointer ssm,\n"
                    "                            guint16 declen, guint active, guint range)\n{")
        cls.keep_body = cls.c_src[cls.c_src.index(keep_def):cls.c_src.index("goodix5e0a_on_fdt_up_reply (FpDevice *dev")]

    def test_a_fast_path_gate_and_thresholds(self):
        """Frame 1 fast-path is gated on non-enroll actions, frame 1, active >= 1500, range >= 500."""
        self.assertIn("Ticket 84: Optimistic Verify Fast-Path", self.keep_body)
        self.assertIn("self->frame_count == 1 && active >= 1500 && range >= 500", self.keep_body)
        self.assertIn("action == FPI_DEVICE_ACTION_VERIFY || self->is_verify", self.keep_body)
        self.assertIn("action == FPI_DEVICE_ACTION_IDENTIFY || self->is_identify", self.keep_body)

    def test_b_speculative_verify_fast_path(self):
        """Speculative verify matches frame 1, logs journal line, returns FALSE without read_image."""
        self.assertIn("goodix_milan_verify_image (self->best_pixels,", self.keep_body)
        self.assertIn("self->tmpl_blob,", self.keep_body)
        self.assertIn("self->tmpl_len,", self.keep_body)
        self.assertIn("&match_pts", self.keep_body)
        self.assertIn("5e0a optimistic fast-path match on frame 1: pts=%d, skipping remaining burst", self.keep_body)
        self.assertIn("return FALSE;", self.keep_body)

    def test_c_speculative_identify_fast_path(self):
        """Speculative identify matches gallery on frame 1, logs journal line, returns FALSE."""
        self.assertIn("fpi_device_get_identify_data (dev, &prints);", self.keep_body)
        self.assertIn("goodix5e0a_get_print_template (p, &v, &dl);", self.keep_body)
        self.assertIn("goodix_milan_identify_image (self->best_pixels,", self.keep_body)
        self.assertIn("&matched_idx, &match_pts);", self.keep_body)
        self.assertIn("5e0a optimistic fast-path identify match on frame 1: idx=%d pts=%d, skipping remaining burst", self.keep_body)

    def test_d_fallback_to_burst_intact(self):
        """When not matched or weak contact, loops frames 2..4 via goodix_tls_read_image."""
        self.assertIn("if (self->frame_count < GOODIX_5E0A_FRAMES_PER_TOUCH)", self.keep_body)
        self.assertIn("goodix_tls_read_image (dev, goodix5e0a_on_read_img, ssm);", self.keep_body)
        self.assertIn("return TRUE;", self.keep_body)

    def test_e_burst_invariants_preserved(self):
        """keep_best_frame performs no SSM transitions; bare score keyword forbidden."""
        for absent in ("fpi_ssm_next_state", "fpi_ssm_jump_to_state",
                       "fpi_ssm_mark_completed", "fpi_ssm_mark_failed"):
            self.assertNotIn(absent, self.keep_body)
        scrubbed = self.c_src.replace("score-proxy", "")
        self.assertNotIn("score", scrubbed)


if __name__ == "__main__":
    unittest.main()
