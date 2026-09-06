"""
Tier 1 - Feature 38: Persistent TLS session across claims (Ticket 38).

Verifies without hardware (hermetic static & structural validation):
(a) _FpiDeviceGoodixTls5e0a gains tls_parked / tls_parked_at / tls_parked_gen;
(b) TTL macro (30s) + short health-check timeout macro (500ms) exist;
(c) goodix_tls_is_alive() helper lives in goodix.c/h (5e0a never reaches
    into priv->tls_hop directly);
(d) deactivate parks (stop read loop only + stamp) when the ctx is alive,
    and keeps the destroy branch (shutdown + flag clear) otherwise;
(e) dev_activate captures the pre-bump gen, reuses a fresh park via ONE
    QUERY_MCU_STATE probe + read-loop restart (no tls_init on that path —
    tls_init appears exactly once in the file, for the full ladder);
(f) fallback paths shut the parked ctx down and run today's full ladder
    exactly once, with gen-mismatch drops and the four named reasons;
(g) suspend always clears the park and shuts down (sleep safety);
(h) no scope creep: scan SSM enum, bz3_threshold, ACTIVATE_RESET and
    ACTIVATE_UPLOAD_CONFIG are untouched.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.h")
GOODIX_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.c")
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _slice(src, start_marker, end_marker):
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


class TestF38TlsPark(unittest.TestCase):

    def test_a_struct_fields(self):
        """Park state lives on the 5e0a device struct with the right types."""
        src = _read(GOODIX5E0A_C)
        struct = _slice(src, "struct _FpiDeviceGoodixTls5e0a",
                        "G_DECLARE_FINAL_TYPE")
        self.assertIn("gboolean              tls_parked;", struct)
        self.assertIn("gint64                tls_parked_at;", struct)
        self.assertIn("guint                 tls_parked_gen;", struct)

    def test_b_ttl_and_health_timeout_macros(self):
        """30s park TTL and 500ms probe timeout are defined by the activate enum."""
        src = _read(GOODIX5E0A_C)
        head = _slice(src, "// ---- ACTIVATE SECTION START ----",
                      "enum activate_states")
        self.assertIn("#define GOODIX_5E0A_TLS_PARK_TTL_US (G_USEC_PER_SEC * 30)", head)
        self.assertIn("#define GOODIX_5E0A_TLS_PARK_HEALTH_TIMEOUT_MS 500", head)

    def test_c_tls_alive_helper(self):
        """Liveness query is a goodix.c/h getter; 5e0a never touches tls_hop."""
        h = _read(GOODIX_H)
        c = _read(GOODIX_C)
        src = _read(GOODIX5E0A_C)
        self.assertIn("gboolean goodix_tls_is_alive (FpDevice *dev);", h)
        impl = _slice(c, "goodix_tls_is_alive (FpDevice *dev)",
                      "goodix_tls_ready_image_handler")
        self.assertIn("priv->tls_hop != NULL", impl)
        self.assertNotIn("->tls_hop", src)
        self.assertIn("goodix_tls_is_alive (dev)", src)

    def test_d_park_on_deactivate(self):
        """Alive ctx -> park (read-loop stop only + stamp); dead ctx -> destroy."""
        src = _read(GOODIX5E0A_C)
        deact = _slice(src, "goodix5e0a_deactivate (FpImageDevice *img_dev)",
                       "// ---- SCAN SECTION END ----")
        # ticket-34 bump still first
        self.assertIn("goodix_activation_gen_bump (dev);", deact)
        # park branch
        self.assertIn("if (goodix_tls_is_alive (dev) && self->warm_ok)", deact)
        self.assertIn("self->tls_parked = TRUE;", deact)
        self.assertIn("self->tls_parked_at = g_get_monotonic_time ();", deact)
        self.assertIn("self->tls_parked_gen = goodix_activation_gen_get (dev);", deact)
        park_idx = deact.index("self->tls_parked = TRUE;")
        destroy_idx = deact.index("self->tls_parked = FALSE;")
        park_branch = deact[deact.index("if (goodix_tls_is_alive (dev) && self->warm_ok)"):destroy_idx]
        self.assertIn("goodix_stop_read_loop (dev);", park_branch)
        self.assertNotIn("goodix_shutdown_tls", park_branch)
        # destroy branch preserved: flag clear + shutdown + stop + complete
        destroy = deact[destroy_idx:]
        self.assertIn("goodix_shutdown_tls (dev, &tls_err);", destroy)
        self.assertIn("goodix_stop_read_loop (dev);", destroy)
        self.assertIn("fpi_image_device_deactivate_complete (img_dev, tls_err);", destroy)

    def test_e_reuse_branch(self):
        """Fresh park -> read-loop restart + ONE short 0xae probe, no handshake."""
        src = _read(GOODIX5E0A_C)
        act = _slice(src, "dev_activate (FpImageDevice *img_dev)",
                     "// ---- ACTIVATE SECTION END ----")
        # stale-guard ordering: pre-bump capture, then bump, then comparison
        self.assertIn("guint pre_gen = goodix_activation_gen_get (dev);", act)
        self.assertIn("guint new_gen = goodix_activation_gen_bump (dev);", act)
        self.assertLess(act.index("pre_gen = goodix_activation_gen_get"),
                        act.index("new_gen = goodix_activation_gen_bump"))
        self.assertIn("self->tls_parked_gen == pre_gen", act)
        self.assertIn("GOODIX_5E0A_TLS_PARK_TTL_US", act)
        # reuse attempt mechanics
        self.assertIn("goodix_start_read_loop (dev);", act)
        self.assertIn("GOODIX_CMD_QUERY_MCU_STATE", act)
        self.assertIn("GOODIX_5E0A_TLS_PARK_HEALTH_TIMEOUT_MS", act)
        self.assertIn("on_parked_health_reply", act)
        self.assertIn("GUINT_TO_POINTER (new_gen)", act)
        self.assertIn("goodix_receive_none", act)
        # park claimed before the probe so fallback cannot loop
        self.assertLess(act.index("self->tls_parked = FALSE;"),
                        act.index("GOODIX_CMD_QUERY_MCU_STATE"))
        # no tls_init anywhere on the reuse path: exactly one call site in
        # the whole file (activate_complete, the full ladder)
        self.assertEqual(src.count("goodix_tls_init ("), 1)

    def test_f_health_callback(self):
        """Probe reply: stale drop, error fallback (named reason), success reuse."""
        src = _read(GOODIX5E0A_C)
        cb = _slice(src, "on_parked_health_reply (FpDevice *dev, gpointer user_data, GError *error)",
                    "on_tls_activation_complete")
        # gen-mismatch drop before any hardware touch
        self.assertIn("GPOINTER_TO_UINT (user_data)", cb)
        self.assertIn("!= goodix_activation_gen_get (dev)", cb)
        self.assertIn("dropping stale parked-TLS health reply", cb)
        self.assertIn("g_error_free (error);", cb)
        self.assertLess(cb.index("return;"), cb.index("goodix_send_enable_chip"))
        # error -> named reason + shutdown + full ladder, once
        self.assertIn('reason = "tls-error";', cb)
        self.assertIn('reason = "timeout";', cb)
        self.assertIn("G_IO_ERROR_TIMED_OUT", cb)
        self.assertIn("5e0a parked TLS session unhealthy (%s), full re-handshake", cb)
        self.assertIn("goodix_shutdown_tls (dev, NULL);", cb)
        self.assertIn("goodix5e0a_start_full_activation (dev);", cb)
        # success -> reuse line + chip-enable confirm, flag stays claimed
        self.assertIn("5e0a TLS session reused (parked %.1fs, gen=%u)", cb)
        self.assertIn("goodix_send_enable_chip (dev, TRUE, on_chip_enabled, NULL);", cb)

    def test_f_sync_fallback_reasons(self):
        """Void park at activate entry names expired/gen-mismatch, then full ladder."""
        src = _read(GOODIX5E0A_C)
        act = _slice(src, "dev_activate (FpImageDevice *img_dev)",
                     "// ---- ACTIVATE SECTION END ----")
        # second "if (self->tls_parked)" — the "\n" excludes the reuse guard above
        tail = act[act.index("if (self->tls_parked)\n"):]
        self.assertIn('reason = "gen-mismatch";', tail)
        self.assertIn('reason = "expired";', tail)
        self.assertIn("5e0a parked TLS session unhealthy (%s), full re-handshake", tail)
        self.assertIn("goodix_shutdown_tls (dev, NULL);", tail)
        self.assertIn("goodix5e0a_start_full_activation (dev);", tail)

    def test_g_suspend_clears_park(self):
        """Suspend never carries a parked session (sleep safety)."""
        src = _read(GOODIX5E0A_C)
        susp = _slice(src, "goodix5e0a_suspend (FpDevice *dev)",
                      "goodix5e0a_resume (FpDevice *dev)")
        self.assertIn("self->tls_parked = FALSE;", susp)
        self.assertIn("goodix_shutdown_tls (dev, NULL);", susp)
        self.assertLess(susp.index("self->tls_parked = FALSE;"),
                        susp.index("goodix_shutdown_tls (dev, NULL);"))

    def test_h_no_scope_creep(self):
        """Scan SSM, threshold, and full-ladder states are untouched."""
        src = _read(GOODIX5E0A_C)
        run = _slice(src, "activate_run_state (FpiSsm *ssm, FpDevice *dev)",
                     "on_chip_enabled")
        self.assertIn("case ACTIVATE_RESET:", run)
        self.assertIn("case ACTIVATE_UPLOAD_CONFIG:", run)
        # full-ladder helper preserves today's ladder entry
        ladder = _slice(src, "goodix5e0a_start_full_activation (FpDevice *dev)",
                        "on_parked_health_reply")
        self.assertIn("self->session_started = FALSE;", ladder)
        self.assertIn("fpi_ssm_new (dev, activate_run_state, ACTIVATE_NUM_STATES)", ladder)
        self.assertIn("activate_complete", ladder)
        # scan SSM enum intact (8 states incl. NUM_STATES)
        for state in ("SCAN_5E0A_SESSION_AE", "SCAN_5E0A_SESSION_D6",
                      "SCAN_5E0A_FDT_DOWN", "SCAN_5E0A_GET_IMAGE",
                      "SCAN_5E0A_FDT_UP_1", "SCAN_5E0A_UP_AE",
                      "SCAN_5E0A_FDT_UP_2", "SCAN_5E0A_NUM_STATES"):
            self.assertIn(state, src)
        # biometric operating point untouched
        self.assertIn("img_dev_class->bz3_threshold = 12;", src)
        # init zeroes the new fields
        init = _slice(src, "fpi_device_goodixtls5e0a_init",
                      "goodix5e0a_axis_correlation")
        self.assertIn("self->tls_parked = FALSE;", init)
        self.assertIn("self->tls_parked_at = 0;", init)
        self.assertIn("self->tls_parked_gen = 0;", init)


if __name__ == "__main__":
    unittest.main()
