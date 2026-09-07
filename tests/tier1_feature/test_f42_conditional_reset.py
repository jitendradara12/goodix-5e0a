"""
Tier 1 - Feature 42: Conditional USB reset on open (Ticket 42).

Verifies without hardware (hermetic static & structural validation):
(a) shared priv (goodix.c) gains `clean_close` (FALSE = reset, safe
    direction) plus a cheap USB-identity snapshot for re-enumeration;
    goodix.h exports the mark_clean / mark_dirty / is_clean helpers;
(b) goodix_dev_init gates the reset on the flag, couples boot_seq++ to
    the reset actually taken (not the open), forces dirty on
    re-enumeration, and logs taken-vs-skipped as always-on lines;
(c) goodix_dev_deinit skips BOTH the gen bump and the TLS shutdown on a
    clean close and keeps both verbatim on a dirty close;
(d) the single TRUE site is the goodix5e0a_deactivate park branch
    (destroy-after-error/success stays dirty); every failure funnel
    (activate_complete, on_tls_activation_complete, on_chip_enabled,
    scan_complete), suspend entry, and claim failure clear to dirty;
(e) suspend still bumps + clears park/warm + shuts down (untouched
    except the added clean clear);
(f) no scope creep: ticket-38 park/health, ticket-39 burst, ticket-40
    predicate/branch, bz3_threshold 12, single tls_init, 25 g_message
    lines in goodix5e0a.c.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.h")
GOODIX_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.c")
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")
GOODIX5E0A_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.h")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _slice(src, start_marker, end_marker):
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


class TestF42ConditionalReset(unittest.TestCase):

    def test_a_priv_field_and_helpers(self):
        """clean_close + USB-identity snapshot live in shared priv; helpers exported."""
        c = _read(GOODIX_C)
        h = _read(GOODIX_H)
        priv = _slice(c, "typedef struct", "} FpiDeviceGoodixTlsPrivate;")
        self.assertIn("gboolean      clean_close;", priv)
        # cheap re-enumeration detector: bus/address/port/vid/pid snapshot
        for field in ("last_usb_bus;", "last_usb_addr;", "last_usb_port;",
                      "last_usb_vid;", "last_usb_pid;", "usb_identity_valid;"):
            self.assertIn(field, priv)
        # safe direction documented: zero-init FALSE = reset
        self.assertIn("FALSE", priv)
        # helpers declared + implemented, single clean/dirty lifetime
        for sym in ("goodix_session_mark_clean (FpDevice *dev);",
                    "goodix_session_mark_dirty (FpDevice *dev);",
                    "goodix_session_is_clean (FpDevice *dev);"):
            self.assertIn(sym, h)
        for sym in ("goodix_session_mark_clean (FpDevice *dev)\n{",
                    "goodix_session_mark_dirty (FpDevice *dev)\n{",
                    "goodix_session_is_clean (FpDevice *dev)\n{"):
            self.assertIn(sym, c)
        self.assertIn("priv->clean_close = TRUE;", c)
        self.assertIn("priv->clean_close = FALSE;", c)
        # TRUE is set only via the helper (park branch calls it; goodix.c
        # itself never assigns TRUE — safe direction cannot self-heal)
        init = _slice(c, "goodix_dev_init (FpDevice *dev, GError **error)",
                      "goodix_reset_state (FpDevice *dev)")
        self.assertNotIn("priv->clean_close = TRUE", init)

    def test_b_reset_conditional_in_dev_init(self):
        """Open takes the reset only when dirty; taken-vs-skipped is logged."""
        c = _read(GOODIX_C)
        init = _slice(c, "goodix_dev_init (FpDevice *dev, GError **error)",
                      "goodix_reset_state (FpDevice *dev)")
        # gating variable derived from the flag
        self.assertIn("take_reset", init)
        self.assertIn("!priv->clean_close", init)
        self.assertIn("g_usb_device_reset", init)
        self.assertIn("g_usb_device_claim_interface", init)
        # reset lives inside the taken branch, claim follows the block
        self.assertLess(init.index("take_reset = !priv->clean_close"),
                        init.index("g_usb_device_reset"))
        self.assertLess(init.index("g_usb_device_reset"),
                        init.index("g_usb_device_claim_interface"))
        # always-on lines MUST distinguish taken vs skipped
        self.assertIn("5e0a USB reset taken", init)
        self.assertIn("5e0a USB reset skipped", init)
        # journal budget in goodix.c: exactly the open-path lines, nothing else
        self.assertEqual(c.count("g_message ("), 3)

    def test_c_boot_seq_coupled_to_reset_taken(self):
        """Counter follows the reset, not the open (no unconditional bump)."""
        c = _read(GOODIX_C)
        init = _slice(c, "goodix_dev_init (FpDevice *dev, GError **error)",
                      "goodix_reset_state (FpDevice *dev)")
        # exactly one bump in the open path, inside the taken branch
        self.assertEqual(init.count("priv->boot_seq++;"), 1)
        taken = init[init.index("if (take_reset)"):init.index("g_usb_device_reset") + 30]
        self.assertIn("priv->boot_seq++;", taken)
        # getter still beside the gen pair (ticket-40 surface intact)
        self.assertIn("guint goodix_boot_seq_get (FpDevice *dev);", _read(GOODIX_H))
        impl = _slice(c, "goodix_boot_seq_get (FpDevice *dev)",
                      "goodix_session_mark_clean")
        self.assertIn("return priv->boot_seq;", impl)

    def test_d_deinit_skips_bump_and_shutdown_on_clean(self):
        """Clean close skips BOTH bump and shutdown; dirty keeps both verbatim."""
        c = _read(GOODIX_C)
        deinit = _slice(c, "goodix_dev_deinit (FpDevice *dev, GError **error)",
                        "// ---- DEV SECTION END ----")
        self.assertIn("gboolean clean_close = priv->clean_close;", deinit)
        self.assertIn("if (!clean_close)", deinit)
        self.assertIn("goodix_activation_gen_bump (dev);", deinit)
        self.assertIn("goodix_shutdown_tls (dev, error);", deinit)
        # both guarded sites sit under the clean check (dirty keeps verbatim)
        first_guard = deinit.index("if (!clean_close)")
        self.assertLess(first_guard, deinit.index("goodix_activation_gen_bump (dev);"))
        self.assertLess(first_guard, deinit.index("goodix_shutdown_tls (dev, error);"))
        # teardown tail preserved on both paths
        self.assertIn("goodix_reset_state (dev);", deinit)
        self.assertIn("g_usb_device_release_interface", deinit)
        release = deinit[deinit.index("released = g_usb_device_release_interface"):]
        self.assertIn("if (!released)", release)
        self.assertIn("priv->clean_close = FALSE;", release)
        self.assertIn("goodix_activation_gen_bump (dev);", release)
        self.assertIn("goodix_shutdown_tls (dev, NULL);", release)

    def test_e_suspend_clears_and_still_shuts_down(self):
        """Suspend voids clean_close but keeps bump + shutdown (sleep safety)."""
        src = _read(GOODIX5E0A_C)
        susp = _slice(src, "goodix5e0a_suspend (FpDevice *dev)",
                      "goodix5e0a_resume (FpDevice *dev)")
        self.assertIn("goodix_session_mark_dirty (dev);", susp)
        self.assertIn("goodix_activation_gen_bump (dev);", susp)
        self.assertIn("self->tls_parked = FALSE;", susp)
        self.assertIn("self->warm_ok = FALSE;", susp)
        self.assertIn("goodix_shutdown_tls (dev, NULL);", susp)
        self.assertLess(susp.index("goodix_session_mark_dirty (dev);"),
                        susp.index("goodix_shutdown_tls (dev, NULL);"))

    def test_f_reenumeration_forces_dirty(self):
        """Bus/address/port/vid/pid mismatch forces dirty+reset regardless."""
        c = _read(GOODIX_C)
        init = _slice(c, "goodix_dev_init (FpDevice *dev, GError **error)",
                      "goodix_reset_state (FpDevice *dev)")
        for sym in ("g_usb_device_get_bus", "g_usb_device_get_address",
                    "g_usb_device_get_port_number",
                    "g_usb_device_get_vid", "g_usb_device_get_pid",
                    "usb_identity_valid", "reenumerated"):
            self.assertIn(sym, init)
        # mismatch path clears the flag before the take_reset decision
        self.assertIn("priv->clean_close = FALSE;", init)
        self.assertLess(init.index("priv->clean_close = FALSE;"),
                        init.index("take_reset = !priv->clean_close"))
        # snapshot refreshed every open for the next comparison
        for line in ("priv->last_usb_bus = bus;", "priv->last_usb_addr = addr;",
                     "priv->last_usb_port = port;",
                     "priv->usb_identity_valid = TRUE;"):
            self.assertIn(line, init)
        # claim failure also poisons the flag (next open resets)
        self.assertIn("if (!ok)", init)

    def test_g_single_clean_site_and_failure_funnels(self):
        """Exactly one TRUE site (park); every failure funnel clears."""
        src = _read(GOODIX5E0A_C)
        # single clean setter in the whole 5e0a file: the park branch
        self.assertEqual(src.count("goodix_session_mark_clean (dev);"), 1)
        deact = _slice(src, "goodix5e0a_deactivate (FpImageDevice *img_dev)",
                       "// ---- SCAN SECTION END ----")
        park = deact.index("if (goodix_tls_is_alive (dev) && self->warm_ok)")
        clean_at = deact.index("goodix_session_mark_clean (dev);")
        self.assertGreater(clean_at, park)
        self.assertLess(clean_at, deact.index("fpi_image_device_deactivate_complete (img_dev, NULL);"))
        # A live host TLS pointer after chip/scan failure is not proof of a
        # clean device session; the existing warm-success state must gate park.
        park_branch = deact[park:clean_at]
        self.assertIn("goodix_tls_is_alive (dev) && self->warm_ok", park_branch)
        # destroy branch (park dead) stays dirty — after-error AND after-success
        self.assertIn("goodix_session_mark_dirty (dev);", deact[deact.index("self->tls_parked = FALSE;"):])
        # failure funnels clear (retry-vs-final ordering: set at funnel entry
        # so a retried-then-parked session still ends clean at deactivate)
        for fn, end in (
            ("on_chip_enabled (FpDevice *dev, gpointer user_data, GError *error)",
             "goodix5e0a_warm_fresh"),
            ("on_tls_activation_complete (FpDevice *dev, gpointer user_data, GError *error)",
             "activate_complete (FpiSsm *ssm, FpDevice *dev, GError *error)"),
            ("activate_complete (FpiSsm *ssm, FpDevice *dev, GError *error)\n{",
             "dev_activate (FpImageDevice *img_dev)"),
            ("goodix5e0a_scan_complete (FpiSsm *ssm, FpDevice *dev, GError *error)",
             "goodix5e0a_scan_start (FpDevice *dev)"),
        ):
            with self.subTest(fn=fn):
                body = _slice(src, fn, end)
                self.assertIn("goodix_session_mark_dirty (dev);", body)

    def test_h_no_scope_creep(self):
        """38/39/40 pins hold; threshold, handshake, journal budget intact."""
        src = _read(GOODIX5E0A_C)
        # ticket-38 surface intact (health probe + park untouched)
        for sym in ("tls_parked", "on_parked_health_reply", "goodix_tls_is_alive",
                    "GOODIX_5E0A_TLS_PARK_TTL_US",
                    "GOODIX_5E0A_TLS_PARK_HEALTH_TIMEOUT_MS",
                    "5e0a TLS session reused (parked %.1fs, gen=%u)"):
            self.assertIn(sym, src)
        # ticket-39 surface intact
        self.assertIn("#define GOODIX_5E0A_FRAMES_PER_TOUCH 3", _read(GOODIX5E0A_H))
        self.assertEqual(src.count("fpi_image_device_image_captured ("), 1)
        # ticket-40 surface intact: predicate + 3-way branch order + warm lines
        self.assertIn("goodix5e0a_warm_fresh (dev)", src)
        act = _slice(src, "dev_activate (FpImageDevice *img_dev)",
                     "// ---- ACTIVATE SECTION END ----")
        park = act.index("self->tls_parked_gen == pre_gen")
        warm = act.index("goodix5e0a_warm_fresh (dev)")
        full = act.index("goodix5e0a_start_full_activation (dev);")
        self.assertLess(park, warm)
        self.assertLess(warm, full)
        self.assertIn("self->warm_boot_seq = goodix_boot_seq_get (dev);", src)
        # biometric operating point untouched
        self.assertIn("img_dev_class->bz3_threshold = 12;", src)
        # handshake never skipped: exactly one tls_init site
        self.assertEqual(src.count("goodix_tls_init ("), 1)
        # journal budget: 25 pre-existing 5e0a lines, zero new there
        self.assertEqual(src.count("g_message ("), 25)


if __name__ == "__main__":
    unittest.main()
