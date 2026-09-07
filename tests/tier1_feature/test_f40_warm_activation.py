"""
Tier 1 - Feature 40: Warm activation fast path (Ticket 40).

Verifies without hardware (hermetic static & structural validation):
(a) _FpiDeviceGoodixTls5e0a gains warm_ok / last_clean_mono / warm_boot_seq /
    warm_down_reason / warm_attempted / warm_retried beside the untouched
    ticket-38 park and ticket-39 burst fields;
(b) GOODIX_5E0A_WARM_TTL_US is 60s and a boot_seq counter lives in the shared
    priv (goodix.c, bumped in goodix_dev_init) with a goodix_boot_seq_get
    getter declared in goodix.h (img_open brackets the open session, not each
    claim, so the counter survives back-to-back verifies);
(c) activate_run_state skips via fpi_ssm_jump_to_state (NOT a reduced enum):
    RESET/READ_CHIP_ID/READ_OTP honor the warm flag and jump to
    CHECK_FW_VER, UPLOAD_CONFIG jumps to ACTIVATE_NUM_STATES (SSM completion
    = TLS handoff), while READ_AND_NOP never skips and CHECK_FW_VER is kept;
(d) dev_activate branches three ways in order AFTER the ticket-34 gen bump:
    38 parked-session check first, elif warm predicate, else today's full
    ladder (with the void-park cleanup ahead of the warm check and the
    expired-reason line on the cold path);
(e) BOTH loud-error funnels (activate_complete, on_tls_activation_complete)
    fall back once per claim on a failed warm attempt (intercept before
    completing, loop-guarded by warm_retried, TLS torn down on the TLS path)
    and invalidate warmth on every other failure;
(f) suspend always clears warmth (sleep safety); the ticket-34 gen-mismatch
    drop in on_tls_activation_complete is preserved;
(g) no scope creep: ticket-38 symbols, ticket-39 macro + single submit,
    bz3_threshold 12, exactly one goodix_tls_init site, no new SSM enum
    states, and no g_message beyond the four specified warm lines.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.h")
GOODIX_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.c")
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")
GOODIX5E0A_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.h")

WARM_TAKEN = "5e0a warm activation: reusing MCU config (age=%.1fs, boot_seq=%u)"
WARM_ENTRY = "5e0a warm path: skipping RESET + config upload, entry=CHECK_FW_VER"
WARM_EXPIRED = "5e0a warm expired: reason=%s"
WARM_FALLBACK = "5e0a warm attempt failed (%s), retrying full ladder"


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _slice(src, start_marker, end_marker):
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


class TestF40WarmActivation(unittest.TestCase):

    def test_a_struct_fields_and_init(self):
        """Warmth bookkeeping lives on the device struct; init zeroes it."""
        src = _read(GOODIX5E0A_C)
        struct = _slice(src, "struct _FpiDeviceGoodixTls5e0a",
                        "G_DECLARE_FINAL_TYPE")
        for field in ("gboolean              warm_ok;",
                      "gint64                last_clean_mono;",
                      "guint                 warm_boot_seq;",
                      "const char           *warm_down_reason;",
                      "gboolean              warm_attempted;",
                      "gboolean              warm_retried;"):
            self.assertIn(field, struct)
        # ticket-38 park and ticket-39 burst footprints untouched
        for field in ("gboolean              tls_parked;",
                      "gint64                tls_parked_at;",
                      "guint                 tls_parked_gen;",
                      "guint               frame_count;",
                      "FpImage            *best_img;",
                      "guint               best_minutiae;",
                      "guint               best_frame_no;"):
            self.assertIn(field, struct)
        init = _slice(src, "fpi_device_goodixtls5e0a_init",
                      "goodix5e0a_axis_correlation")
        for line in ("self->warm_ok = FALSE;",
                     "self->last_clean_mono = 0;",
                     "self->warm_boot_seq = 0;",
                     'self->warm_down_reason = "cold-start";',
                     "self->warm_attempted = FALSE;",
                     "self->warm_retried = FALSE;"):
            self.assertIn(line, init)

    def test_b_ttl_macro_and_boot_seq(self):
        """60s warm TTL by the activate enum; boot_seq counter in shared priv."""
        src = _read(GOODIX5E0A_C)
        head = _slice(src, "// ---- ACTIVATE SECTION START ----",
                      "enum activate_states")
        self.assertIn("#define GOODIX_5E0A_WARM_TTL_US (G_USEC_PER_SEC * 60)", head)
        c = _read(GOODIX_C)
        h = _read(GOODIX_H)
        # counter lives in shared priv beside the activation generation
        priv = _slice(c, "typedef struct", "} FpiDeviceGoodixTlsPrivate;")
        self.assertIn("guint         boot_seq;", priv)
        self.assertIn("guint         activation_gen;", priv)
        # bumped in goodix_dev_init next to the USB reset, getter beside the gen pair
        init = _slice(c, "goodix_dev_init (FpDevice *dev, GError **error)",
                      "goodix_reset_state (FpDevice *dev)")
        self.assertIn("priv->boot_seq++;", init)
        self.assertLess(init.index("priv->boot_seq++;"),
                        init.index("g_usb_device_claim_interface"))
        self.assertIn("guint goodix_boot_seq_get (FpDevice *dev);", h)
        impl = _slice(c, "goodix_boot_seq_get (FpDevice *dev)",
                      "goodix_dev_deinit (FpDevice *dev, GError **error)")
        self.assertIn("return priv->boot_seq;", impl)

    def test_c_warm_skips_via_jump(self):
        """Skippable states jump forward on the warm flag; kept states run."""
        src = _read(GOODIX5E0A_C)
        run = _slice(src, "activate_run_state (FpiSsm *ssm, FpDevice *dev)",
                     "on_chip_enabled")
        # RESET + CHIP_ID + OTP jump to the kept FW discriminator
        for state in ("case ACTIVATE_RESET:",
                      "case ACTIVATE_READ_CHIP_ID:",
                      "case ACTIVATE_READ_OTP:"):
            case = run[run.index(state):run.index("break;", run.index(state))]
            self.assertIn("if (self->warm_attempted)", case)
            self.assertIn("fpi_ssm_jump_to_state (ssm, ACTIVATE_CHECK_FW_VER);", case)
        # UPLOAD_CONFIG completes the SSM into the TLS handoff
        up = run[run.index("case ACTIVATE_UPLOAD_CONFIG:"):run.index("break;", run.index("case ACTIVATE_UPLOAD_CONFIG:"))]
        self.assertIn("if (self->warm_attempted)", up)
        self.assertIn("fpi_ssm_jump_to_state (ssm, ACTIVATE_NUM_STATES);", up)
        # READ_AND_NOP (mandatory: read loop restarts here) never skips
        nop = run[run.index("case ACTIVATE_READ_AND_NOP:"):run.index("case ACTIVATE_RESET:")]
        self.assertIn("goodix_start_read_loop (dev);", nop)
        self.assertNotIn("fpi_ssm_jump_to_state", nop)
        self.assertNotIn("warm_attempted", nop)
        # CHECK_FW_VER (discriminator) always runs
        fw = run[run.index("case ACTIVATE_CHECK_FW_VER:"):run.index("case ACTIVATE_UPLOAD_CONFIG:")]
        self.assertIn("goodix_send_query_firmware_version", fw)
        self.assertNotIn("fpi_ssm_jump_to_state", fw)
        # NOT a reduced enum: same six states, no warm-specific enumerator
        enum = _slice(src, "enum activate_states", "};")
        for state in ("ACTIVATE_READ_AND_NOP", "ACTIVATE_RESET",
                      "ACTIVATE_READ_CHIP_ID", "ACTIVATE_READ_OTP",
                      "ACTIVATE_CHECK_FW_VER", "ACTIVATE_UPLOAD_CONFIG",
                      "ACTIVATE_NUM_STATES"):
            self.assertIn(state, enum)
        self.assertNotIn("ACTIVATE_WARM", src)

    def test_d_three_way_branch_order(self):
        """Park check first, warm predicate second, full ladder last."""
        src = _read(GOODIX5E0A_C)
        act = _slice(src, "dev_activate (FpImageDevice *img_dev)",
                     "// ---- ACTIVATE SECTION END ----")
        park = act.index("self->tls_parked_gen == pre_gen")
        warm = act.index("goodix5e0a_warm_fresh (dev)")
        full = act.index("goodix5e0a_start_full_activation (dev);")
        self.assertLess(park, warm)
        self.assertLess(warm, full)
        # warm branch logs the taken line and starts the shared-SSM warm run
        warm_branch = act[warm:full]
        self.assertIn("goodix5e0a_log_warm_taken (dev);", warm_branch)
        self.assertIn("goodix5e0a_start_warm_activation (dev);", warm_branch)
        self.assertIn("return;", warm_branch)
        # cold branch names the invalidation reason before the full ladder
        self.assertIn("5e0a warm expired: reason=%s", act)
        self.assertIn('"ttl-expired"', act)
        self.assertIn('"cold-start"', act)
        expired_at = act.index("5e0a warm expired: reason=%s")
        self.assertIn("self->warm_attempted = FALSE;", act[expired_at - 1500:expired_at])
        # per-claim retry budget reset ahead of all three branches
        self.assertIn("self->warm_retried = FALSE;", act)
        self.assertLess(act.index("self->warm_retried = FALSE;"), park)
        # void-park cleanup still precedes the warm check (stale ctx shutdown
        # before any warm SSM, whose TLS handoff asserts tls_hop == NULL)
        void_park = act.index('reason = "gen-mismatch";')
        self.assertLess(void_park, warm)
        # warm starter is the shared SSM with the flag set, plus the entry line
        starter = _slice(src, "goodix5e0a_start_warm_activation (FpDevice *dev)",
                         "goodix5e0a_start_full_activation (FpDevice *dev)")
        self.assertIn(WARM_ENTRY, starter)
        self.assertIn("self->warm_attempted = TRUE;", starter)
        self.assertIn("fpi_ssm_new (dev, activate_run_state, ACTIVATE_NUM_STATES)", starter)
        self.assertIn("activate_complete", starter)
        self.assertNotIn("goodix_tls_init", starter)
        self.assertNotIn("goodix_shutdown_tls", starter)
        # full starter never skips
        ladder = _slice(src, "goodix5e0a_start_full_activation (FpDevice *dev)",
                        "on_parked_health_reply")
        self.assertIn("self->warm_attempted = FALSE;", ladder)

    def test_e_fallback_once_per_claim(self):
        """Both funnels retry the full ladder silently once, then stay loud."""
        src = _read(GOODIX5E0A_C)
        # "\n{" anchors on the definitions, not the forward declaration above
        for fn, end, extra in (
            ("activate_complete (FpiSsm *ssm, FpDevice *dev, GError *error)\n{",
             "dev_activate (FpImageDevice *img_dev)", ()),
            ("on_tls_activation_complete (FpDevice *dev, gpointer user_data, GError *error)\n{",
             "activate_complete (FpiSsm *ssm, FpDevice *dev, GError *error)\n{",
             ("goodix_shutdown_tls (dev, NULL);", "goodix_reset_state (dev);")),
        ):
            with self.subTest(fn=fn):
                funnel = _slice(src, fn, end)
                guard = funnel.index("if (self->warm_attempted && !self->warm_retried)")
                complete = funnel.index("fpi_image_device_activate_complete")
                # warm interception precedes the loud completion
                self.assertLess(guard, complete)
                err = funnel[guard:complete]
                self.assertIn(WARM_FALLBACK, err)
                self.assertIn("self->warm_ok = FALSE;", err)
                self.assertIn("self->warm_attempted = FALSE;", err)
                self.assertIn("self->warm_retried = TRUE;", err)
                self.assertIn("goodix5e0a_start_full_activation (dev);", err)
                self.assertIn("return;", err)
                for line in extra:
                    self.assertIn(line, err)
                # non-warm failures still invalidate warmth and stay loud
                loud = funnel[complete - 600:]
                self.assertIn("fpi_image_device_activate_complete", loud)
        # success stamps warmth (host→device proof) in exactly one place
        chip = _slice(src, "on_chip_enabled (FpDevice *dev, gpointer user_data, GError *error)",
                      "goodix5e0a_start_warm_activation")
        self.assertIn("self->warm_ok = TRUE;", chip)
        self.assertIn("self->last_clean_mono = g_get_monotonic_time ();", chip)
        self.assertIn("self->warm_boot_seq = goodix_boot_seq_get (dev);", chip)

    def test_f_suspend_clears_and_gen_guard_preserved(self):
        """Suspend unconditionally voids warmth; ticket-34 drop still first."""
        src = _read(GOODIX5E0A_C)
        susp = _slice(src, "goodix5e0a_suspend (FpDevice *dev)",
                      "goodix5e0a_resume (FpDevice *dev)")
        self.assertIn("self->warm_ok = FALSE;", susp)
        self.assertIn('self->warm_down_reason = "suspended";', susp)
        self.assertLess(susp.index("self->warm_ok = FALSE;"),
                        susp.index("goodix_shutdown_tls (dev, NULL);"))
        tls = _slice(src, "on_tls_activation_complete (FpDevice *dev, gpointer user_data, GError *error)",
                     "activate_complete (FpiSsm *ssm, FpDevice *dev, GError *error)")
        self.assertIn("GPOINTER_TO_UINT (user_data) != goodix_activation_gen_get (dev)", tls)
        self.assertIn("dropping stale TLS activation completion", tls)
        self.assertLess(tls.index("dropping stale TLS activation completion"),
                        tls.index("if (self->warm_attempted && !self->warm_retried)"))

    def test_g_transport_clears_crypto_preserves(self):
        """38 health probe: silent device voids warmth, live-key miss keeps it."""
        src = _read(GOODIX5E0A_C)
        cb = _slice(src, "on_parked_health_reply (FpDevice *dev, gpointer user_data, GError *error)",
                    "on_tls_activation_complete")
        self.assertIn("G_IO_ERROR_TIMED_OUT", cb)
        self.assertIn("self->warm_ok = FALSE;", cb)
        self.assertIn('self->warm_down_reason = "transport-miss";', cb)
        # crypto-grade miss re-enters the warm ladder when fresh
        self.assertIn("goodix5e0a_warm_fresh (dev)", cb)
        self.assertIn("goodix5e0a_start_warm_activation (dev);", cb)
        # ticket-38 fallback shape preserved on both halves
        self.assertIn("goodix_shutdown_tls (dev, NULL);", cb)
        self.assertIn("goodix5e0a_start_full_activation (dev);", cb)
        self.assertIn('reason = "timeout";', cb)

    def test_h_no_scope_creep(self):
        """38/39 pins hold; handshake never skipped; four warm lines only."""
        src = _read(GOODIX5E0A_C)
        # ticket-38 surface intact
        for sym in ("tls_parked", "on_parked_health_reply", "goodix_tls_is_alive",
                    "GOODIX_5E0A_TLS_PARK_TTL_US",
                    "GOODIX_5E0A_TLS_PARK_HEALTH_TIMEOUT_MS"):
            self.assertIn(sym, src)
        # ticket-39 surface intact
        self.assertIn("#define GOODIX_5E0A_FRAMES_PER_TOUCH 3", _read(GOODIX5E0A_H))
        self.assertEqual(src.count("fpi_image_device_image_captured ("), 1)
        self.assertIn("score-proxy", src)
        self.assertNotIn("score", src.replace("score-proxy", ""))
        # biometric operating point untouched
        self.assertIn("img_dev_class->bz3_threshold = 12;", src)
        # handshake never skipped: exactly one tls_init site (the shared
        # activate_complete handoff used by both ladders)
        self.assertEqual(src.count("goodix_tls_init ("), 1)
        # journal budget: the four specified warm lines across five new sites
        # (the fallback line serves both funnels) — 20 pre-existing + 5.
        for line in (WARM_TAKEN, WARM_ENTRY, WARM_EXPIRED, WARM_FALLBACK):
            self.assertIn(line, src)
        self.assertEqual(src.count("g_message ("), 25)


if __name__ == "__main__":
    unittest.main()
