"""
Tier 2 - Boundary 24: Non-blocking Socket Bounds
Tests socket shutdown safety when descriptors are -1 or already closed.
"""

import unittest

class TestB24NonblockingBounds(unittest.TestCase):

    def setUp(self):
        self.goodixtls_c = "/home/sastauser/code/temp/goodix/libfprint-driver/goodixtls.c"

    def test_shutdown_checks_client_fd_validity(self):
        """Verify goodix_tls_server_deinit checks if (self->client_fd >= 0) before shutdown."""
        with open(self.goodixtls_c, "r") as f:
            content = f.read()
        self.assertIn("if (self->client_fd >= 0)", content)
        self.assertIn("shutdown (self->client_fd, SHUT_RDWR);", content)

    def test_shutdown_checks_sock_fd_validity(self):
        """Verify goodix_tls_server_deinit checks if (self->sock_fd >= 0) before shutdown."""
        with open(self.goodixtls_c, "r") as f:
            content = f.read()
        self.assertIn("if (self->sock_fd >= 0)", content)
        self.assertIn("shutdown (self->sock_fd, SHUT_RDWR);", content)

    def test_double_close_protection_fd_reset_to_negative_one(self):
        """Verify file descriptors are reset to -1 after close."""
        with open(self.goodixtls_c, "r") as f:
            content = f.read()
        self.assertIn("self->client_fd = -1;", content)
        self.assertIn("self->sock_fd = -1;", content)

    def test_null_server_instance_safety(self):
        """Verify deinit returns TRUE if passed NULL self pointer."""
        with open(self.goodixtls_c, "r") as f:
            content = f.read()
        self.assertIn("if (!self)\n    return TRUE;", content)

    def test_thread_join_checks_thread_non_zero(self):
        """Verify pthread_join is only called when serve_thread != 0."""
        with open(self.goodixtls_c, "r") as f:
            content = f.read()
        self.assertIn("if (self->serve_thread)", content)

if __name__ == "__main__":
    unittest.main()
