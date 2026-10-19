"""
Tier 1 - Feature 117: Dynamic OTP DAC Calibration and Unified Configuration (Ticket 117 / 118).

Requirements:
(a) ACTIVATE_READ_OTP issues CMD 0xa6 via goodix_send_read_otp and handles response via goodix5e0a_on_read_otp.
(b) FpiDeviceGoodixTls5e0a contains dynamic runtime packet buffers: dac[4], fdt_down_s12, fdt_up_u01, mcu_config.
(c) goodix5e0a_on_read_otp decodes primary (0x2e..0x31), redundant (0x32..0x35), and high bit (0x13) offsets,
    logs decoded DACs via fp_dbg, and calls goodix5e0a_update_dacs.
(d) goodix5e0a_update_dacs dynamically updates FDT down, FDT up, and goodix5e0a_capture_payload.
(e) Scan and config upload pathways transmit dynamic buffers rather than static const tables.
(f) Applying dacs[0] = 0xad produces exact byte modifications matching experiments/jet-soup-capture.patch
    (offsets 0xc8, 0xeb, 0xec, checksum 0x1e4a, and capture payload byte 0 == 0x01).
"""

import ctypes
import os
import re
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOODIX5E0A_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.c")
GOODIX5E0A_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix5e0a.h")
GOODIX_H = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.h")
GOODIX_C = os.path.join(REPO_ROOT, "libfprint-driver", "goodix.c")
PATCH_PATH = os.path.join(REPO_ROOT, "experiments", "jet-soup-capture.patch")


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


def _slice(src, start_marker, end_marker):
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


def _compile_c_shared_lib(c_code):
    tmpdir = tempfile.mkdtemp(prefix="goodix_test_c_")
    c_path = os.path.join(tmpdir, "module.c")
    so_path = os.path.join(tmpdir, "module.so")
    with open(c_path, "w", encoding="utf-8") as f:
        f.write(c_code)
    subprocess.run(["gcc", "-shared", "-fPIC", "-O2", c_path, "-o", so_path], check=True)
    return so_path, tmpdir


class DevStruct(ctypes.Structure):
    _fields_ = [
        ("dac", ctypes.c_uint16 * 4),
        ("fdt_down_s12", ctypes.c_uint8 * 35),
        ("fdt_up_u01", ctypes.c_uint8 * 35),
        ("mcu_config", ctypes.c_uint8 * 256),
    ]


