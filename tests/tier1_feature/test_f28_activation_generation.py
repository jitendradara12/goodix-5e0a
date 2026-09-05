"""
Tier 1 - Feature 28: Stale-Activation Generation Guard (Ticket 34).

Verifies without hardware (hermetic static & structural validation):
(a) goodix.h exports goodix_activation_gen_get and goodix_activation_gen_bump;
(b) FpiDeviceGoodixTlsPrivate in goodix.c contains guint activation_gen;
(c) Exactly 5 bump sites exist across activation starts and teardown/deactivate paths:
    - goodix_dev_deinit (goodix.c)
    - dev_activate (goodix511.c)
    - dev_activate (goodix5e0a.c)
    - goodix5e0a_deactivate (goodix5e0a.c)
    - dev_deactivate (goodix5xx.c)
(d) Generation capture at TLS init:
    - goodix5e0a.c activate_complete passes GUINT_TO_POINTER(goodix_activation_gen_get(dev))
    - goodix5xx.c goodixtls5xx_init_tls passes GUINT_TO_POINTER(goodix_activation_gen_get(dev))
(e) Stale completion drop logic in on_tls_activation_complete (5e0a) and tls_activation_complete (5xx):
    - checks GPOINTER_TO_UINT(user_data) != goodix_activation_gen_get(dev)
    - frees error via g_error_free(error)
    - returns early without sending commands or calling activate_complete.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.h")
GOODIX_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.c")
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")
GOODIX5XX_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5xx.c")
GOODIX511_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix511.c")


class TestF28ActivationGeneration(unittest.TestCase):

    def test_a_header_exports(self):
        """Verify goodix.h declares get and bump functions."""
        with open(GOODIX_H, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("guint goodix_activation_gen_get (FpDevice *dev);", content)
        self.assertIn("guint goodix_activation_gen_bump (FpDevice *dev);", content)

    def test_b_private_struct_field(self):
        """Verify FpiDeviceGoodixTlsPrivate struct has activation_gen field."""
        with open(GOODIX_C, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("activation_gen;", content)
        self.assertIn("goodix_activation_gen_get (FpDevice *dev)", content)
        self.assertIn("goodix_activation_gen_bump (FpDevice *dev)", content)

    def test_c_five_bump_sites(self):
        """Verify all 5 activation start and teardown sites call bump."""
        with open(GOODIX_C, "r", encoding="utf-8") as f:
            goodix_c = f.read()
        with open(GOODIX5E0A_C, "r", encoding="utf-8") as f:
            goodix5e0a_c = f.read()
        with open(GOODIX5XX_C, "r", encoding="utf-8") as f:
            goodix5xx_c = f.read()
        with open(GOODIX511_C, "r", encoding="utf-8") as f:
            goodix511_c = f.read()

        # 1. shared deinit in goodix.c
        deinit_idx = goodix_c.index("goodix_dev_deinit (FpDevice")
        self.assertIn("goodix_activation_gen_bump (dev);", goodix_c[deinit_idx:deinit_idx + 600])

        # 2. 5e0a dev_activate
        act_5e0a_idx = goodix5e0a_c.index("dev_activate (FpImageDevice *img_dev)")
        self.assertIn("goodix_activation_gen_bump (dev);", goodix5e0a_c[act_5e0a_idx:act_5e0a_idx + 600])

        # 3. 5e0a deactivate
        deact_5e0a_idx = goodix5e0a_c.index("goodix5e0a_deactivate (FpImageDevice *img_dev)")
        self.assertIn("goodix_activation_gen_bump (dev);", goodix5e0a_c[deact_5e0a_idx:deact_5e0a_idx + 600])

        # 4. 5xx dev_deactivate
        deact_5xx_idx = goodix5xx_c.index("dev_deactivate (FpImageDevice *img_dev)")
        self.assertIn("goodix_activation_gen_bump (dev);", goodix5xx_c[deact_5xx_idx:deact_5xx_idx + 600])

        # 5. 511 dev_activate
        act_511_idx = goodix511_c.index("dev_activate (FpImageDevice *img_dev)")
        self.assertIn("goodix_activation_gen_bump (dev);", goodix511_c[act_511_idx:act_511_idx + 600])

    def test_d_generation_capture_at_tls_init(self):
        """Verify TLS init captures generation into user_data pointer."""
        with open(GOODIX5E0A_C, "r", encoding="utf-8") as f:
            goodix5e0a_c = f.read()
        with open(GOODIX5XX_C, "r", encoding="utf-8") as f:
            goodix5xx_c = f.read()

        self.assertIn("GUINT_TO_POINTER (goodix_activation_gen_get (dev))", goodix5e0a_c)
        self.assertIn("GUINT_TO_POINTER (goodix_activation_gen_get (dev))", goodix5xx_c)

    def test_e_stale_completion_drop_logic(self):
        """Verify on_tls_activation_complete (5e0a) and tls_activation_complete (5xx) drop cleanly."""
        with open(GOODIX5E0A_C, "r", encoding="utf-8") as f:
            src_5e0a = f.read()
        with open(GOODIX5XX_C, "r", encoding="utf-8") as f:
            src_5xx = f.read()

        # 5e0a check
        cb_start = src_5e0a.index("on_tls_activation_complete (FpDevice *dev, gpointer user_data, GError *error)")
        cb_body = src_5e0a[cb_start:cb_start + 1200]
        self.assertIn("GPOINTER_TO_UINT (user_data) != goodix_activation_gen_get (dev)", cb_body)
        self.assertIn("dropping stale TLS activation completion", cb_body)
        self.assertIn("g_error_free (error);", cb_body)
        self.assertLess(cb_body.index("return;"), cb_body.index("goodix_send_enable_chip"))

        # 5xx check
        cb_5xx_start = src_5xx.index("tls_activation_complete (FpDevice *dev, gpointer user_data")
        cb_5xx_body = src_5xx[cb_5xx_start:cb_5xx_start + 1200]
        self.assertIn("GPOINTER_TO_UINT (user_data) != goodix_activation_gen_get (dev)", cb_5xx_body)
        self.assertIn("dropping stale TLS activation completion", cb_5xx_body)
        self.assertIn("g_error_free (error);", cb_5xx_body)


if __name__ == "__main__":
    unittest.main()
