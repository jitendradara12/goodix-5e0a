"""
Tier 1 - Feature 47: Verify-Retry Finger Release Guard (Ticket 47).

Hermetic static and structural validation:
(a) _FpiDeviceGoodixTls5e0a gains retry_guard and retry_guard_mono fields;
(b) fpi_device_goodixtls5e0a_init zeroes retry_guard and retry_guard_mono;
(c) goodix5e0a_on_read_img deliver path stamps retry_guard = TRUE and records
    retry_guard_mono on non-enroll actions;
(d) goodix5e0a_scan_start checks retry_guard and expires it after 2000ms TTL;
(e) SCAN_5E0A_SESSION_D6 jumps to SCAN_5E0A_FDT_UP_1 when retry_guard is TRUE;
(f) SCAN_5E0A_FDT_UP_2 uses 2000ms timeout when retry_guard is TRUE;
(g) goodix5e0a_on_fdt_up_reply clears retry_guard and jumps to SCAN_5E0A_FDT_DOWN;
(h) goodix5e0a_suspend and goodix5e0a_scan_complete reset retry_guard;
(i) bz3_threshold is 14 and nr_enroll_stages is 5 (Ticket 43 operating point).
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _slice(src, start_marker, end_marker):
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


class TestF47VerifyRetryReleaseGuard(unittest.TestCase):

    def test_a_struct_fields(self):
        """_FpiDeviceGoodixTls5e0a contains retry_guard and retry_guard_mono."""
        src = _read(GOODIX5E0A_C)
        struct = _slice(src, "struct _FpiDeviceGoodixTls5e0a", "G_DECLARE_FINAL_TYPE")
        self.assertIn("gboolean            retry_guard;", struct)
        self.assertIn("gint64              retry_guard_mono;", struct)

    def test_b_init_zeroes_fields(self):
        """fpi_device_goodixtls5e0a_init initializes retry_guard fields."""
        src = _read(GOODIX5E0A_C)
        init = _slice(src, "fpi_device_goodixtls5e0a_init", "goodix5e0a_axis_correlation")
        self.assertIn("self->retry_guard = FALSE;", init)
        self.assertIn("self->retry_guard_mono = 0;", init)

    def test_c_deliver_stamps_retry_guard(self):
        """Verify deliver path stamps retry_guard = TRUE and records monotonic time."""
        src = _read(GOODIX5E0A_C)
        deliver = _slice(src, "deliver:", "/* Ticket 39:")
        self.assertIn("self->retry_guard = TRUE;", deliver)
        self.assertIn("self->retry_guard_mono = g_get_monotonic_time ();", deliver)
        self.assertIn("fpi_image_device_report_finger_status (FP_IMAGE_DEVICE (dev), FALSE);", deliver)

    def test_d_scan_start_ttl_check(self):
        """goodix5e0a_scan_start expires retry_guard after 2000ms TTL."""
        src = _read(GOODIX5E0A_C)
        scan_start = _slice(src, "goodix5e0a_scan_start (FpDevice *dev)", "goodix5e0a_change_state")
        self.assertIn("if (self->retry_guard)", scan_start)
        self.assertIn("delta_us > 2 * G_USEC_PER_SEC", scan_start)
        self.assertIn("self->retry_guard = FALSE;", scan_start)

    def test_e_session_d6_routes_to_fdt_up(self):
        """SCAN_5E0A_SESSION_D6 jumps to SCAN_5E0A_FDT_UP_1 when retry_guard is active."""
        src = _read(GOODIX5E0A_C)
        run_state = _slice(src, "goodix5e0a_scan_run_state", "goodix5e0a_scan_complete")
        self.assertIn("if (self->retry_guard)", run_state)
        self.assertIn("fpi_ssm_jump_to_state (ssm, SCAN_5E0A_FDT_UP_1);", run_state)
        self.assertIn("fpi_ssm_jump_to_state (ssm, SCAN_5E0A_FDT_DOWN);", run_state)

    def test_f_fdt_up_2_timeout_bounded(self):
        """SCAN_5E0A_FDT_UP_2 uses 2000ms timeout when retry_guard is active."""
        src = _read(GOODIX5E0A_C)
        run_state = _slice(src, "goodix5e0a_scan_run_state", "goodix5e0a_scan_complete")
        self.assertIn("self->retry_guard ? 2000 : 5000", run_state)

    def test_g_fdt_up_reply_clears_guard_and_arms_fdt_down(self):
        """goodix5e0a_on_fdt_up_reply clears retry_guard and transitions to FDT_DOWN."""
        src = _read(GOODIX5E0A_C)
        up_reply = _slice(src, "goodix5e0a_on_fdt_up_reply", "goodix5e0a_scan_run_state")
        self.assertIn("if (self->retry_guard)", up_reply)
        self.assertIn("self->retry_guard = FALSE;", up_reply)
        self.assertIn("fpi_ssm_jump_to_state (ssm, SCAN_5E0A_FDT_DOWN);", up_reply)
        self.assertIn("return;", up_reply)

    def test_g2_fdt_up_timeout_reissues_while_held(self):
        """0x34 timeout with guard set re-issues FDT_UP (held finger is not a release)."""
        src = _read(GOODIX5E0A_C)
        up_reply = _slice(src, "goodix5e0a_on_fdt_up_reply", "goodix5e0a_scan_run_state")
        # cancelled teardown never re-issues on an orphaned SSM
        self.assertIn("G_IO_ERROR_CANCELLED", up_reply)
        self.assertIn("fpi_ssm_mark_failed (ssm, err);", up_reply)
        # timeout + live guard re-arms the same FDT_UP probe, guard kept
        self.assertIn("if (self->retry_guard && self->scan_ssm == ssm)", up_reply)
        self.assertIn("finger still present, re-issuing FDT UP", up_reply)
        self.assertIn("GOODIX_CMD_MCU_SWITCH_TO_FDT_UP", up_reply)
        self.assertIn("2000, goodix5e0a_on_fdt_up_reply, ssm", up_reply)
        # the re-issue precedes the release-ok clear, so a timeout can never clear
        self.assertLess(up_reply.index("re-issuing FDT UP"),
                        up_reply.index("release ok, arming FDT DOWN"))

    def test_h_teardown_and_suspend_safety(self):
        """Suspend, scan complete error, and destroy deactivate reset retry_guard."""
        src = _read(GOODIX5E0A_C)
        suspend = _slice(src, "goodix5e0a_suspend (FpDevice *dev)", "fpi_device_goodixtls5e0a_class_init")
        self.assertIn("self->retry_guard = FALSE;", suspend)

        scan_complete = _slice(src, "goodix5e0a_scan_complete", "goodix5e0a_scan_start")
        self.assertIn("self->retry_guard = FALSE;", scan_complete)

    def test_i_threshold_and_enroll_stages_pinned(self):
        """Ticket 43 operating point holds: threshold 14, 5 enroll stages."""
        src = _read(GOODIX5E0A_C)
        class_init = _slice(src, "fpi_device_goodixtls5e0a_class_init", "fpi_device_class_auto_initialize_features")
        self.assertIn("dev_class->nr_enroll_stages = 5;", class_init)
        self.assertIn("img_dev_class->bz3_threshold = 14;", class_init)


if __name__ == "__main__":
    unittest.main()
