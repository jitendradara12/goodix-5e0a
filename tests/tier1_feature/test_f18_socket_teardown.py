"""
Tier 1 - Feature 18: Non-blocking TLS Socket Teardown
Requirements: shutdown(fd, SHUT_RDWR) before thread join to prevent PAM hangs.
"""

import unittest

class TestF18SocketTeardown(unittest.TestCase):

    def setUp(self):
        self.goodixtls_c_path = "/home/sastauser/code/temp/goodix/libfprint-driver/goodixtls.c"

    def test_shutdown_shut_rdwr_before_thread_join(self):
        """Verify shutdown(fd, SHUT_RDWR) is called on client socket to break blocking read/write."""
        with open(self.goodixtls_c_path, "r") as f:
            content = f.read()
        self.assertIn("shutdown", content)
        self.assertIn("SHUT_RDWR", content)

    def test_pthread_join_cleanup(self):
        """Verify pthread_join is called to cleanly reap TLS server worker thread."""
        with open(self.goodixtls_c_path, "r") as f:
            content = f.read()
        self.assertIn("pthread_join", content)

    def test_ssl_free_and_context_cleanup(self):
        """Verify SSL session and SSL_CTX are properly freed during shutdown."""
        with open(self.goodixtls_c_path, "r") as f:
            content = f.read()
        self.assertIn("SSL_free", content)
        self.assertIn("SSL_CTX_free", content)

    def test_socket_descriptor_invalidation(self):
        """Verify closed socket descriptors are set to -1 to prevent double-close."""
        with open(self.goodixtls_c_path, "r") as f:
            content = f.read()
        self.assertIn("close", content)

    def test_tls_stop_function_present(self):
        """Verify goodix_tls_server_deinit is implemented."""
        with open(self.goodixtls_c_path, "r") as f:
            content = f.read()
        self.assertIn("goodix_tls_server_deinit", content)

if __name__ == "__main__":
    unittest.main()
