"""
Tier 1 - Feature 86: Eliminate 2000ms CMD 0xd4 TLS Established Timeout (Ticket 86).

Verifies without hardware (hermetic static & structural validation):
(a) goodix_send_tls_successfully_established sends GOODIX_CMD_TLS_SUCCESSFULLY_ESTABLISHED (0xd4)
    with reply=FALSE and timeout=GOODIX_TIMEOUT, allowing goodix_receive_ack to complete the
    command immediately upon MCU ACK (~16ms) without waiting for a non-existent second reply packet.
(b) on_tls_successfully_established does not swallow transfer errors; it propagates error
    to priv->tls_ready_callback so activation failure or warm fallback handles it cleanly.
(c) The hardcoded 2000ms timeout is eliminated from goodix_send_tls_successfully_established.
"""

import unittest
from tests.repo_paths import repo

GOODIX_C = repo("libfprint-driver", "goodix.c")
GOODIX_H = repo("libfprint-driver", "goodix.h")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestF86TlsEstablishedAck(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.c_src = _read(GOODIX_C)
        cls.h_src = _read(GOODIX_H)
        send_def = "goodix_send_tls_successfully_established (FpDevice          *dev,"
        on_def = "on_tls_successfully_established (FpDevice *dev, gpointer user_data,"
        cls.send_body = cls.c_src[cls.c_src.index(send_def):cls.c_src.index("goodix_send_read_otp (FpDevice *dev")]
        cls.on_body = cls.c_src[cls.c_src.index(on_def):cls.c_src.index("tls_handshake_done (FpiSsm *ssm, FpDevice *dev")]

    def test_a_reply_is_false_in_send_protocol(self):
        """0xd4 must specify reply=FALSE so that MCU ACK completes the command immediately."""
        self.assertIn("Ticket 86", self.send_body)
        self.assertIn("GOODIX_CMD_TLS_SUCCESSFULLY_ESTABLISHED", self.send_body)
        self.assertIn("GOODIX_TIMEOUT, FALSE, goodix_receive_none, cb_info", self.send_body)
        self.assertIn("GOODIX_TIMEOUT, FALSE, NULL, NULL", self.send_body)

    def test_b_no_hardcoded_2000ms_timeout(self):
        """0xd4 must not contain hardcoded 2000ms timeout in goodix_send_tls_successfully_established."""
        self.assertNotIn("2000, TRUE", self.send_body)
        self.assertNotIn("2000, FALSE", self.send_body)

    def test_c_on_tls_successfully_established_propagates_error(self):
        """on_tls_successfully_established must propagate genuine errors rather than ignoring them."""
        self.assertIn("Ticket 86", self.on_body)
        self.assertIn("if (error)", self.on_body)
        self.assertIn("fp_err (\"failed to send TLS established: %s\", error->message);", self.on_body)
        self.assertIn("((GoodixNoneCallback) priv->tls_ready_callback->callback)(\n        dev, priv->tls_ready_callback->user_data, error);", self.on_body)


if __name__ == "__main__":
    unittest.main()
