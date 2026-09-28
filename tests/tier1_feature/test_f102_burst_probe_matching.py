"""
Tier 1 - Feature 102: Burst-wide matching probes (Ticket 102).

Verifies without hardware (hermetic static & structural validation):
(a) every frame of the per-touch burst is banked (pixels + active count) in
    goodix5e0a_keep_best_frame and zeroed by goodix5e0a_reset_touch_frames, so
    probe state never leaks across touches;
(b) goodix5e0a_burst_probe_order returns the ranked winner first, then every
    other usable frame in capture order, exactly once, and never a frame that
    failed normalization (active < 64, buffer zeroed);
(c) verify and identify probe the whole burst in that order and report the
    engine's own per-frame verdict — first match wins, and the matching
    frame's points are what the caller sees;
(d) exactly one verifyImage and one identifyImage call site; the deliver tail
    and the ticket-84 fast path share goodix5e0a_verify_burst, so the fast
    path can never widen what counts as a match;
(e) per-frame decisions are unchanged (the engine's own >0 gate), the ranked
    winner stays in best_pixels for enrollment, and the ticket-39/76 journal
    lines plus the 25 g_message budget are untouched.
"""

import unittest
from tests.repo_paths import repo

GOODIX5E0A_C = repo("libfprint-driver", "goodix5e0a.c")

FRAMES = 4
PROBE_ACTIVE_MIN = 64


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _function_body(src, signature):
    """Body of the function whose definition is `signature` + a newline + `{`."""
    start = src.index(signature + "\n{")
    end = src.index("\n}\n", start)
    return src[start:end]


def _model_probe_order(frame_count, best_frame_no, burst_active):
    """Python mirror of goodix5e0a_burst_probe_order (statement-for-statement).

    Returns the 0-based indexes the driver would probe, in order.
    """
    banked = min(frame_count, FRAMES)
    best = best_frame_no
    order = []

    if best > 0 and best <= banked and burst_active[best - 1] >= PROBE_ACTIVE_MIN:
        order.append(best - 1)
    for i in range(banked):
        if (len(order) == 0 or i != order[0]) and burst_active[i] >= PROBE_ACTIVE_MIN:
            order.append(i)
    return order


