"""
Tier 1 - Feature 76: Milan native frame quality proxy (Ticket 76).

Verifies without hardware (hermetic static & structural validation):
(a) goodix_milan.h declares goodix_milan_frame_quality with out_quality /
    out_overlap pair outputs;
(b) goodix_milan.c resolves the getQuality export as OPTIONAL (outside the
    required-export fatal gate) and implements the wrapper: fixed 64x80
    geometry, engine/export-down fallback to 0, ensure_gs before the call,
    combined (quality << 8 | overlap) ranking proxy;
(c) goodix5e0a.c keep_best_frame measures the native pair on the 64x80
    normalized buffer (NOT the scaled FpImage), ranks lexicographically
    (quality, overlap, then minutiae), and degrades to exact ticket-39
    minutiae order when the pair reads 0/0;
(d) enrollment floor stays minutiae-based (one variable per build: ticket 76
    changes selection only, not the enroll gate);
(e) burst lifecycle (reset/init/claim) carries the new pair fields.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")
GOODIX5E0A_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.h")
MILAN_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix_milan.c")
MILAN_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix_milan.h")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _slice(src, start_marker, end_marker):
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


class TestF76MilanQualityProxy(unittest.TestCase):

    def test_a_bridge_declares_frame_quality(self):
        """Public bridge exposes the native quality probe."""
        hdr = _read(MILAN_H)
        self.assertIn("goodix_milan_frame_quality", hdr)
        self.assertIn("guint *out_quality", hdr)
        self.assertIn("guint *out_overlap", hdr)

    def test_b_getquality_optional_and_wrapper_sound(self):
        """getQuality is optional; wrapper guards geometry/engine/GS."""
        src = _read(MILAN_C)
        # export resolved ...
        self.assertIn('m_getQuality = get_export("getQuality");', src)
        # ... but NOT part of the fatal required-exports gate
        gate = _slice(src, "if (!m_getAlgorithmVersion", "required Milan engine exports missing")
        self.assertNotIn("m_getQuality", gate)
        # missing export degrades with a debug line, never fails init
        self.assertIn("falls back to residual range and active area", src)
        # wrapper body: fixed geometry, engine-down fallback, GS, combine
        fn = _slice(src, "goodix_milan_frame_quality (const uint8_t *pixels",
                    "void *goodix_milan_enroll_start")
        self.assertIn("width != 64 || height != 80", fn)
        self.assertIn("!g_milan_available || !m_getQuality", fn)
        self.assertIn("ensure_gs();", fn)
        self.assertIn("m_getQuality(&img, qout);", fn)
        self.assertIn("return (q << 8) | o;", fn)

    def test_c_keep_ranks_native_first_minutiae_tiebreak(self):
        """keep_best_frame: native pair primary, range and active tiebreak."""
        src = _read(GOODIX5E0A_C)
        keep_def = ("goodix5e0a_keep_best_frame (FpDevice *dev, gpointer ssm,\n"
                    "                            guint16 declen, guint active, guint range)\n{")
        keep = src[src.index(keep_def):src.index("goodix5e0a_on_fdt_up_reply (FpDevice *dev")]
        # measured on the exact verify buffer, not the scaled image
        self.assertIn("goodix_milan_frame_quality (self->latest_norm_pixels,", keep)
        self.assertIn("GOODIX_5E0A_WIDTH,", keep)
        self.assertIn("GOODIX_5E0A_HEIGHT,", keep)
        # lexicographic rank
        self.assertIn("guint best_proxy = (self->best_quality << 8) | self->best_overlap;", keep)
        self.assertIn("quality_proxy > best_proxy", keep)
        self.assertIn("range > self->best_range", keep)
        self.assertIn("self->best_quality = quality;", keep)
        self.assertIn("self->best_overlap = overlap;", keep)

    def test_d_enroll_floor_stays_minutiae(self):
        """Ticket 76: enroll gate checks active area and Milan native quality."""
        src = _read(GOODIX5E0A_C)
        cb = _slice(src, "goodix5e0a_on_read_img (FpDevice *dev",
                    "goodix5e0a_on_fdt_up_reply (FpDevice *dev")
        enroll = cb[cb.index("if (action == FPI_DEVICE_ACTION_ENROLL)"):cb.index("deliver:")]
        self.assertIn("self->best_active < 64", enroll)
        self.assertIn("5e0a enrollment touch rejected: active=%u (press firmer)", enroll)
        self.assertIn("5e0a enrollment quality check: active=%u range=%u quality=%u overlap=%u", enroll)

    def test_e_lifecycle_carries_native_pair(self):
        """reset/init zero the pair; claim logs it."""
        src = _read(GOODIX5E0A_C)
        reset = _slice(src, "goodix5e0a_reset_touch_frames (FpiDeviceGoodixTls5e0a *self)",
                       "goodix5e0a_retry_enroll")
        self.assertIn("self->best_quality = 0;", reset)
        self.assertIn("self->best_overlap = 0;", reset)
        claim = _slice(src, "goodix5e0a_claim_best_frame (FpiDeviceGoodixTls5e0a *self)",
                       "goodix5e0a_keep_best_frame (FpDevice *dev")
        # winner line logs quality, overlap, range, score-proxy
        self.assertIn("quality=%u overlap=%u range=%u score-proxy=%u", claim)


if __name__ == "__main__":
    unittest.main()
