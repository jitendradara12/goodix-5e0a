"""Checkout-local Meson integration checks; compilation is covered by the native lane."""

import unittest
from tests.repo_paths import REPO_ROOT


class TestF20MesonWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch = (REPO_ROOT / "goodix-5e0a-integration.patch").read_text()
        cls.additions = "\n".join(line[1:] for line in patch.splitlines()
                                  if line.startswith("+") and not line.startswith("+++"))

    def test_driver_registered_with_tls_helper(self):
        self.assertIn("'goodixtls5e0a',", self.additions)
        self.assertRegex(self.additions, r"'goodixtls5e0a'\s*:\s*\[\s*'goodixtls'\s*\]")

    def test_driver_and_engine_sources_registered(self):
        self.assertRegex(
            self.additions,
            r"'goodixtls5e0a'\s*:\s*\[\s*'drivers/goodixtls/goodix5e0a.c',"
            r"\s*'drivers/goodixtls/goodix_milan.c'\s*\]",
        )
        for name in ("goodix5e0a.c", "goodix5e0a.h", "goodix_milan.c", "goodix_milan.h"):
            self.assertTrue((REPO_ROOT / "libfprint-driver" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
