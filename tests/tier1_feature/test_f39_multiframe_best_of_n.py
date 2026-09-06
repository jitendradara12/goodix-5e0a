"""
Tier 1 - Feature 39: Multi-frame best-of-N capture per touch (Ticket 39).

Verifies without hardware (hermetic static & structural validation):
(a) GOODIX_5E0A_FRAMES_PER_TOUCH is 3 in goodix5e0a.h;
(b) _FpiDeviceGoodixTls5e0a gains frame_count / best_img / best_minutiae /
    best_frame_no beside the untouched ticket-38 park fields;
(c) non-enroll touches re-issue goodix_tls_read_image from the keep helper
    while count < N, with no SSM advance on that path (exactly two
    read_image call sites: the GET_IMAGE state and the burst re-issue);
(d) per-frame / best-frame / short-fallback journal lines exist with the
    `score-proxy` wording (the driver never sees the core verdict, so bare
    `score` must not appear anywhere in the driver);
(e) enrollment keeps today's single-frame floor gate byte-identical and
    never enters the burst (N-loop gated to non-enroll);
(f) exactly one image_captured call site and one mark_completed site are
    preserved; the error fallback (mark_failed with zero frames,
    best-so-far submit otherwise) is intact;
(g) no scope creep: bz3_threshold stays 12 and the ticket-38 park symbols
    are still present.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")
GOODIX5E0A_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.h")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _slice(src, start_marker, end_marker):
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


class TestF39MultiframeBestOfN(unittest.TestCase):

    def test_a_frames_per_touch_macro_is_3(self):
        """Burst length N=3 lives in the header next to the enroll floor."""
        hdr = _read(GOODIX5E0A_H)
        self.assertIn("#define GOODIX_5E0A_FRAMES_PER_TOUCH 3", hdr)
        self.assertIn("#define GOODIX_5E0A_ENROLL_MIN_MINUTIAE (12)", hdr)

    def test_b_struct_counter_and_best_fields(self):
        """Per-touch burst state lives on the device struct; park fields stay."""
        src = _read(GOODIX5E0A_C)
        struct = _slice(src, "struct _FpiDeviceGoodixTls5e0a",
                        "G_DECLARE_FINAL_TYPE")
        for field in ("guint               frame_count;",
                      "FpImage            *best_img;",
                      "guint               best_minutiae;",
                      "guint               best_frame_no;"):
            self.assertIn(field, struct)
        # ticket-38 park footprint untouched
        for field in ("gboolean              tls_parked;",
                      "gint64                tls_parked_at;",
                      "guint                 tls_parked_gen;"):
            self.assertIn(field, struct)
        # init zeroes the new fields
        init = _slice(src, "fpi_device_goodixtls5e0a_init",
                      "goodix5e0a_axis_correlation")
        for field in ("self->frame_count = 0;",
                      "self->best_img = NULL;",
                      "self->best_minutiae = 0;",
                      "self->best_frame_no = 0;"):
            self.assertIn(field, init)

    def test_c_burst_reissue_without_ssm_advance(self):
        """Two read_image sites; the burst one loops until N, advancing nothing."""
        src = _read(GOODIX5E0A_C)
        self.assertEqual(src.count("goodix_tls_read_image ("), 2)
        self.assertIn("case SCAN_5E0A_GET_IMAGE:", src)
        # anchor on the definition (brace), not the prototype above on_read_img
        keep_def = ("goodix5e0a_keep_best_frame (FpDevice *dev, gpointer ssm, FpImage *img,\n"
                    "                            guint16 declen, guint active, guint range)\n{")
        keep = src[src.index(keep_def):src.index("goodix5e0a_on_fdt_up_reply (FpDevice *dev")]
        self.assertIn("if (self->frame_count < GOODIX_5E0A_FRAMES_PER_TOUCH)", keep)
        self.assertIn("goodix_tls_read_image (dev, goodix5e0a_on_read_img, ssm);", keep)
        self.assertLess(keep.index("goodix_tls_read_image (dev, goodix5e0a_on_read_img, ssm);"),
                        keep.index("return TRUE;"))
        # same-SSM burst: no state advance or completion inside the helper
        for absent in ("fpi_ssm_next_state", "fpi_ssm_jump_to_state",
                       "fpi_ssm_mark_completed", "fpi_ssm_mark_failed"):
            self.assertNotIn(absent, keep)
        # judging reuses the existing minutiae proxy; winner retained, loser unrefed
        self.assertIn("goodix5e0a_count_minutiae (img)", keep)
        self.assertIn("self->best_img = img;", keep)
        self.assertIn("g_object_unref (img);", keep)

    def test_d_journal_lines_and_score_proxy_wording(self):
        """Per-frame / best / short-fallback lines; never a bare `score`."""
        src = _read(GOODIX5E0A_C)
        self.assertIn("5e0a frame %u/%u: declen=%u active=%u range=%u "
                      "minutiae=%u score-proxy=%u", src)
        self.assertIn("5e0a best frame %u/%u: minutiae=%u score-proxy=%u (submitting)", src)
        self.assertIn("short declen=%u, submitting best-so-far %u/%u", src)
        # rendered output matches the hardware-verify grep `frame [0-9]/3|score`
        self.assertIn("GOODIX_5E0A_FRAMES_PER_TOUCH 3", _read(GOODIX5E0A_H))
        # driver cannot see the core verdict: `score` only inside `score-proxy`
        scrubbed = src.replace("score-proxy", "")
        self.assertNotIn("score", scrubbed)
        scrubbed_h = _read(GOODIX5E0A_H).replace("score-proxy", "")
        self.assertNotIn("score", scrubbed_h)

    def test_e_enroll_gate_intact_and_burst_gated(self):
        """Floor gate byte-identical; burst entered only off the enroll path."""
        src = _read(GOODIX5E0A_C)
        cb = _slice(src, "goodix5e0a_on_read_img (FpDevice *dev",
                    "goodix5e0a_on_fdt_up_reply (FpDevice *dev")
        # floor gate wording and retry behavior unchanged
        for line in ("5e0a enrollment quality check: minutiae_count=%u (floor=%d)",
                     "5e0a enrollment touch rejected: minutiae_count=%u < %d (press firmer)",
                     "GOODIX_5E0A_ENROLL_MIN_MINUTIAE",
                     "fpi_image_device_retry_scan (FP_IMAGE_DEVICE (dev), "
                     "FP_DEVICE_RETRY_TOO_SHORT);"):
            self.assertIn(line, cb)
        # enroll branch never touches the burst helpers
        enroll = cb[cb.index("if (action == FPI_DEVICE_ACTION_ENROLL)"):cb.index("deliver:")]
        enroll_gate = enroll[:enroll.index("fpi_image_device_retry_scan")]
        self.assertNotIn("goodix5e0a_keep_best_frame", enroll_gate)
        self.assertNotIn("goodix5e0a_claim_best_frame", enroll_gate)
        # burst + both fallbacks gated to non-enroll, before the shared tail
        self.assertIn("if (action != FPI_DEVICE_ACTION_ENROLL)", cb)
        burst = cb[cb.index("goodix5e0a_keep_best_frame (dev, ssm, img, len, "
                            "frame_active, frame_range)"):cb.index("deliver:")]
        self.assertIn("img = goodix5e0a_claim_best_frame (self);", burst)

    def test_f_single_submit_and_error_fallback(self):
        """One image_captured site, one mark_completed; zero-frame errors fail as today."""
        src = _read(GOODIX5E0A_C)
        self.assertEqual(src.count("fpi_image_device_image_captured ("), 1)
        self.assertIn("fpi_image_device_image_captured (FP_IMAGE_DEVICE (dev), img);", src)
        self.assertEqual(src.count("fpi_ssm_mark_completed ("), 1)
        cb = _slice(src, "goodix5e0a_on_read_img (FpDevice *dev",
                    "goodix5e0a_on_fdt_up_reply (FpDevice *dev")
        # error with a banked winner submits best-so-far; without, marks failed
        self.assertIn("if (action != FPI_DEVICE_ACTION_ENROLL && self->best_img != NULL)", cb)
        self.assertIn("g_error_free (err);", cb)
        self.assertIn("fpi_ssm_mark_failed (ssm, err);", cb)
        # claim helper logs the best line and releases ownership exactly once
        claim = _slice(src, "goodix5e0a_claim_best_frame (FpiDeviceGoodixTls5e0a *self)",
                       "goodix5e0a_keep_best_frame (FpDevice *dev")
        self.assertIn("5e0a best frame %u/%u: minutiae=%u score-proxy=%u (submitting)", claim)
        self.assertIn("self->best_img = NULL;", claim)

    def test_g_resets_on_touch_claim_and_teardown(self):
        """Burst state resets at touch start, claim entry, and every teardown."""
        src = _read(GOODIX5E0A_C)
        pairs = (
            ("goodix5e0a_scan_start (FpDevice *dev)",
             "goodix5e0a_change_state"),
            ("dev_activate (FpImageDevice *img_dev)",
             "// ---- ACTIVATE SECTION END ----"),
            ("goodix5e0a_scan_complete (FpiSsm *ssm, FpDevice *dev, GError *error)",
             "goodix5e0a_scan_start (FpDevice *dev)"),
            ("goodix5e0a_deactivate (FpImageDevice *img_dev)",
             "// ---- SCAN SECTION END ----"),
            ("goodix5e0a_suspend (FpDevice *dev)",
             "goodix5e0a_resume (FpDevice *dev)"),
        )
        for fn, end in pairs:
            with self.subTest(fn=fn):
                body = _slice(src, fn, end)
                self.assertIn("goodix5e0a_reset_touch_frames (self);", body)

    def test_h_no_scope_creep(self):
        """Threshold and ticket-38 park symbols are untouched."""
        src = _read(GOODIX5E0A_C)
        self.assertIn("img_dev_class->bz3_threshold = 12;", src)
        for sym in ("tls_parked", "on_parked_health_reply", "goodix_tls_is_alive"):
            self.assertIn(sym, src)
        for state in ("SCAN_5E0A_SESSION_AE", "SCAN_5E0A_SESSION_D6",
                      "SCAN_5E0A_FDT_DOWN", "SCAN_5E0A_GET_IMAGE",
                      "SCAN_5E0A_FDT_UP_1", "SCAN_5E0A_UP_AE",
                      "SCAN_5E0A_FDT_UP_2", "SCAN_5E0A_NUM_STATES"):
            self.assertIn(state, src)


if __name__ == "__main__":
    unittest.main()