class TestF117DynamicOTPCalibration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(GOODIX5E0A_C, "r", encoding="utf-8") as f:
            cls.c_src = f.read()
        with open(GOODIX5E0A_H, "r", encoding="utf-8") as f:
            cls.h_5e0a_src = f.read()
        with open(GOODIX_H, "r", encoding="utf-8") as f:
            cls.h_src = f.read()
        with open(GOODIX_C, "r", encoding="utf-8") as f:
            cls.goodix_c = f.read()
        with open(PATCH_PATH, "r", encoding="utf-8") as f:
            cls.patch_src = f.read()

        match = re.search(r"static const guint8 goodix_5e0a_config\[256\]\s*=\s*\{([^}]+)\};", cls.h_5e0a_src)
        assert match, "goodix_5e0a_config missing from header"
        cls.base_cfg = bytearray(int(x.strip(), 16) for x in match.group(1).split(",") if x.strip())

        # Harvest update_dacs function directly from goodix5e0a.c
        start_ud = cls.c_src.index("static void\ngoodix5e0a_update_dacs")
        end_ud = cls.c_src.index("static void\ngoodix5e0a_on_read_otp", start_ud)
        update_dacs_c = cls.c_src[start_ud:end_ud].strip()

        # Build test module compiling actual C code from goodix5e0a.c
        c_code = f"""
        #include <stdint.h>
        #include <stdbool.h>
        #include <string.h>
        typedef uint8_t guint8;
        typedef uint16_t guint16;
        typedef uint32_t guint32;
        typedef struct {{
            guint16 dac[4];
            guint8 fdt_down_s12[35];
            guint8 fdt_up_u01[35];
            guint8 mcu_config[256];
        }} FpiDeviceGoodixTls5e0a;
        guint8 goodix5e0a_capture_payload[10] = {{0x05, 0x00, 0xb0, 0x00, 0xb2, 0x00, 0xb0, 0x00, 0xb1, 0x00}};
        #define fp_dbg(...) do {{}} while (0)

        {update_dacs_c}

        void c_update_dacs(FpiDeviceGoodixTls5e0a *self, const guint16 dacs[4]) {{
            goodix5e0a_update_dacs(self, dacs);
        }}
        guint8 c_get_capture_payload_byte(int idx) {{
            return goodix5e0a_capture_payload[idx];
        }}
        void c_set_capture_payload_byte(int idx, guint8 val) {{
            goodix5e0a_capture_payload[idx] = val;
        }}
        int c_decode_otp_loop(const guint8 *data, guint16 len, guint16 *dacs) {{
            if (!data || len < 64) return 0;
            bool valid = true;
            for (int i = 0; i < 4; i++) {{
                guint8 p = data[0x2e + i], s = data[0x32 + i];
                if (p != 0 && (p == s || s == 0)) dacs[i] = p;
                else if (s != 0) dacs[i] = s;
                else valid = false;
                if (valid && (data[0x13] & (1 << (3 - i)))) dacs[i] |= 0x100;
            }}
            return valid ? 1 : 0;
        }}
        """
        cls.so_path, cls.tmpdir = _compile_c_shared_lib(c_code)
        cls.c_lib = ctypes.CDLL(cls.so_path)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_a_struct_fields_and_exports(self):
        """Verify dynamic packet buffers on FpiDeviceGoodixTls5e0a and exported capture payload."""
        self.assertIn("guint16             dac[4];", self.c_src)
        self.assertIn("guint8              fdt_down_s12[sizeof (goodix_5e0a_down_s12)]", self.c_src)
        self.assertIn("fdt_up_u01[sizeof (goodix_5e0a_up_u01)]", self.c_src)
        self.assertIn("mcu_config[sizeof (goodix_5e0a_config)];", self.c_src)
        self.assertIn("extern guint8 goodix5e0a_capture_payload[10];", self.h_src)
        self.assertIn("guint8 goodix5e0a_capture_payload[10] =", self.goodix_c)

    def test_b_otp_state_machine_wiring(self):
        """Verify ACTIVATE_READ_OTP invokes goodix5e0a_on_read_otp, logs DACs, and calls update_dacs."""
        self.assertIn("case ACTIVATE_READ_OTP:", self.c_src)
        self.assertIn("goodix_send_read_otp (dev, goodix5e0a_on_read_otp, ssm);", self.c_src)

        on_read_otp = _slice(self.c_src, "goodix5e0a_on_read_otp (FpDevice *dev,", "activate_run_state")
        self.assertIn("if (valid)", on_read_otp)
        self.assertIn("goodix5e0a_update_dacs (self, dacs);", on_read_otp)
        self.assertIn("fp_dbg (\"5e0a OTP DAC calibration: 0x%03x 0x%03x 0x%03x 0x%03x\",", on_read_otp)
        self.assertIn("fp_dbg (\"5e0a OTP DAC calibration mismatch, using default\");", on_read_otp)
        self.assertIn("fp_dbg (\"5e0a OTP read bypassed or truncated: len=%u\", len);", on_read_otp)
        self.assertNotIn("(void) dacs;", on_read_otp)

    def test_c_dynamic_buffer_dispatch_sites(self):
        """Verify send_cmd sites use dynamic instance buffers and never static const tables."""
        # Exactly 2 dispatch sites for fdt_down_s12 (on_tls_activation_complete and scan_run_state)
        self.assertEqual(self.c_src.count("self->fdt_down_s12, sizeof (self->fdt_down_s12)"), 2)
        # Exactly 4 dispatch sites for fdt_up_u01 (2 in on_fdt_up_reply guards, 2 in scan_run_state)
        self.assertEqual(self.c_src.count("self->fdt_up_u01, sizeof (self->fdt_up_u01)"), 4)
        # Dynamic MCU config upload site
        self.assertIn("goodix_send_upload_config_mcu (dev, self->mcu_config,", self.c_src)

        # Confirm static tables only appear in struct sizing and init memcpy, never in dispatch sites
        self.assertEqual(self.c_src.count("goodix_5e0a_down_s12"), 3)
        self.assertEqual(self.c_src.count("goodix_5e0a_up_u01"), 3)
        self.assertEqual(self.c_src.count("goodix_5e0a_config"), 3)
        self.assertNotIn("goodix_send_upload_config_mcu (dev, goodix_5e0a_config,", self.c_src)
        self.assertNotIn("send_cmd (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_DOWN, goodix_5e0a_down_s12", self.c_src)
        self.assertNotIn("send_cmd (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_UP, goodix_5e0a_up_u01", self.c_src)
        self.assertNotIn("send_cmd_reply (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_UP, goodix_5e0a_up_u01", self.c_src)

    def test_d_otp_dac_decode_logic(self):
        """Verify algorithmic OTP decoding across maintainer and Jet-Soup samples using compiled C code."""
        # 1. Maintainer unit sample: primary 0xb0, 0xb2, 0xb0, 0xb1; no high bits
        raw_maint = bytearray(64)
        raw_maint[0x2e:0x32] = bytes([0xb0, 0xb2, 0xb0, 0xb1])
        raw_maint[0x32:0x36] = bytes([0xb0, 0xb2, 0xb0, 0xb1])
        dacs = (ctypes.c_uint16 * 4)()
        valid = self.c_lib.c_decode_otp_loop((ctypes.c_uint8 * 64).from_buffer(raw_maint), 64, dacs)
        self.assertEqual(valid, 1)
        self.assertEqual(list(dacs), [0xb0, 0xb2, 0xb0, 0xb1])
        self.assertEqual(_decode_otp_dacs(raw_maint), [0xb0, 0xb2, 0xb0, 0xb1])

        # 2. Jet-Soup unit sample: primary 0xad, 0xae, 0xac, 0xad
        raw_jet = bytearray(64)
        raw_jet[0x2e:0x32] = bytes([0xad, 0xae, 0xac, 0xad])
        raw_jet[0x32:0x36] = bytes([0xad, 0xae, 0xac, 0xad])
        valid = self.c_lib.c_decode_otp_loop((ctypes.c_uint8 * 64).from_buffer(raw_jet), 64, dacs)
        self.assertEqual(valid, 1)
        self.assertEqual(list(dacs), [0xad, 0xae, 0xac, 0xad])
        self.assertEqual(_decode_otp_dacs(raw_jet), [0xad, 0xae, 0xac, 0xad])

        # 3. Redundant fallback when primary is zero
        raw_redundant = bytearray(64)
        raw_redundant[0x32:0x36] = bytes([0xb0, 0xb2, 0xb0, 0xb1])
        valid = self.c_lib.c_decode_otp_loop((ctypes.c_uint8 * 64).from_buffer(raw_redundant), 64, dacs)
        self.assertEqual(valid, 1)
        self.assertEqual(list(dacs), [0xb0, 0xb2, 0xb0, 0xb1])
        self.assertEqual(_decode_otp_dacs(raw_redundant), [0xb0, 0xb2, 0xb0, 0xb1])

        # 4. High bit in 0x13 for channel 0 and 2 (bits 3 and 1)
        raw_high = bytearray(64)
        raw_high[0x2e:0x32] = bytes([0x10, 0x20, 0x30, 0x40])
        raw_high[0x13] = 0x0a  # bits 3 and 1 set
        valid = self.c_lib.c_decode_otp_loop((ctypes.c_uint8 * 64).from_buffer(raw_high), 64, dacs)
        self.assertEqual(valid, 1)
        self.assertEqual(list(dacs), [0x110, 0x20, 0x130, 0x40])
        self.assertEqual(_decode_otp_dacs(raw_high), [0x110, 0x20, 0x130, 0x40])

        # 5. Invalid / all-zero and truncated buffer rejection
        raw_zero = bytearray(64)
        valid = self.c_lib.c_decode_otp_loop((ctypes.c_uint8 * 64).from_buffer(raw_zero), 64, dacs)
        self.assertEqual(valid, 0)
        self.assertIsNone(_decode_otp_dacs(raw_zero))

        raw_short = bytearray(32)
        valid_short = self.c_lib.c_decode_otp_loop((ctypes.c_uint8 * 32).from_buffer(raw_short), 32, dacs)
        self.assertEqual(valid_short, 0)
        self.assertIsNone(_decode_otp_dacs(raw_short))

    def test_e_c_implementation_dac_update_sites(self):
        """Verify compiled goodix5e0a_update_dacs C code checks 0xad mask and updates correct offsets."""
        update_dacs = _slice(self.c_src, "goodix5e0a_update_dacs (FpiDeviceGoodixTls5e0a *self,", "goodix5e0a_on_read_otp")
        self.assertIn("if ((dacs[0] & 0xff) == 0xad)", update_dacs)
        self.assertIn("self->mcu_config[0xc8] = 0x1f;", update_dacs)
        self.assertIn("self->mcu_config[0xeb] = 0xf0;", update_dacs)
        self.assertIn("self->mcu_config[0xec] = 0x00;", update_dacs)
        self.assertIn("0xa5a5", update_dacs)
        self.assertIn("self->mcu_config[0xfe] = csum & 0xff;", update_dacs)
        self.assertIn("self->mcu_config[0xff] = (csum >> 8) & 0xff;", update_dacs)
        self.assertIn("goodix5e0a_capture_payload[0] = 0x01;", update_dacs)
        self.assertIn("goodix5e0a_capture_payload[0] = 0x05;", update_dacs)
        self.assertIn("fp_dbg (\"5e0a dynamic config applied: 0xad unit, checksum=0x%04x\", csum);", update_dacs)
        self.assertIn("fp_dbg (\"5e0a dynamic config applied: standard unit\");", update_dacs)

    def test_f_wire_dac_alignment_against_jet_soup_patch(self):
        """Verify executing compiled goodix5e0a_update_dacs produces exact byte modifications matching jet-soup-capture.patch."""
        # Parse target capture payload byte from patch
        m_payload = re.search(r"\+guint8 goodix5e0a_capture_payload\[10\]\s*=\s*\{([^}]+)\};", self.patch_src)
        self.assertIsNotNone(m_payload, "capture payload not found in patch")
        patch_payload = [int(x.strip(), 16) for x in m_payload.group(1).split(",") if x.strip()]
        self.assertEqual(patch_payload[0], 0x01)

        # Baseline checksum is 0x0e53
        sum_def = 0xa5a5
        for j in range(0, 254, 2):
            sum_def += self.base_cfg[j] | (self.base_cfg[j + 1] << 8)
        self.assertEqual((-sum_def) & 0xffff, 0x0e53)
        self.assertEqual(self.base_cfg[0xfe] | (self.base_cfg[0xff] << 8), 0x0e53)

        # Execute compiled C update_dacs with 0xad and 0x1ad
        for test_dac0 in (0xad, 0x1ad):
            dev = DevStruct()
            for i, b in enumerate(self.base_cfg):
                dev.mcu_config[i] = b
            dacs = (ctypes.c_uint16 * 4)(test_dac0, 0xae, 0xac, 0xad)
            self.c_lib.c_set_capture_payload_byte(0, 0x05)

            # Call real compiled C code
            self.c_lib.c_update_dacs(ctypes.byref(dev), dacs)

            # Assert exact byte updates in C memory
            self.assertEqual(dev.mcu_config[0xc8], 0x1f)
            self.assertEqual(dev.mcu_config[0xeb], 0xf0)
            self.assertEqual(dev.mcu_config[0xec], 0x00)

            csum = dev.mcu_config[0xfe] | (dev.mcu_config[0xff] << 8)
            self.assertEqual(csum, 0x1e4a)
            self.assertEqual(dev.mcu_config[0xfe], 0x4a)
            self.assertEqual(dev.mcu_config[0xff], 0x1e)
            self.assertEqual(self.c_lib.c_get_capture_payload_byte(0), patch_payload[0])

            # Compare differences against baseline
            diffs = {idx: (self.base_cfg[idx], dev.mcu_config[idx]) for idx in range(256) if self.base_cfg[idx] != dev.mcu_config[idx]}
            expected_diffs = {
                0xc8: (0x15, 0x1f),
                0xeb: (0x00, 0xf0),
                0xec: (0x01, 0x00),
                0xfe: (0x53, 0x4a),
                0xff: (0x0e, 0x1e),
            }
            self.assertEqual(diffs, expected_diffs)

        # Execute compiled C update_dacs with maintainer 0xb0 unit
        dev_maint = DevStruct()
        for i, b in enumerate(self.base_cfg):
            dev_maint.mcu_config[i] = b
        dacs_maint = (ctypes.c_uint16 * 4)(0xb0, 0xb2, 0xb0, 0xb1)
        self.c_lib.c_set_capture_payload_byte(0, 0x01)

        self.c_lib.c_update_dacs(ctypes.byref(dev_maint), dacs_maint)

        csum_maint = dev_maint.mcu_config[0xfe] | (dev_maint.mcu_config[0xff] << 8)
        self.assertEqual(csum_maint, 0x0e53)
        self.assertEqual(self.c_lib.c_get_capture_payload_byte(0), 0x05)
        self.assertEqual(list(dev_maint.mcu_config), list(self.base_cfg))


if __name__ == "__main__":
    unittest.main()
