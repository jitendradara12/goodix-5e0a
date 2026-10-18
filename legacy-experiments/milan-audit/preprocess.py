"""Bounded experimental vendor preprocessing through the existing emulator.

The third preprocessor argument is an OPTIONAL 0x4c98-byte feature output.
Passing NULL disables it. A 4096-byte placeholder is incorrect and must not
be used. The second argument is an enrollment-purpose flag (0 or 1), recovered
from wbdi CheckCaptureDataRequest at 0x8ff24..0x8ff65.
"""

import struct

import numpy as np

WIDTH = 64
HEIGHT = 80
PIXELS = WIDTH * HEIGHT
GUARD = bytes([0xA5]) * 64


class GuardedBuffer:
    def __init__(self, engine, data):
        self.engine = engine
        self.length = len(data)
        self.base = engine.put(GUARD + bytes(data) + GUARD)
        self.address = self.base + len(GUARD)

    def read(self):
        self.check()
        return bytes(self.engine.u.mem_read(self.address, self.length))

    def check(self):
        memory = self.engine.u.mem_read
        if bytes(memory(self.base, len(GUARD))) != GUARD:
            raise RuntimeError("Vendor call wrote before an input/output buffer")
        if bytes(memory(self.address + self.length, len(GUARD))) != GUARD:
            raise RuntimeError("Vendor call wrote after an input/output buffer")


def raw_pixels(values):
    array = np.asarray(values)
    if array.shape != (HEIGHT, WIDTH):
        raise ValueError("Expected one 64x80 frame")
    if not np.issubdtype(array.dtype, np.integer):
        raise ValueError("Raw frame must contain integer 12-bit pixels")
    if np.any(array < 0) or np.any(array > 4095):
        raise ValueError("Raw frame pixels must be between 0 and 4095")
    return array.astype("<u2").tobytes()


class VendorPreprocessor:
    def __init__(self, engine, calibration, *, calibration_state=None, layout="legacy"):
        if layout not in {"legacy", "profile10"}:
            raise ValueError("Unknown vendor raster layout")
        self.layout = layout
        self.width, self.height = (80, 64) if layout == "profile10" else (WIDTH, HEIGHT)
        self.engine = engine
        self.calibration = GuardedBuffer(engine, self._raw_pixels(calibration))
        if engine.call("ppp_param_init", [10]) != 0:
            raise RuntimeError("Vendor sensor-profile initialization failed")
        if engine.call("preprocess_init_calidata") != 0:
            raise RuntimeError("Vendor default-calibration initialization failed")
        self.state = None
        if calibration_state is not None:
            expected = engine.call("preprocess_get_calidata_len")
            if len(calibration_state) != expected or expected != 0x224B0:
                raise ValueError(
                    "Calibration state size does not match the reviewed engine"
                )
            self.state = GuardedBuffer(engine, calibration_state)
            result = engine.call(
                "preprocess_load_calidata", [self.state.address, expected]
            )
            if self.state.read() != calibration_state:
                raise RuntimeError("Vendor load changed the source calibration state")
            if result != 0:
                raise RuntimeError(
                    f"Vendor calibration state rejected with 0x{result:x}"
                )
        record = bytearray(48)
        struct.pack_into("<Q", record, 24, self.calibration.address)
        struct.pack_into("<II", record, 36, self.height, self.width)
        self.record = GuardedBuffer(engine, record)
        result = engine.call("preprocessor_init", [self.record.address])
        self.record.check()
        self.calibration.check()
        if result != 0:
            raise RuntimeError(f"Vendor calibration failed with 0x{result:x}")

    def _raw_pixels(self, raw):
        canonical = raw_pixels(raw)
        if self.layout == "legacy":
            return canonical
        # Profile 10's parameter table fixes SENSOR_ROW=64, SENSOR_COL=80.
        # The preprocessor uses those globals rather than the image dimensions.
        # Keep the caller/matcher's 64x80 raster canonical at both boundaries.
        return np.frombuffer(canonical, dtype="<u2").reshape(HEIGHT, WIDTH).T.copy().tobytes()

    def save_state(self):
        size = self.engine.call("preprocess_get_calidata_len")
        if size != 0x224B0:
            raise RuntimeError("Unexpected calibration state size")
        state = GuardedBuffer(self.engine, bytes(size))
        length = GuardedBuffer(self.engine, struct.pack("<I", size))
        result = self.engine.call(
            "preprocess_save_calidata", [state.address, length.address]
        )
        if result != 0 or struct.unpack("<I", length.read())[0] != size:
            raise RuntimeError(
                f"Vendor calibration state save failed with 0x{result:x}"
            )
        return state.read()

    def process(self, raw, *, enrolling=False):
        engine = self.engine
        source_pixels = GuardedBuffer(engine, self._raw_pixels(raw))
        output_pixels = GuardedBuffer(engine, bytes(PIXELS))

        def image(data, length, bits):
            record = bytearray(48)
            struct.pack_into("<Qhh", record, 0, data, self.width, self.height)
            record[14] = bits
            record[15] = 1
            struct.pack_into("<Ih", record, 20, length, 1)
            struct.pack_into("<I", record, 28, 10)
            return GuardedBuffer(engine, record)

        source = image(source_pixels.address, 2 * PIXELS, 16)
        output = image(output_pixels.address, PIXELS, 8)
        purpose = GuardedBuffer(engine, struct.pack("<I", int(enrolling)))
        metrics = GuardedBuffer(engine, bytes(8))
        result = engine.call(
            "preprocessor",
            [source.address, purpose.address, 0, output.address, metrics.address, 0, 0],
        )
        for buffer in (source_pixels, output_pixels, source, output, purpose, metrics):
            buffer.check()
        if source_pixels.read() != self._raw_pixels(raw):
            raise RuntimeError("Vendor call changed the source pixels")
        coverage, quality = struct.unpack("<II", metrics.read())
        pixels = output_pixels.read()
        if self.layout == "profile10":
            pixels = np.frombuffer(pixels, dtype=np.uint8).reshape(64, 80).T.copy().tobytes()
        return {
            "return_code": result & 0xFFFFFFFF,
            "quality": quality,
            "coverage": coverage,
            "pixels": pixels,
        }
