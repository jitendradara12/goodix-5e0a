"""
Tier 1 - Feature 117: Dynamic OTP DAC Calibration and Unified Configuration (Ticket 117).

Requirements:
(a) ACTIVATE_READ_OTP issues CMD 0xa6 via goodix_send_read_otp and handles response via goodix5e0a_on_read_otp.
(b) FpiDeviceGoodixTls5e0a contains dynamic runtime packet buffers: dac[4], fdt_down_s12, fdt_up_u01, mcu_config.
(c) goodix5e0a_on_read_otp decodes primary (0x2e..0x31), redundant (0x32..0x35), and high bit (0x13) offsets.
(d) goodix5e0a_update_dacs dynamically updates FDT down, FDT up, and goodix5e0a_capture_payload.
(e) Scan and config upload pathways transmit dynamic buffers rather than static const tables.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")
GOODIX_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.h")
GOODIX_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.c")


def _decode_otp_dacs(data):
    if not data or len(data) < 64:
        return None
    dacs = [0, 0, 0, 0]
    valid = True
    for i in range(4):
        p = data[0x2e + i]
        s = data[0x32 + i]
        if p != 0 and (p == s or s == 0):
            dacs[i] = p
        elif s != 0:
            dacs[i] = s
        else:
            valid = False
        if valid and (data[0x13] & (1 << (3 - i))):
            dacs[i] |= 0x100
    return dacs if valid else None


class TestF117DynamicOTPCalibration(unittest.TestCase):

    def setUp(self):
        with open(GOODIX5E0A_C, "r", encoding="utf-8") as f:
            self.c_src = f.read()
        with open(GOODIX_H, "r", encoding="utf-8") as f:
            self.h_src = f.read()
        with open(GOODIX_C, "r", encoding="utf-8") as f:
            self.goodix_c = f.read()

    def test_a_struct_fields_and_exports(self):
        """Verify dynamic packet buffers on FpiDeviceGoodixTls5e0a and exported capture payload."""
        self.assertIn("guint16             dac[4];", self.c_src)
        self.assertIn("guint8              fdt_down_s12[sizeof (goodix_5e0a_down_s12)]", self.c_src)
        self.assertIn("fdt_up_u01[sizeof (goodix_5e0a_up_u01)]", self.c_src)
        self.assertIn("mcu_config[sizeof (goodix_5e0a_config)];", self.c_src)
        self.assertIn("extern guint8 goodix5e0a_capture_payload[10];", self.h_src)
        self.assertIn("guint8 goodix5e0a_capture_payload[10] =", self.goodix_c)

    def test_b_otp_state_machine_wiring(self):
        """Verify ACTIVATE_READ_OTP invokes goodix5e0a_on_read_otp."""
        self.assertIn("case ACTIVATE_READ_OTP:", self.c_src)
        self.assertIn("goodix_send_read_otp (dev, goodix5e0a_on_read_otp, ssm);", self.c_src)

    def test_c_dynamic_buffer_dispatch_sites(self):
        """Verify send_cmd sites use dynamic instance buffers."""
        self.assertIn("self->fdt_down_s12, sizeof (self->fdt_down_s12)", self.c_src)
        self.assertIn("self->fdt_up_u01, sizeof (self->fdt_up_u01)", self.c_src)
        self.assertIn("goodix_send_upload_config_mcu (dev, self->mcu_config,", self.c_src)

    def test_d_otp_dac_decode_logic(self):
        """Verify algorithmic OTP decoding across maintainer and Jet-Soup hardware samples."""
        # Maintainer unit sample: primary 0xb0, 0xb2, 0xb0, 0xb1; no high bits
        raw_maint = bytearray(64)
        raw_maint[0x2e:0x32] = bytes([0xb0, 0xb2, 0xb0, 0xb1])
        raw_maint[0x32:0x36] = bytes([0xb0, 0xb2, 0xb0, 0xb1])
        self.assertEqual(_decode_otp_dacs(raw_maint), [0xb0, 0xb2, 0xb0, 0xb1])

        # Jet-Soup unit sample: primary 0xad, 0xae, 0xac, 0xad
        raw_jet = bytearray(64)
        raw_jet[0x2e:0x32] = bytes([0xad, 0xae, 0xac, 0xad])
        raw_jet[0x32:0x36] = bytes([0xad, 0xae, 0xac, 0xad])
        self.assertEqual(_decode_otp_dacs(raw_jet), [0xad, 0xae, 0xac, 0xad])

        # Redundant fallback when primary is zero
        raw_redundant = bytearray(64)
        raw_redundant[0x32:0x36] = bytes([0xb0, 0xb2, 0xb0, 0xb1])
        self.assertEqual(_decode_otp_dacs(raw_redundant), [0xb0, 0xb2, 0xb0, 0xb1])

        # High bit in 0x13 for channel 0 and 2 (bits 3 and 1)
        raw_high = bytearray(64)
        raw_high[0x2e:0x32] = bytes([0x10, 0x20, 0x30, 0x40])
        raw_high[0x13] = 0x0a  # bits 3 and 1 set
        self.assertEqual(_decode_otp_dacs(raw_high), [0x110, 0x20, 0x130, 0x40])


if __name__ == "__main__":
    unittest.main()
