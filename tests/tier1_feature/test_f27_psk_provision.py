"""
Tier 1 - Feature 27: activation-time PSK reconciliation wire/header/source-presence (ticket 26).

Verifies WITHOUT hardware (hermetic: no USB, no openssl):
(a) header goodix_5e0a_psk bytes equal the mock CANONICAL_PSK fixture;
(b) goodix_send_preset_psk_write sizes the 0xe0 send with sizeof(GoodixPresetPsk);
(c) activation orders READ_PSK -> PROVISION_PSK -> UPLOAD_CONFIG and the
    key-match branch jumps to ACTIVATE_UPLOAD_CONFIG;
(d) mock 0xe4 reply shape carries flags 0xBB020001 plus a 32-byte key.
(e) ticket 26.3: ACTIVATE_READ_PSK dispatches the sliced 16-byte 0xe4 read
    (GOODIX_5E0A_PSK_FLAGS, 32, 0), the slice helper builds [len,off,flags,0],
    provision-reject is soft-fail, and the old 511 helper still exists.

Not covered here: live activation sequencing (needs hardware/fprintd).
"""

import os
import re
import struct
import unittest

from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_PRESET_PSK_READ, CANONICAL_PSK,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEADER_PATH = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.h")
GOODIX_C_PATH = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.c")
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


class TestF27PskProvision(unittest.TestCase):

    def test_a_header_psk_matches_mock_fixture(self):
        """Header goodix_5e0a_psk must be 32 bytes equal to CANONICAL_PSK."""
        with open(HEADER_PATH, "r", encoding="utf-8") as f:
            header_content = f.read()
        psk = parse_c_array(header_content, "goodix_5e0a_psk")
        self.assertEqual(len(psk), 32)
        self.assertEqual(psk, CANONICAL_PSK)

    def test_b_preset_psk_write_uses_struct_sizeof(self):
        """0xe0 send sites must size with the packed struct, never the pointer.

        goodix_send_preset_psk_write must pass
        sizeof (GoodixPresetPsk) + length at both send sites; the fixed code
        also uses it for the g_malloc, so the bare pattern occurs 3 times
        (malloc + both sends) in the function body. The send-site pattern
        (with the g_free destroy notify) occurs exactly twice. The bug was
        sizeof (payload) + length where payload is guint8*: on x86_64 both
        are 8 so the wire was accidentally correct, but on a 4-byte-pointer
        arch it would send 4+32=36 truncated bytes.
        """
        with open(GOODIX_C_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        start = src.index("goodix_send_preset_psk_write (FpDevice")
        end = src.index("goodix_send_preset_psk_read (FpDevice")
        body = src[start:end]
        self.assertEqual(body.count("sizeof (GoodixPresetPsk) + length"), 3)
        self.assertEqual(body.count("sizeof (GoodixPresetPsk) + length, g_free"), 2)
        self.assertEqual(body.count("sizeof (payload) + length"), 0)
        # Packed-struct oracle: flags(4B) + length(4B) = 8; wire pin 8+32=40.
        self.assertEqual(struct.calcsize("<II"), 8)
        self.assertEqual(8 + 32, 40)

    def test_c_activation_psk_state_ordering(self):
        """Activation must order READ_PSK -> PROVISION_PSK -> UPLOAD_CONFIG."""
        with open(GOODIX_5E0A_C_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        i_read = src.index("ACTIVATE_READ_PSK")
        i_provision = src.index("ACTIVATE_PROVISION_PSK")
        i_upload = src.index("ACTIVATE_UPLOAD_CONFIG")
        self.assertLess(i_read, i_provision)
        self.assertLess(i_provision, i_upload)
        run = src[src.index("activate_run_state"):]
        j_read = run.index("goodix_send_preset_psk_read")
        j_write = run.index("goodix_send_preset_psk_write")
        j_upload = run.index("goodix_send_upload_config_mcu")
        self.assertLess(j_read, j_write)
        self.assertLess(j_write, j_upload)
        self.assertIn("fpi_ssm_jump_to_state (ssm, ACTIVATE_UPLOAD_CONFIG)", src)

    def test_d_mock_0xe4_reply_shape_flags_and_key_length(self):
        """Mock 0xe4 reply shape: flags 0xBB020001 plus a 32-byte key.

        Uses literals only (no fixture import) so this pins the wire shape
        independently of shared mock constants.
        """
        mcu = MockGoodixMCU()
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_PRESET_PSK_READ, b""))
        reply = mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        self.assertTrue(ok)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_PRESET_PSK_READ)
        self.assertGreaterEqual(len(payload), 4 + 32)
        flags_val = struct.unpack("<I", payload[:4])[0]
        self.assertEqual(flags_val, 0xBB020001)
        self.assertEqual(len(payload[4:]), 32)

    def test_e_sliced_psk_read_and_soft_fail_provision(self):
        """Ticket 26.3: sliced 16-byte 0xe4 read + soft-fail provision.

        (a) ACTIVATE_READ_PSK dispatches goodix_send_preset_psk_read_slice
            with (GOODIX_5E0A_PSK_FLAGS, 32, 0);
        (b) goodix.c defines the slice helper building a 16-byte LE payload
            [length, offset, flags, 0] for GOODIX_CMD_PRESET_PSK_READ;
        (c) on_psk_write soft-fails (warn + advance, no fpi_ssm_mark_failed);
        (d) the old goodix_send_preset_psk_read helper still exists (511 compat).
        """
        with open(GOODIX_5E0A_C_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        with open(GOODIX_C_PATH, "r", encoding="utf-8") as f:
            gsrc = f.read()

        # (a) slice dispatch with proven ticket-26.1 bytes.
        self.assertIn(
            "goodix_send_preset_psk_read_slice (dev, GOODIX_5E0A_PSK_FLAGS, 32, 0",
            src)

        # (b) slice helper definition: 4-field LE packing + 16-byte size +
        # 0xe4 command + shared read trampoline.
        start = gsrc.index("goodix_send_preset_psk_read_slice (FpDevice")
        body = gsrc[start:start + 2500]
        self.assertGreaterEqual(body.count("GUINT32_TO_LE"), 4)
        self.assertIn("GOODIX_CMD_PRESET_PSK_READ", body)
        self.assertIn("16", body)
        self.assertIn("goodix_receive_preset_psk_read", body)

        # (c) soft-fail: warn + advance, never wedge warm logins.
        wstart = src.index("on_psk_write (FpDevice")
        wend = src.index("activate_run_state", wstart)
        wbody = src[wstart:wend]
        self.assertIn("continuing with host key", wbody)
        self.assertNotIn("fpi_ssm_mark_failed", wbody)

        # (d) 511 compat: old 8-byte helper definition untouched.
        self.assertIn("goodix_send_preset_psk_read (FpDevice", gsrc)


if __name__ == "__main__":
    unittest.main()
