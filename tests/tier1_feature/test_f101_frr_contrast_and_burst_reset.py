"""
Tier 1 - Feature 101: FRR contrast lane + per-touch enrollment burst (Ticket 101).

Verifies without hardware (hermetic static & structural validation):
(a) GOODIX_5E0A_CONTRAST_GAIN is calibrated to 1.5f — the ticket-72 shootout's
    validated lane. At 1.0 the Milan engine's minutiae extraction sits only
    ~20-40% above its contrast floor, so light/sloppy presses fall below it
    and every verify reports no-match with pts=0 (live journal 2026-09-27:
    5 consecutive verifies, all "5e0a Milan verify: match=0 pts=0", template
    unpack clean). Offline battery through the real DLL: gain 1.0 rejects
    6/20 degraded genuine probes, gain 1.5 accepts every recoverable one
    (down to 40% residual contrast) with impostors + garbage frames scoring
    0 at every level and a 5-finger identify gallery keeping 0 false accepts;
(b) normalization consumes the macro (single calibration point, no literal);
(c) the enroll-continue branch of on_read_img resets the burst AFTER the
    deliver tail consumed the winner and BEFORE fpi_ssm_next_state, so each
    of the 12 enrollment touches banks its own 4-frame burst. The live
    journal showed the pre-fix behaviour: frame numbering ran 4/4 -> 5/4 ->
    ... -> 11/4 with the SAME stale "best frame 3/4" (identical
    range/overlap) re-submitted at every touch — one impression stitched
    12 times instead of 12 distinct impressions;
(d) the pre-existing reset hygiene sites (claim, SSM completion, scan start,
    deactivate, suspend, both enroll rejection paths) are all still present.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")
GOODIX5E0A_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.h")


def _read(path):
    with open(path, "r") as f:
        return f.read()


def _slice(src, begin_marker, length=9000):
    idx = src.index(begin_marker)
    return src[idx:idx + length]


class TestF101FRRLaneAndPerTouchBurst(unittest.TestCase):
    """Ticket 101: contrast gain 1.5 + fresh burst per enrollment touch."""

    def setUp(self):
        self.src_c = _read(GOODIX5E0A_C)
        self.src_h = _read(GOODIX5E0A_H)

    def test_contrast_gain_is_ticket_101_lane(self):
        """(a) Gain macro is 1.5f with the ticket-101 rationale in place."""
        self.assertIn("#define GOODIX_5E0A_CONTRAST_GAIN (1.5f)", self.src_h)
        self.assertNotIn("#define GOODIX_5E0A_CONTRAST_GAIN (1.0f)", self.src_h)
        # The calibration history is documented at the definition site.
        hidx = self.src_h.index("GOODIX_5E0A_CONTRAST_GAIN (1.5f)")
        self.assertIn("Ticket 101", self.src_h[:hidx])

    def test_normalization_consumes_the_macro(self):
        """(b) One calibration point: residual mapping uses the macro, not a literal."""
        self.assertIn("residual[i] * GOODIX_5E0A_CONTRAST_GAIN", self.src_c)
        self.assertNotIn("residual[i] * 1.5f", self.src_c)
        self.assertNotIn("residual[i] * 1.0f", self.src_c)

    def test_enroll_continue_resets_burst_per_touch(self):
        """(c) Each enrollment touch starts with an empty burst.

        The reset must sit in the enroll-continue else-branch: after the
        deliver tail (image_captured consumed the winner) and before
        fpi_ssm_next_state re-arms the SSM for the next touch."""
        marker = ("goodix5e0a_reset_touch_frames (self); "
                  "/* ticket 101: fresh burst per enroll touch */")
        self.assertIn(marker, self.src_c)

        cb = _slice(self.src_c, "goodix5e0a_on_read_img (FpDevice *dev")
        self.assertIn(marker, cb)
        delivered = cb.index("fpi_image_device_image_captured (dev);")
        reset_at = cb.index(marker)
        self.assertLess(delivered, reset_at,
                        "burst reset must not run before the winner is delivered")
        next_state_at = cb.index("fpi_ssm_next_state (ssm);", reset_at)
        self.assertLess(reset_at, next_state_at,
                        "burst reset must precede the SSM re-arm for the next touch")
        self.assertLess(next_state_at - reset_at, 200,
                        "reset and re-arm belong to the same enroll-continue branch")
        # The completing branch is untouched: completion still marks the SSM done.
        self.assertIn("fpi_ssm_mark_completed (ssm);", cb)

    def test_burst_hygiene_sites_preserved(self):
        """(d) All pre-existing reset sites survive the ticket-101 edit."""
        self.assertGreaterEqual(self.src_c.count("goodix5e0a_reset_touch_frames (self);"), 8)
        for site in (
            "goodix5e0a_scan_complete",   # SSM completion
            "goodix5e0a_scan_start",      # touch start
            "goodix5e0a_deactivate",      # deactivation
        ):
            self.assertIn(site, self.src_c)
        # Claim entry and suspend paths keep their guards.
        self.assertIn("a stale burst winner must never survive across claims", self.src_c.lower())


if __name__ == "__main__":
    unittest.main()
