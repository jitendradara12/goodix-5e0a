"""Image-record helpers shared by native and emulated offline backends."""

import struct


class ImageOperations:
    def image(self, pixels, w=64, h=80, bits=8):
        address = self.put(bytes(pixels))
        record = bytearray(48)
        struct.pack_into("<Qhh", record, 0, address, w, h)
        record[14] = bits
        record[15] = 1
        struct.pack_into("<hI", record, 24, 1, 0)
        struct.pack_into("<I", record, 28, 10)
        record[40:42] = b"\x64\x64"
        return self.put(bytes(record))

    def quality(self, pixels):
        image = self.image(pixels)
        output = self.put(bytes(8))
        result = self.call("getQuality", [image, output])
        return [
            result,
            list(self.u.mem_read(image + 40, 2)),
            struct.unpack("<II", self.u.mem_read(output, 8)),
        ]
