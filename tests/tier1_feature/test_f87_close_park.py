"""Close must reach the existing idle park path before transport teardown.

Structural regression guard only; deployed-driver reuse needs journal evidence.
"""
import unittest
from pathlib import Path
from tests.repo_paths import repo


class TestClosePark(unittest.TestCase):
    def test_idle_close_parks_before_deinit(self):
        src = Path(repo("libfprint-driver", "goodix5e0a.c")).read_text()
        close = src.split("dev_close (FpDevice *dev)", 1)[1].split(
            "dev_enroll (FpDevice *dev)", 1)[0]
        gate = "if (self->scan_ssm == NULL && self->warm_ok && goodix_tls_is_alive (dev))"
        call = "goodix5e0a_deactivate ((FpImageDevice *) dev);"
        self.assertIn(gate, close)
        self.assertLess(close.index(gate), close.index(call))
        self.assertLess(close.index(call), close.index("fpi_ssm_free (self->scan_ssm);"))
        self.assertLess(close.index(call), close.index("goodix_dev_deinit (dev, &error)"))
        # Closing must not invent a second site that marks a session clean.
        self.assertNotIn("goodix_session_mark_clean", close)


if __name__ == "__main__":
    unittest.main()
