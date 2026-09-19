"""
Tier 1 - Feature 77: Multi-finger gallery identify (Ticket 77).

Verifies without hardware (hermetic static & structural validation):
(a) goodix_milan.h declares goodix_milan_identify_image (N-gallery, single
    identifyImage call, same >0 gate as verify, fail-closed);
(b) goodix_milan.c implements it: per-entry validation, engine init + GS,
    unpack-each with fail-closed cleanup, ONE m_identifyImage with
    count=n_templates, winner bounds-checked, unpacked handles deleted;
(c) goodix5e0a.c wires dev_identify: vtable entry, per-claim flags,
    deliver gallery branch (empty gallery / unusable frame -> no-match,
    winner reported as the exact gallery object, then complete);
(d) one variable per build: verify single-template path, 0x32=0 / 0x34
    re-issue semantics, enroll floor (16), and burst ranking are untouched;
(e) offline evidence lives in legacy-experiments/test_milan_gallery.c (exit 0 =
    4/4 genuine with correct idx, 3/3 impostor rejected, FAR 0%).
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")
MILAN_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix_milan.c")
MILAN_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix_milan.h")
GALLERY_C = os.path.join(REPO_ROOT, "legacy-experiments", "test_milan_gallery.c")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _slice(src, start_marker, end_marker):
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


class TestF77MultiFingerGallery(unittest.TestCase):

    def test_a_bridge_declares_gallery_identify(self):
        """Public bridge exposes the N-gallery identify entry."""
        hdr = _read(MILAN_H)
        self.assertIn("goodix_milan_identify_image", hdr)
        self.assertIn("const uint8_t **template_blobs", hdr)
        self.assertIn("const size_t *template_lens", hdr)
        self.assertIn("int n_templates", hdr)
        self.assertIn("int *out_idx", hdr)
        self.assertIn("int *out_score", hdr)

    def test_b_gallery_single_call_fail_closed(self):
        """One identifyImage(count=N); corrupt entries reject, never match."""
        src = _read(MILAN_C)
        fn = src[src.index("goodix_milan_identify_image (const uint8_t *pixels"):]
        # validation + engine/GS
        self.assertIn("n_templates <= 0", fn)
        self.assertIn("width != 64 || height != 80", fn)
        self.assertIn("ensure_gs();", fn)
        # unpack-each with fail-closed path
        self.assertIn("m_templateUnPack", fn)
        self.assertIn("fail_closed", fn)
        # single gallery call with the true count (never hardcoded 1 here)
        self.assertIn("m_identifyImage (&probe, NULL, unpacked, n_templates,", fn)
        # same >0 gate as verify + winner bounds check
        self.assertIn("matched_idx >= 0 && matched_idx < n_templates && match_score > 0", fn)
        # every unpacked handle deleted on both paths
        self.assertEqual(fn.count("m_templateDelete (unpacked[i]);"), 2)
        # verify single-template path still intact below
        self.assertIn("active_templates[1]", src)

    def test_c_driver_wires_identify(self):
        """vtable + flags + deliver gallery branch."""
        src = _read(GOODIX5E0A_C)
        # vtable
        self.assertIn("dev_class->identify = dev_identify;", src)
        # per-claim flags set in all three entries
        self.assertIn("gboolean            is_identify;", src)
        enroll = _slice(src, "dev_enroll (FpDevice *dev)", "dev_verify (FpDevice *dev)")
        self.assertIn("self->is_verify = FALSE;", enroll)
        self.assertIn("self->is_identify = FALSE;", enroll)
        # deliver has a dedicated IDENTIFY branch reporting the gallery object
        self.assertIn("action == FPI_DEVICE_ACTION_IDENTIFY || self->is_identify", src)
        self.assertIn("fpi_device_get_identify_data (dev, &prints);", src)
        self.assertIn("goodix_milan_identify_image (self->best_pixels,", src)
        self.assertIn("fpi_device_identify_report (dev, owners[match_idx], NULL, NULL);", src)
        self.assertIn("fpi_device_identify_report (dev, NULL, NULL, NULL);", src)
        self.assertIn("fpi_device_identify_complete (dev, NULL);", src)
        # empty gallery and unusable frames fail closed as no-match
        self.assertIn("empty gallery, reporting no-match", src)
        self.assertIn("no usable frame, reporting identify no-match", src)
        # identify is single-touch like verify: excluded from the enroll loop
        self.assertIn("!self->is_verify && !self->is_identify && self->enroll_stage", src)

    def test_d_verify_and_guards_untouched(self):
        """One variable: verify path, FDT semantics, enroll floor unchanged."""
        src = _read(GOODIX5E0A_C)
        # verify still single-template via tmpl_blob
        self.assertIn("goodix_milan_verify_image (self->best_pixels,", src)
        self.assertIn("fpi_device_verify_report (dev, FPI_MATCH_SUCCESS, NULL, NULL);", src)
        self.assertIn("fpi_device_verify_report (dev, FPI_MATCH_FAIL, NULL, NULL);", src)
        # FDT timeouts: DOWN blocking (0), UP finite guard/normal
        self.assertIn("GOODIX_CMD_MCU_SWITCH_TO_FDT_DOWN", src)
        self.assertIn("GOODIX_5E0A_FDT_UP_GUARD_TIMEOUT_MS", src)
        self.assertIn("GOODIX_5E0A_FDT_UP_TIMEOUT_MS", src)
        # CANCELLED never re-issues
        self.assertIn("CANCELLED must never fall back or re-issue", src)

    def test_e_offline_gallery_harness_present(self):
        """Offline probe source exists and encodes the zero-FAR verdict."""
        src = _read(GALLERY_C)
        self.assertIn("live_dense_pad_seed68", src)
        self.assertIn("goodix_milan_identify_image", src)
        self.assertIn("imp_ok, n_imp", src)
        self.assertIn("[VERDICT: CONFIRMED] 2-finger gallery isolates", src)


if __name__ == "__main__":
    unittest.main()