class TestF102BurstProbeMatching(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read(GOODIX5E0A_C)

    def test_a_burst_is_banked_per_frame_and_reset(self):
        """The burst arrays exist, are banked in keep_best_frame, and are zeroed."""
        struct = self.src[self.src.index("struct _FpiDeviceGoodixTls5e0a"):
                           self.src.index("G_DECLARE_FINAL_TYPE")]
        self.assertIn("guint8              burst_pixels[GOODIX_5E0A_FRAMES_PER_TOUCH][GOODIX_5E0A_FRAME_SIZE];",
                      struct)
        self.assertIn("guint               burst_active[GOODIX_5E0A_FRAMES_PER_TOUCH];",
                      struct)

        reset = _function_body(self.src,
                               "goodix5e0a_reset_touch_frames (FpiDeviceGoodixTls5e0a *self)")
        self.assertIn("memset (self->burst_pixels, 0, sizeof (self->burst_pixels));", reset)
        self.assertIn("memset (self->burst_active, 0, sizeof (self->burst_active));", reset)

        keep = _function_body(
            self.src,
            "goodix5e0a_keep_best_frame (FpDevice *dev, gpointer ssm,\n"
            "                            guint16 declen, guint active, guint range)")
        self.assertIn("memcpy (self->burst_pixels[self->frame_count - 1], self->latest_norm_pixels,",
                      keep)
        self.assertIn("self->burst_active[self->frame_count - 1] = active;", keep)
        # 1-based frame_count, bounded by the burst length
        self.assertIn("if (self->frame_count <= GOODIX_5E0A_FRAMES_PER_TOUCH)", keep)
        # the ranked winner is still banked for enrollment
        self.assertIn("memcpy (self->best_pixels, self->latest_norm_pixels, GOODIX_5E0A_FRAME_SIZE);",
                      keep)

    def test_b_probe_order_winner_first_then_capture_order(self):
        """The order helper's shape is pinned, and its model behaviour is checked."""
        order_fn = _function_body(
            self.src,
            "goodix5e0a_burst_probe_order (FpiDeviceGoodixTls5e0a *self, guint *order)")
        self.assertIn("guint banked = MIN (self->frame_count, (guint) GOODIX_5E0A_FRAMES_PER_TOUCH);",
                      order_fn)
        self.assertIn("guint best = self->best_frame_no;", order_fn)
        self.assertIn("if (best > 0 && best <= banked && self->burst_active[best - 1] >= 64)",
                      order_fn)
        self.assertIn("order[n++] = best - 1;", order_fn)
        self.assertIn("if ((n == 0 || i != order[0]) && self->burst_active[i] >= 64)",
                      order_fn)
        self.assertIn("order[n++] = i;", order_fn)
        self.assertIn("return n;", order_fn)

        # Mirror checks: winner first, others in capture order, unusable skipped,
        # every usable frame probed exactly once.
        self.assertEqual(_model_probe_order(4, 3, [900, 900, 900, 900]), [2, 0, 1, 3])
        self.assertEqual(_model_probe_order(4, 1, [900, 900, 900, 900]), [0, 1, 2, 3])
        self.assertEqual(_model_probe_order(4, 2, [900, 0, 900, 900]), [0, 2, 3])
        self.assertEqual(_model_probe_order(4, 4, [900, 900, 900, 0]), [0, 1, 2])
        self.assertEqual(_model_probe_order(2, 4, [900, 900, 900, 900]), [0, 1])
        self.assertEqual(_model_probe_order(4, 0, [900, 900, 900, 900]), [0, 1, 2, 3])
        self.assertEqual(_model_probe_order(4, 4, [10, 20, 30, 40]), [])
        self.assertEqual(_model_probe_order(0, 0, [900, 900, 900, 900]), [])
        self.assertEqual(_model_probe_order(2, 2, [900, 900, 900, 900]), [1, 0])
        # no duplicate probes, never more than the banked burst
        for best in range(0, 5):
            for actives in ([900] * 4, [900, 0, 900, 0], [0, 0, 900, 0], [0] * 4):
                order = _model_probe_order(4, best, actives)
                self.assertEqual(len(order), len(set(order)))
                self.assertLessEqual(len(order), FRAMES)
                for i in order:
                    self.assertGreaterEqual(actives[i], PROBE_ACTIVE_MIN)

    def test_c_verify_probes_the_whole_burst(self):
        """One verifyImage call site probes each usable frame, winner first."""
        helper = self.src[self.src.index("goodix5e0a_verify_burst (FpiDeviceGoodixTls5e0a *self"):
                          self.src.index("/* Ticket 77/84:")]
        self.assertIn("guint probes = goodix5e0a_burst_probe_order (self, order);", helper)
        self.assertIn("goodix_milan_verify_image (self->burst_pixels[order[i]],", helper)
        self.assertIn("self->tmpl_blob,", helper)
        self.assertIn("self->tmpl_len,", helper)
        # first engine match wins and its points are reported
        self.assertIn("if (matched)", helper)
        self.assertIn("*out_pts = frame_pts;", helper)
        self.assertEqual(self.src.count("goodix_milan_verify_image ("), 1)

        # The deliver tail and the ticket-84 fast path both use that helper.
        verify_branch = self.src[self.src.index("if (action == FPI_DEVICE_ACTION_VERIFY || self->is_verify)"):
                                self.src.index("else if (action == FPI_DEVICE_ACTION_IDENTIFY || self->is_identify)")]
        self.assertIn("guint probes = goodix5e0a_burst_probe_order (self, order);",
                      verify_branch)
        self.assertIn("gboolean is_match = goodix5e0a_verify_burst (self, &match_pts);",
                      verify_branch)
        self.assertNotIn("best_active", verify_branch)
        fast_path = self.src[self.src.index("Ticket 84: Optimistic Verify Fast-Path"):
                             self.src.index("if (self->frame_count < GOODIX_5E0A_FRAMES_PER_TOUCH)")]
        self.assertIn("if (goodix5e0a_verify_burst (self, &match_pts))", fast_path)
        self.assertNotIn("match_pts > 0", helper)

    def test_d_identify_probes_the_whole_burst(self):
        """One identifyImage call site probes each usable frame; fail-closed kept."""
        helper = self.src[self.src.index("goodix5e0a_identify_best_frame (FpDevice *dev"):
                          self.src.index("\nstatic void\ngoodix5e0a_deliver_frame")]
        self.assertIn("guint probes = goodix5e0a_burst_probe_order (self, order);", helper)
        self.assertIn("goodix_milan_identify_image (self->burst_pixels[order[i]],", helper)
        self.assertIn("blobs, lens, (int) m,", helper)
        self.assertIn("for (guint i = 0; i < probes && !matched; i++)", helper)
        self.assertEqual(self.src.count("goodix_milan_identify_image ("), 1)
        # engine verdict plus bounds check before any winner object is used
        self.assertIn("if (matched && idx >= 0 && (guint) idx < m)", helper)
        self.assertIn("*out_print = owners[idx];", helper)
        # unavailable gallery templates still fail closed with the old journal line
        self.assertIn("5e0a Milan identify: match=0 idx=-1 pts=0 (gallery=%u usable=0)", helper)

    def test_e_no_usable_frame_gate_is_the_burst(self):
        """Both deliver branches treat 'no usable burst frame' as no-match."""
        verify_branch = self.src[self.src.index("if (action == FPI_DEVICE_ACTION_VERIFY || self->is_verify)"):
                                self.src.index("else if (action == FPI_DEVICE_ACTION_IDENTIFY || self->is_identify)")]
        self.assertIn("if (probes == 0)", verify_branch)
        self.assertIn("5e0a no usable frame, reporting no-match", verify_branch)
        self.assertIn("fpi_device_verify_report (dev, FPI_MATCH_FAIL, NULL, NULL);", verify_branch)

        identify_branch = self.src[self.src.index("else if (action == FPI_DEVICE_ACTION_IDENTIFY || self->is_identify)"):
                                  self.src.index("else if (action == FPI_DEVICE_ACTION_ENROLL)")]
        self.assertIn("if (probes == 0)", identify_branch)
        self.assertIn("5e0a no usable frame, reporting identify no-match", identify_branch)
        self.assertIn("fpi_device_identify_report (dev, NULL, NULL, NULL);", identify_branch)

    def test_f_journal_and_engine_contract_untouched(self):
        """Per-probe lines are debug-only; the verdict journal and gates survive."""
        self.assertIn('fp_dbg ("5e0a verify probe %u/%u (frame %u): match=%d pts=%d"', self.src)
        self.assertIn('fp_dbg ("5e0a identify probe %u/%u (frame %u): match=%d idx=%d pts=%d"', self.src)
        self.assertIn('fp_dbg ("5e0a Milan verify: match=%d pts=%d", is_match, match_pts);', self.src)
        self.assertIn('fp_dbg ("5e0a Milan identify: match=%d idx=%d pts=%d (gallery=%u usable=%u)"', self.src)
        # always-on journal budget untouched (no new g_message sites)
        self.assertEqual(self.src.count("g_message ("), 25)
        # the driver never sees the core decision: no bare `score`
        scrubbed = self.src.replace("score-proxy", "")
        self.assertNotIn("score", scrubbed)
        # the per-frame probe list is a hard bound, never a heap allocation
        self.assertIn("guint order[GOODIX_5E0A_FRAMES_PER_TOUCH];", self.src)


if __name__ == "__main__":
    unittest.main()
