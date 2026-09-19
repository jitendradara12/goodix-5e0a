"""
Tier 1 - Feature 19: Protocol State Reset on Deactivation
Structural checks for the shared goodix_reset_state helper used by live teardown.
"""

import unittest
from tests.repo_paths import repo

class TestF19DeactivateReset(unittest.TestCase):

    def setUp(self):
        self.goodix_c_path = repo("libfprint-driver", "goodix.c")

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

if __name__ == "__main__":
    unittest.main()
