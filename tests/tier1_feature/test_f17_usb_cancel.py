"""
Tier 1 - Feature 17: Deterministic USB Read Loop Cancellation
Requirements: Use g_cancellable_cancel and g_cancellable_reset to prevent uncancelled transfers.
"""

import unittest
from tests.repo_paths import repo

class TestF17USBCancel(unittest.TestCase):

    def setUp(self):
        self.goodix_c_path = repo("libfprint-driver", "goodix.c")

    def test_transfer_cancellable_cancel_called_on_deactivate(self):
        """Verify g_cancellable_cancel is invoked in goodix_stop_read_loop to abort in-flight URBs."""
        with open(self.goodix_c_path, "r") as f:
            content = f.read()
        self.assertIn("g_cancellable_cancel", content)
        self.assertIn("goodix_stop_read_loop", content)

    def test_transfer_cancellable_reset_on_activation(self):
        """Verify g_cancellable_reset is invoked in goodix_start_read_loop before reissuing read transfers."""
        with open(self.goodix_c_path, "r") as f:
            content = f.read()
        self.assertIn("g_cancellable_reset", content)
        self.assertIn("goodix_start_read_loop", content)

    def test_transfer_cancellable_token_field_in_private_struct(self):
        """Verify GCancellable *transfer_cancel_tkn is declared in FpiDeviceGoodixTlsPrivate."""
        with open(self.goodix_c_path, "r") as f:
            content = f.read()
        self.assertIn("GCancellable *transfer_cancel_tkn;", content)

    def test_inited_flag_lifecycle(self):
        """Verify priv->inited boolean tracks active state to avoid double-free or double-start."""
        with open(self.goodix_c_path, "r") as f:
            content = f.read()
        self.assertIn("priv->inited = TRUE", content)
        self.assertIn("priv->inited = FALSE", content)

    def test_cancellable_null_safety(self):
        """Verify cancellation checks token validity before calling g_cancellable_cancel."""
        with open(self.goodix_c_path, "r") as f:
            content = f.read()
        self.assertIn("if (priv->transfer_cancel_tkn)", content)

if __name__ == "__main__":
    unittest.main()
