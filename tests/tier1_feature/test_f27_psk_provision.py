"""
Tier 1 - Feature 27: upstream-clean activation without PSK reconciliation (ticket 26 follow-up).

Verifies WITHOUT hardware (hermetic: no USB, no openssl) that the ticket-26
READ_PSK / PROVISION_PSK instrumentation is gone and activation talks TLS
directly with the static host key:

(a) header goodix_5e0a_psk bytes equal the mock CANONICAL_PSK fixture
    (TLS still needs the host key);
(b) activation orders CHECK_FW_VER -> UPLOAD_CONFIG with no PSK states,
    callbacks, or slice dispatch in between;
(c) no factory-default key table ships in the tree;
(d) the 5e0a-only sliced 0xe4 helper is gone while the shared 511
    read/write transport helpers remain.

Context: ticket 26 closed as could-not-reproduce (single cold-boot
bad-record-MAC event, true-poweroff boot clean); Exp 26.4 falsified the
bb020001 slot as the TLS slot and Exp 26.5 proved 0xe0 rejected in both
encodings. The strip removes two per-activation USB round-trips plus
journal noise and the factory secret (docs/UPSTREAM.md section 6).

Not covered here: live activation sequencing (needs hardware/fprintd).
"""

import os
import re
import unittest

from tests.test_utils import CANONICAL_PSK

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEADER_PATH = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.h")
GOODIX_C_PATH = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.c")
GOODIX_H_PATH = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.h")
GOODIX_5E0A_C_PATH = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")


def parse_c_array(header_content: str, array_name: str) -> bytes:
    """Extracts a byte array from a C header file."""
    pattern = rf"(?:static\s+)?const\s+guint8\s+{array_name}\s*\[\s*\d*\s*\]\s*=\s*\{{([^}}]+)\}};"
    match = re.search(pattern, header_content, re.DOTALL)
    if not match:
        raise ValueError(f"Array '{array_name}' not found in header")
    hex_str = match.group(1)
    # Extract all 0x.. hex literals
    hex_bytes = re.findall(r"0x([0-9a-fA-F]{2})", hex_str)
    return bytes(int(b, 16) for b in hex_bytes)


class TestF27UpstreamCleanNoPskReconciliation(unittest.TestCase):

    def test_a_header_psk_matches_mock_fixture(self):
        """Header goodix_5e0a_psk must be 32 bytes equal to CANONICAL_PSK."""
        with open(HEADER_PATH, "r", encoding="utf-8") as f:
            header_content = f.read()
        psk = parse_c_array(header_content, "goodix_5e0a_psk")
        self.assertEqual(len(psk), 32)
        self.assertEqual(psk, CANONICAL_PSK)

    def test_b_no_psk_reconciliation_states_or_callbacks(self):
        """Activation must not contain READ_PSK / PROVISION_PSK states or handlers."""
        with open(GOODIX_5E0A_C_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        for absent in (
            "ACTIVATE_READ_PSK",
            "ACTIVATE_PROVISION_PSK",
            "on_psk_read",
            "on_psk_write",
            "goodix_send_preset_psk_read_slice",
            "goodix_send_preset_psk_write",
            "goodix_5e0a_psk_default",
        ):
            self.assertNotIn(absent, src, f"{absent} must be stripped from goodix5e0a.c")

    def test_c_activation_orders_fw_ver_then_upload_config(self):
        """Enum and dispatch must place UPLOAD_CONFIG directly after CHECK_FW_VER."""
        with open(GOODIX_5E0A_C_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        enum_start = src.index("enum activate_states")
        enum_end = src.index("};", enum_start)
        enum_body = src[enum_start:enum_end]
        enumerators = re.findall(r"ACTIVATE_\w+", enum_body)
        self.assertIn("ACTIVATE_CHECK_FW_VER", enumerators)
        self.assertIn("ACTIVATE_UPLOAD_CONFIG", enumerators)
        self.assertEqual(
            enumerators.index("ACTIVATE_UPLOAD_CONFIG"),
            enumerators.index("ACTIVATE_CHECK_FW_VER") + 1,
        )
        run = src[src.index("activate_run_state"):]
        j_fw = run.index("goodix_send_query_firmware_version")
        j_up = run.index("goodix_send_upload_config_mcu")
        self.assertLess(j_fw, j_up)
        # The next activation case after the FW_VER dispatch must be UPLOAD_CONFIG.
        next_case = re.search(r"case (ACTIVATE_\w+)", run[j_fw:])
        self.assertIsNotNone(next_case)
        self.assertEqual(next_case.group(1), "ACTIVATE_UPLOAD_CONFIG")

    def test_d_no_factory_key_in_tree(self):
        """Factory-default key table and bytes must not ship anywhere in the driver."""
        for path in (HEADER_PATH, GOODIX_5E0A_C_PATH, GOODIX_C_PATH):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("goodix_5e0a_psk_default", content, path)
            # Factory bytes 68776fdc...ff1c9 must not appear in any driver file.
            self.assertNotIn("0x68, 0x77, 0x6f, 0xdc", content, path)

    def test_e_shared_psk_helpers_preserved_for_511(self):
        """Generic 0xe4/0xe0 transport stays for 511; 5e0a-only slice helper is gone."""
        with open(GOODIX_C_PATH, "r", encoding="utf-8") as f:
            gsrc = f.read()
        with open(GOODIX_H_PATH, "r", encoding="utf-8") as f:
            ghdr = f.read()
        self.assertIn("goodix_send_preset_psk_read (FpDevice", gsrc)
        self.assertIn("goodix_send_preset_psk_write (FpDevice", gsrc)
        self.assertIn("goodix_send_preset_psk_read (FpDevice", ghdr)
        self.assertIn("goodix_send_preset_psk_write (FpDevice", ghdr)
        self.assertNotIn("goodix_send_preset_psk_read_slice", gsrc)
        self.assertNotIn("goodix_send_preset_psk_read_slice", ghdr)


if __name__ == "__main__":
    unittest.main()
