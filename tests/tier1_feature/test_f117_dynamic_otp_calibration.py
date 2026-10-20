"""Execute the driver's OTP decoder and packet builder, without USB or root."""

import ctypes
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def function(source, name):
    """Extract a complete C definition, rather than a copied implementation."""
    start = source.index(name + " (")
    start = source.rfind("\n", 0, start - 1) + 1
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class Device(ctypes.Structure):
    _fields_ = [("dac", ctypes.c_uint16 * 4),
                ("down", ctypes.c_uint8 * 35),
                ("up", ctypes.c_uint8 * 35),
                ("config", ctypes.c_uint8 * 256),
                ("capture", ctypes.c_uint8 * 10)]


class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "libfprint-driver/goodix5e0a.c").read_text()
        transport = (ROOT / "libfprint-driver/goodix.c").read_text()
        header = (ROOT / "libfprint-driver/goodix5e0a.h").read_text()
        tables = []
        for name in ("config", "img_payload", "down_s12", "up_u01"):
            tables.append(re.search(r"static const guint8 goodix_5e0a_" + name + r"\[\d+\] = \{.*?\};", header, re.S)[0])
        cls.defaults = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", tables[0]))
        code = '''
#include <stdint.h>
#include <string.h>
typedef uint8_t guint8;
typedef uint16_t guint16;
typedef uint32_t guint32;
typedef unsigned int guint;
typedef int gboolean;
#define TRUE 1
#define FALSE 0
#define fp_dbg(...) do {} while (0)
typedef struct { guint8 capture_payload[10]; } FpiDeviceGoodixTlsPrivate;
typedef struct {
  guint16 dac[4];
  guint8 fdt_down_s12[35], fdt_up_u01[35], mcu_config[256];
  FpiDeviceGoodixTlsPrivate transport;
} FpiDeviceGoodixTls5e0a;
typedef FpiDeviceGoodixTls5e0a FpDevice;
#define FP_DEVICE(x) (x)
#define FPI_DEVICE_GOODIXTLS(x) (x)
static FpiDeviceGoodixTlsPrivate *
fpi_device_goodixtls_get_instance_private(FpDevice *dev) { return &dev->transport; }
'''
        code += "\n".join(tables) + "\n"
        code += function(transport, "goodix5e0a_set_capture_payload") + "\n"
        code += function(cls.source, "goodix5e0a_decode_otp") + "\n"
        code += function(cls.source, "goodix5e0a_update_dacs") + "\n"
        code += '''
int decode(const guint8 *data, guint16 len, guint16 *dacs) {
  return goodix5e0a_decode_otp(data, len, dacs);
}
void configure(FpiDeviceGoodixTls5e0a *self, const guint16 *dacs) {
  goodix5e0a_update_dacs(self, dacs);
}
'''
        cls.tmp = tempfile.TemporaryDirectory(prefix="goodix-otp-test-")
        cls.addClassCleanup(cls.tmp.cleanup)
        source = Path(cls.tmp.name) / "otp.c"
        library = source.with_suffix(".so")
        source.write_text(code)
        subprocess.run(["cc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.decode.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16, ctypes.POINTER(ctypes.c_uint16)]
        cls.lib.decode.restype = ctypes.c_int
        cls.lib.configure.argtypes = [ctypes.POINTER(Device), ctypes.POINTER(ctypes.c_uint16)]

    def decode(self, data):
        buffer = (ctypes.c_uint8 * len(data)).from_buffer_copy(data) if data is not None else None
        dacs = (ctypes.c_uint16 * 4)()
        valid = self.lib.decode(buffer, len(data) if data is not None else 64, dacs)
        return list(dacs) if valid else None

    def configure(self, device, dacs):
        self.lib.configure(ctypes.byref(device), (ctypes.c_uint16 * 4)(*dacs))

    def test_actual_decoder_handles_both_units_redundancy_and_unmapped_flags(self):
        for channels in ([0xb0, 0xb2, 0xb0, 0xb1], [0xad, 0xae, 0xac, 0xad]):
            for primary, secondary in ((channels, channels), (channels, [0]*4), ([0]*4, channels), ([1]*4, channels)):
                for mask in range(16):
                    with self.subTest(channels=channels, primary=primary, secondary=secondary, mask=mask):
                        raw = bytearray(64)
                        raw[0x2e:0x32] = bytes(primary)
                        raw[0x32:0x36] = bytes(secondary)
                        raw[0x13] = mask
                        self.assertEqual(self.decode(raw), list(channels))

    def test_observed_otp_flags_do_not_change_verified_wire_dacs(self):
        # Maintainer's live OTP low nibble is 0x0c. Its verified Windows wire
        # DAC words are 00b0/00b2/00b0/00b1, not 01b0/01b2/00b0/00b1.
        raw = bytearray(64)
        raw[0x13] = 0x0c
        raw[0x2e:0x32] = raw[0x32:0x36] = bytes([0xb0, 0xb2, 0xb0, 0xb1])
        self.assertEqual(self.decode(raw), [0xb0, 0xb2, 0xb0, 0xb1])

    def test_actual_decoder_rejects_missing_channel_and_truncated_reads(self):
        self.assertIsNone(self.decode(None))
        for length in range(64):
            self.assertIsNone(self.decode(bytes([0xff]) * length))
        for channel in range(4):
            raw = bytearray([1] * 64)
            raw[0x2e + channel] = raw[0x32 + channel] = 0
            self.assertIsNone(self.decode(raw))

    def assert_channels(self, device, channels):
        encoded = b"".join(v.to_bytes(2, "little") for v in channels)
        self.assertEqual(bytes(device.down)[2:10], encoded)
        self.assertEqual(bytes(device.down)[26:34], encoded)
        self.assertEqual(bytes(device.up)[2:10], encoded)
        self.assertEqual(bytes(device.capture)[2:10], encoded)

    def test_known_jet_profile_matches_wire_config_and_checksum(self):
        device = Device()
        for channels in ([0xad, 0xae, 0xac, 0xad], [0x1ad, 0xae, 0x1ac, 0xad]):
            self.configure(device, channels)
            self.assert_channels(device, channels)
            differences = {i: (a, b) for i, (a, b) in enumerate(zip(self.defaults, device.config)) if a != b}
            self.assertEqual(differences, {0xc8: (0x15, 0x1f), 0xeb: (0, 0xf0), 0xec: (1, 0), 0xfe: (0x53, 0x4a), 0xff: (0x0e, 0x1e)})
            self.assertEqual(device.capture[0], 1)
            self.assertEqual((0xa5a5 + sum(int.from_bytes(bytes(device.config)[i:i+2], "little") for i in range(0, 256, 2))) & 0xffff, 0)

    def test_recalibration_restores_defaults_and_only_full_profile_selects_jet_config(self):
        device = Device()
        self.configure(device, [0xad, 0xae, 0xac, 0xad])
        for channels in ([0xb0, 0xb2, 0xb0, 0xb1], [0xad, 0x20, 0x30, 0x40]):
            self.configure(device, channels)
            self.assertEqual(bytes(device.config), self.defaults)
            self.assertEqual(device.capture[0], 5)
            self.assert_channels(device, channels)

    def test_instances_do_not_share_capture_or_config_state(self):
        jet, standard = Device(), Device()
        self.configure(jet, [0xad, 0xae, 0xac, 0xad])
        saved = bytes(jet)
        self.configure(standard, [0xb0, 0xb2, 0xb0, 0xb1])
        self.assertEqual(bytes(jet), saved)
        self.assertNotEqual(bytes(jet.capture), bytes(standard.capture))

    def test_transport_and_activation_use_the_calibrated_instance(self):
        transport = (ROOT / "libfprint-driver/goodix.c").read_text()
        dispatch = function(transport, "goodix_send_mcu_get_image")
        self.assertIn("payload = priv->capture_payload;", dispatch)
        self.assertIn("goodix_send_read_otp (dev, goodix5e0a_on_read_otp, ssm);", self.source)
        callback = function(self.source, "goodix5e0a_on_read_otp")
        self.assertIn("goodix5e0a_decode_otp (data, len, dacs)", callback)
        self.assertIn("goodix5e0a_update_dacs (self, defaults)", callback)
        self.assertIn("goodix_send_upload_config_mcu (dev, self->mcu_config,", self.source)


if __name__ == "__main__":
    unittest.main()
