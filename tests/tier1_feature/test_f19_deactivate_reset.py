"""
Tier 1 - Feature 19: Protocol State Reset on Deactivation
Requirements: Clear priv->cmd, priv->ack, priv->reply, timers, and data buffers in dev_deactivate.
"""

import unittest

class TestF19DeactivateReset(unittest.TestCase):

    def setUp(self):
        self.goodix_c_path = "/home/sastauser/code/temp/goodix/libfprint-driver/goodix.c"
        self.goodix5xx_c_path = "/home/sastauser/code/temp/goodix/libfprint-driver/goodix5xx.c"

    def test_goodix_reset_state_clears_cmd(self):
        """Verify goodix_reset_state resets priv->cmd to 0."""
        with open(self.goodix_c_path, "r") as f:
            content = f.read()
        self.assertIn("priv->cmd = 0;", content)

    def test_goodix_reset_state_clears_ack_and_reply_flags(self):
        """Verify goodix_reset_state resets priv->ack = FALSE and priv->reply = FALSE."""
        with open(self.goodix_c_path, "r") as f:
            content = f.read()
        self.assertIn("priv->ack = FALSE;", content)
        self.assertIn("priv->reply = FALSE;", content)

    def test_goodix_reset_state_frees_data_buffer(self):
        """Verify goodix_reset_state frees allocated data buffers to prevent memory leaks."""
        with open(self.goodix_c_path, "r") as f:
            content = f.read()
        self.assertIn("g_clear_pointer (&priv->data, g_free);", content)

    def test_dev_deactivate_calls_goodix_reset_state(self):
        """Verify dev_deactivate in goodix5xx.c calls goodix_reset_state(dev)."""
        with open(self.goodix5xx_c_path, "r") as f:
            content = f.read()
        self.assertIn("goodix_reset_state (dev);", content)

    def test_dev_deactivate_cleans_calibration_img(self):
        """Verify dev_deactivate frees calibration image buffer."""
        with open(self.goodix5xx_c_path, "r") as f:
            content = f.read()
        self.assertIn("goodixtls5xx_cleanup", content)
        self.assertIn("priv->calibration_img = NULL;", content)

if __name__ == "__main__":
    unittest.main()
